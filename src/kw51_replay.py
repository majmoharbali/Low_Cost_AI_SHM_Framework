"""Freeze reference detectors and replay the published KW51 hourly features."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from .environment_baseline import METHODS, ResidualModel, fit_model, spline_penalty, support
from .kw51 import ARCHIVE_SHA256, ENVIRONMENT, TrackedModes, load_tracked_modes, period_masks


PURGE_HOURS = 24
MIN_ROWS = 200
BOOTSTRAP_HOURS = 168
BOOTSTRAP_SEED = 513
SCHEMA_VERSION = 1


def partitions(hours):
    masks = period_masks(hours)
    reference = np.flatnonzero(masks["pre_retrofit"])
    cut_fit, cut_cal = len(reference) * 3 // 5, len(reference) * 4 // 5
    if cut_fit <= PURGE_HOURS or cut_cal - cut_fit <= PURGE_HOURS:
        raise ValueError("Reference record too short for purged chronological blocks")
    return {
        "fit": reference[:cut_fit - PURGE_HOURS],
        "fit_purge": reference[cut_fit - PURGE_HOURS:cut_fit],
        "calibration": reference[cut_fit:cut_cal - PURGE_HOURS],
        "calibration_purge": reference[cut_cal - PURGE_HOURS:cut_cal],
        "reference_test": reference[cut_cal:],
        **{period: np.flatnonzero(masks[period]) for period in ("retrofit", "post_retrofit", "boundary_excluded")},
    }


def bounds_of(hours):
    return [str(hours[0]), str(hours[-1])] if len(hours) else None


def temperature_column(data, label):
    return data.environment[:, tuple(ENVIRONMENT).index(label)]


def _autocorrelation(series):
    results = {}
    for lag in (1, 24, 168):
        a, b = series[:-lag], series[lag:]
        valid = np.isfinite(a) & np.isfinite(b)
        a, b = a[valid], b[valid]
        correlation = None
        if len(a) >= 20 and np.std(a) > 0 and np.std(b) > 0:
            correlation = float(np.corrcoef(a, b)[0, 1])
        results[lag] = {"pairs": len(a), "r": correlation}
    return results


def _calibrate(model, t_cal, f_cal, valid):
    scores = model.scores(t_cal[valid], f_cal[valid])
    if len(scores) < MIN_ROWS or not np.isfinite(scores).all():
        raise ValueError("Need at least 200 eligible calibration hours")
    cutoff = float(np.quantile(scores, 0.99, method="higher"))
    return {"model": asdict(model), "threshold": cutoff, "calibration_hours": len(scores)}


def _paired_temperature_fit(t_fit, t_cal, f_fit, f_cal):
    """Use the same complete rows and a joint support rule for both proxies."""
    fit = np.isfinite(f_fit).all(axis=1)
    cal = np.isfinite(f_cal).all(axis=1)
    for label in t_fit:
        fit &= np.isfinite(t_fit[label])
        cal &= np.isfinite(t_cal[label])
    if fit.sum() < MIN_ROWS:
        return {"unavailable": "Fewer than 200 common fitting hours"}
    models = {label: fit_model("linear", t[fit], f_fit[fit]) for label, t in t_fit.items()}
    for label, model in models.items():
        cal &= support(t_cal[label], model.bounds)
    if cal.sum() < MIN_ROWS:
        return {"unavailable": "Fewer than 200 jointly supported calibration hours"}
    return {
        "common_fitting_hours": int(fit.sum()),
        "models": {label: _calibrate(model, t_cal[label], f_cal, cal) for label, model in models.items()},
    }


def freeze(data: TrackedModes) -> dict:
    """Fit and calibrate with pre-retrofit hours only."""
    split = partitions(data.hours)
    fit, cal = split["fit"], split["calibration"]
    temperatures = {label: temperature_column(data, label) for label in ("tVL", "tBD31A")}
    air = temperatures["tVL"]
    joint = np.isfinite(data.frequency_hz[fit]) & np.isfinite(air[fit, None])
    coverage = joint.mean(axis=0)
    columns = np.flatnonzero(coverage >= 0.90)
    if not len(columns):
        raise ValueError("No mode meets the fitting-period 90% joint coverage rule")
    f_fit = data.frequency_hz[np.ix_(fit, columns)]
    f_cal = data.frequency_hz[np.ix_(cal, columns)]
    t_fit, t_cal = air[fit], air[cal]
    complete = np.isfinite(f_fit).all(axis=1) & np.isfinite(t_fit)
    if complete.sum() < MIN_ROWS:
        raise ValueError("Fewer than 200 common fitting hours")
    penalty, tuning = spline_penalty(t_fit, f_fit, purge_hours=PURGE_HOURS)
    models = {}
    for method in METHODS:
        model = fit_model(method, t_fit[complete], f_fit[complete], penalty=penalty)
        eligible = np.isfinite(f_cal).all(axis=1) & support(t_cal, model.bounds)
        models[method] = _calibrate(model, t_cal, f_cal, eligible)
        residuals = np.full_like(f_fit, np.nan)
        residuals[complete] = model.residuals(t_fit[complete], f_fit[complete])
        models[method]["fitting_residual_autocorrelation"] = {
            int(col + 1): _autocorrelation(residuals[:, i]) for i, col in enumerate(columns)
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "archive_sha256": ARCHIVE_SHA256,
        "primary_temperature": "tVL",
        "mode_ids": (columns + 1).tolist(),
        "fitting_joint_coverage_by_mode": coverage.tolist(),
        "partitions": {
            name: {"hours": len(ids), "bounds": bounds_of(data.hours[ids])}
            for name, ids in split.items()
        },
        "common_fitting_hours": int(complete.sum()),
        "fitting_temperature_autocorrelation": _autocorrelation(np.where(complete, t_fit, np.nan)),
        "spline_penalty": penalty,
        "spline_tuning": tuning,
        "primary_models": models,
        "paired_temperature_sensitivity": _paired_temperature_fit(
            {k: t[fit] for k, t in temperatures.items()},
            {k: t[cal] for k, t in temperatures.items()}, f_fit, f_cal,
        ),
    }


def alarm_trace(hours, scores, threshold):
    exceed = np.isfinite(scores) & (scores > threshold)
    adjacent = np.r_[False, np.diff(hours) == np.timedelta64(1, "h")]
    persisted = exceed & np.r_[False, exceed[:-1]] & adjacent
    onset = persisted & ~(np.r_[False, persisted[:-1]] & adjacent)
    return exceed, persisted, onset


def _summary(hours, scores, threshold):
    exceed, alarm, onset = alarm_trace(hours, scores, threshold)
    scored = int(np.isfinite(scores).sum())
    return {
        "scheduled": len(hours),
        "scored": scored,
        "abstained": len(hours) - scored,
        "coverage": scored / len(hours),
        "exceedances": int(exceed.sum()),
        "exceedance_fraction_scored": float(exceed.sum() / scored) if scored else None,
        "alarm_hours": int(alarm.sum()),
        "alarm_fraction_scored": float(alarm.sum() / scored) if scored else None,
        "alarm_fraction_scheduled": float(alarm.mean()),
        "episodes": int(onset.sum()),
        "episodes_per_30_scheduled_days": float(onset.sum() * 720 / len(hours)),
    }, onset


def _reference_intervals(onsets):
    """Paired moving-block intervals on the scheduled reference-test grid."""
    n = len(next(iter(onsets.values())))
    block = BOOTSTRAP_HOURS
    if n < 2 * block:
        return {"unavailable": "Reference test shorter than two bootstrap blocks"}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    starts = rng.integers(0, n - block + 1, size=(2000, (n + block - 1) // block))
    indices = (starts[:, :, None] + np.arange(block)).reshape(2000, -1)[:, :n]
    rates = {key: flags[indices].sum(axis=1) * 720 / n for key, flags in onsets.items()}

    def interval(values):
        return np.quantile(values, [0.025, 0.975]).tolist()

    return {
        "block_hours": block,
        "seed": BOOTSTRAP_SEED,
        "replicates": len(starts),
        "episodes_per_30_days_interval": {key: interval(rate) for key, rate in rates.items()},
        "difference_from_constant_interval": {
            key: interval(rate - rates["constant"]) for key, rate in rates.items() if key != "constant"
        },
    }


def _evaluate_models(hours, frequency, artifacts, temperatures):
    raw = {
        key: ResidualModel(**item["model"]).scores(temperatures[key], frequency)
        for key, item in artifacts.items()
    }
    common = np.logical_and.reduce([np.isfinite(scores) for scores in raw.values()])
    results, onsets = {}, {}
    for key, item in artifacts.items():
        matched, onsets[key] = _summary(hours, np.where(common, raw[key], np.nan), item["threshold"])
        operating, _ = _summary(hours, raw[key], item["threshold"])
        results[key] = {"common": matched, "operating": operating}
    return results, onsets


def evaluate(data: TrackedModes, frozen: dict) -> dict:
    """Score untouched blocks using only the frozen model and calibration cutoffs."""
    if frozen["schema_version"] != SCHEMA_VERSION or frozen["archive_sha256"] != ARCHIVE_SHA256:
        raise ValueError("Frozen model schema or archive identity differs")
    columns = np.asarray(frozen["mode_ids"], dtype=int) - 1
    if not len(columns) or np.any((columns < 0) | (columns >= data.frequency_hz.shape[1])):
        raise ValueError("Frozen mode panel is incompatible with the archive")
    split = partitions(data.hours)
    primary = frozen["primary_models"]
    low, high = primary["linear"]["model"]["bounds"]
    sensitivity = frozen["paired_temperature_sensitivity"]
    results = {}
    for name in ("reference_test", "retrofit", "post_retrofit"):
        ids = split[name]
        hours = data.hours[ids]
        frequency = data.frequency_hz[np.ix_(ids, columns)]
        air = temperature_column(data, frozen["primary_temperature"])[ids]
        panel = np.isfinite(frequency).all(axis=1)
        finite_temp = np.isfinite(air)
        outside = finite_temp & ~support(air, (low, high))
        metrics, onsets = _evaluate_models(hours, frequency, primary, dict.fromkeys(primary, air))
        period = {
            "bounds": bounds_of(hours),
            "missing_panel": int((~panel).sum()),
            "missing_temperature": int((~finite_temp).sum()),
            "outside_fitting_temperature": int(outside.sum()),
            "outside_fitting_temperature_with_panel": int((outside & panel).sum()),
            "models": metrics,
        }
        if name == "reference_test":
            period["common_episode_rate_bootstrap"] = _reference_intervals(onsets)
        if "models" in sensitivity:
            paired = sensitivity["models"]
            stats, _ = _evaluate_models(
                hours, frequency, paired, {label: temperature_column(data, label)[ids] for label in paired},
            )
            period["paired_temperature_sensitivity"] = {label: counts["common"] for label, counts in stats.items()}
        else:
            period["paired_temperature_sensitivity"] = sensitivity
        results[name] = period
    return {"archive_sha256": ARCHIVE_SHA256, "mode_ids": frozen["mode_ids"], "periods": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for name in ("freeze", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("archive", type=Path)
        command.add_argument("--frozen", type=Path, required=True)
        if name == "evaluate":
            command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        data = load_tracked_modes(args.archive)
        if args.action == "freeze":
            path, result = args.frozen, freeze(data)
        else:
            if args.frozen.resolve() == args.output.resolve():
                raise ValueError("Evaluation output must differ from the frozen artifact")
            raw = args.frozen.read_bytes()
            path, result = args.output, evaluate(data, json.loads(raw))
            result["frozen_sha256"] = hashlib.sha256(raw).hexdigest()
        path.parent.mkdir(parents=True, exist_ok=True)
        # A fresh run should use a new directory, preserving the earlier freeze.
        with path.open("x", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    except (ValueError, KeyError, OSError, np.linalg.LinAlgError) as exc:
        parser.exit(2, f"KW51 replay failed: {exc}\n")
    print(path)


if __name__ == "__main__":
    main()
