"""Compare reduced sensor layouts and controlled corruption on KW51 ambient records."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from io import BytesIO
from itertools import combinations
import json
from pathlib import Path
from time import perf_counter

import numpy as np
from scipy.io import loadmat
from scipy.signal import resample_poly

from .identification import identify_modes, modal_assurance
from .kw51 import CHANNELS, load_tracked_modes
from .kw51_fetch_raw import scheduled_hours
from .records import SignalWindow


DECK = CHANNELS[:6]
MODE_IDS = (3, 5, 6, 9, 13)
DECIMATION = 16
NPERSEG = 2048
SAMPLE_RATE = 825.8064516129032
BIN = SAMPLE_RATE / DECIMATION / NPERSEG
ALL_CHANNELS = tuple(range(len(DECK)))
CORRUPTIONS = ("noise_5db", "dc_bias", "timing", "burst")
PHASES = ("fit", "calibration", "reference_test", "retrofit", "post_retrofit")


@dataclass(frozen=True)
class Record:
    hour: str
    period: str
    acquired_at: datetime | None = None
    samples: np.ndarray | None = None
    reason: str | None = None


def read_record(row, root):
    """Read a hash-bound, simultaneous six-channel interval in m/s²."""
    hour, period = row["scheduled_hour_utc"], row["period"]
    if row["status"] != "downloaded":
        return Record(hour, period, reason=row["status"])
    if Path(row["file"]).name != row["file"]:
        raise ValueError("Manifest file must be a local filename")
    raw = (root / row["file"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {row['file']}")
    accel = loadmat(BytesIO(raw), simplify_cells=True, variable_names=["predat_a"])["predat_a"]
    clock, values, labels = accel["sdn"], accel["tdata"], tuple(accel["labels"])
    rate = float(accel["fs"])
    if (
        clock.ndim != 1 or values.shape != (len(clock), len(labels))
        or len(set(labels)) != len(labels) or not set(DECK).issubset(labels)
        or not np.isclose(rate, SAMPLE_RATE, rtol=0.0, atol=1e-6)
        or not np.isfinite(clock).all()
    ):
        raise ValueError(f"Inconsistent acquisition arrays in {row['file']}")
    # The serial time axis is common to all channels. Allow float round-off
    # of a MATLAB day number, but reject a gap, shift or rate inconsistency.
    seconds = (clock - 719529.0) * 86400.0
    start = datetime.fromtimestamp(seconds[0], timezone.utc)
    scheduled = datetime.fromisoformat(hour)
    name_start = datetime.strptime(Path(row["file"]).stem, "ambient_%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    if (
        abs((start - name_start).total_seconds()) > 0.01
        or scheduled.hour != name_start.hour or scheduled.date() != name_start.date()
        or not np.allclose(seconds - seconds[0], np.arange(len(clock)) / rate, rtol=0, atol=3e-5)
    ):
        raise ValueError(f"Invalid common time base in {row['file']}")
    length = int(np.ceil(rate * 121))
    if len(clock) < length:
        return Record(hour, period, reason="too_short_for_common_crop")
    selected = values[:length, [labels.index(label) for label in DECK]].T
    if not np.isfinite(selected).all():
        return Record(hour, period, reason="incomplete_full_deck")
    return Record(hour, period, start, resample_poly(selected, 1, DECIMATION, axis=1))


def scenario_data(samples, layout, condition, index):
    """Use equal-length intervals and never modify the source arrays."""
    size = int(120 * SAMPLE_RATE / DECIMATION)
    # Span the intended skew in every layout, including a two-channel pair.
    offsets = np.zeros(len(layout), dtype=int)
    if condition == "timing":
        offsets = np.rint(np.linspace(0, 3, len(layout))).astype(int)
    rows = np.array([
        samples[channel, 4 - delay:4 - delay + size]
        for channel, delay in zip(layout, offsets, strict=True)
    ])
    quality = ["valid"] * len(layout)
    if condition == "noise_5db":
        rng = np.random.default_rng([47, index])
        noise = rng.normal(size=(len(DECK), size))[list(layout)]
        rms = np.sqrt(np.mean(np.square(rows), axis=1, keepdims=True))
        rows += rms * 10 ** (-5 / 20) * noise
    elif condition == "dc_bias":
        rows += np.where(np.array(layout) % 2, -0.002, 0.002)[:, None]
    elif condition == "burst" and index % 4 == 0:
        channel = index // 4 % len(layout)
        mid, count = size // 2, round(2 * SAMPLE_RATE / DECIMATION)
        rows[channel, mid:mid + count] = np.nan
        quality[channel] = "missing"
    return rows, tuple(quality)


def _run_fdd(record, layout, condition, index, bands):
    if record.samples is None:
        return None, None
    values, quality = scenario_data(record.samples, layout, condition, index)
    window = SignalWindow(
        values, SAMPLE_RATE / DECIMATION, tuple(DECK[i] for i in layout),
        record.hour, record.acquired_at, "kw51_ambient", quality=quality,
    )
    begin = perf_counter()
    modes = identify_modes(window, bands, now=window.end_at, nperseg=NPERSEG)
    return modes, perf_counter() - begin


def _frequency(modes, column):
    return modes[column].frequency_hz if modes is not None else None


def _pilot_modes(records, tracked):
    by_hour = {str(hour): i for i, hour in enumerate(tracked.hours)}
    indices = [i for i, row in enumerate(records) if row.period == "fit" and row.samples is not None]
    if len(indices) < 8:
        raise ValueError("Fewer than eight usable development recordings")
    provider = tracked.frequency_hz[[by_hour[records[i].hour[:13]] for i in indices]]
    bands, mode_ids = [], []
    for mode in MODE_IDS:
        values = provider[:, mode - 1]
        finite = values[np.isfinite(values)]
        if len(finite) >= 8:
            centre = float(np.median(finite))
            bands.append((centre - 0.12, centre + 0.12))
            mode_ids.append(mode)
    if not bands:
        raise ValueError("No candidate frequency band has eight provider estimates on development hours")
    identified = [_run_fdd(records[i], ALL_CHANNELS, "clean", i, bands)[0] for i in indices]
    checks, qualified = {}, []
    for j, mode in enumerate(mode_ids):
        values = np.array([_frequency(estimates, j) for estimates in identified], dtype=float)
        pair = np.isfinite(values) & np.isfinite(provider[:, mode - 1])
        within = np.abs(values[pair] - provider[pair, mode - 1]) <= 2 * BIN
        count = int(np.isfinite(values).sum())
        accepted = count / len(indices) >= 0.75 and pair.sum() >= 8 and within.mean() >= 0.70
        checks[mode] = {
            "band_hz": bands[j], "development_identified": count, "development_usable": len(indices),
            "provider_pairs": int(pair.sum()), "within_two_bins": int(within.sum()), "qualified": bool(accepted),
        }
        if accepted:
            qualified.append(j)
    selected = sorted(qualified, key=lambda j: (-checks[mode_ids[j]]["development_identified"], mode_ids[j]))[:2]
    return bands, mode_ids, checks, selected, identified


def _layouts(development, selected):
    # FDD vectors are unit normalised. Use development medians of their
    # squared components to rank subsets for coverage in both directions.
    energy = []
    for mode in selected:
        shapes = np.array([row[mode].shape for row in development if row[mode].shape is not None])
        median = np.median(np.abs(shapes) ** 2, axis=0)
        energy.append(median / median.sum())
    rng = np.random.default_rng(47)
    layouts = {"full6": ALL_CHANNELS}
    for size in (4, 2):
        candidates = list(combinations(ALL_CHANNELS, size))
        mixed = [row for row in candidates if len({DECK[i][-1] for i in row}) == 2]

        def rank(layout):
            # Channels with the same longitudinal station index count once.
            stations = len({DECK[i][3:5] for i in layout})
            retained = min((values[list(layout)].sum() for values in energy), default=0.0)
            return -retained, -stations, layout

        layouts[f"engineered{size}"] = min(mixed, key=rank)
        pool = [layout for layout in candidates if layout != layouts[f"engineered{size}"]]
        for k, index in enumerate(rng.choice(len(pool), 3, replace=False), start=1):
            layouts[f"random{size}_{k}"] = pool[index]
    return layouts


def _fit_change_score(frequencies, records, panel):
    if not panel:
        return {"unavailable": "No mode passed development comparability checks"}
    samples = np.asarray(frequencies, dtype=float)[:, panel]
    complete = np.isfinite(samples).all(axis=1)
    phases = np.array([record.period for record in records])
    fit, cal = samples[complete & (phases == "fit")], samples[complete & (phases == "calibration")]
    counts = {"fit": len(fit), "calibration": len(cal)}
    if min(counts.values()) < 8:
        return {"unavailable": "Fewer than eight complete hours in a reference block", **counts}
    centre = np.median(fit, axis=0)
    scale = np.maximum(1.4826 * np.median(np.abs(fit - centre), axis=0), BIN)
    scores = (np.abs(cal - centre) / scale).max(axis=1)
    return {"centre": centre.tolist(), "scale": scale.tolist(),
            "threshold": float(np.quantile(scores, 0.99, method="higher")), **counts}


def _flags(frequencies, panel, model):
    result = np.full(len(frequencies), np.nan)
    if "threshold" in model:
        freq = np.asarray(frequencies, dtype=float)[:, panel]
        complete = np.isfinite(freq).all(axis=1)
        score = (np.abs(freq[complete] - model["centre"]) / model["scale"]).max(axis=1)
        result[complete] = score > model["threshold"]
    return result


def _scenario_summary(scenario, clean_full, layout, flags, full_flags, records, mode_ids):
    modes, timings = zip(*scenario)
    baseline, _ = zip(*clean_full)
    report = {}
    for phase in PHASES:
        ids = [i for i, record in enumerate(records) if record.period == phase]
        observed = np.isfinite(flags[ids])
        common = observed & np.isfinite(full_flags[ids])
        times = [timings[i] for i in ids if timings[i] is not None]
        metrics = {
            "scheduled": len(ids), "scorable": int(observed.sum()),
            "flags": int(np.nansum(flags[ids])), "paired_flags": int(common.sum()),
            "flag_disagreements": int((flags[ids][common] != full_flags[ids][common]).sum()),
            "median_identification_ms": float(1000 * np.median(times)) if times else None,
            "modes": {},
        }
        for j, mode in enumerate(mode_ids):
            deviations, assurance, reasons = [], [], {}
            count = lost = 0
            for i in ids:
                base = baseline[i][j] if baseline[i] is not None else None
                result = modes[i][j] if modes[i] is not None else None
                available = result is not None and result.frequency_hz is not None
                count += available
                if not available:
                    reason = result.reason if result is not None else records[i].reason
                    reasons[reason] = reasons.get(reason, 0) + 1
                if base is not None and base.frequency_hz is not None:
                    if available:
                        deviations.append(abs(result.frequency_hz - base.frequency_hz))
                        assurance.append(modal_assurance(result.shape, base.shape[list(layout)]))
                    else:
                        lost += 1
            metrics["modes"][mode] = {
                "identified": count, "lost_vs_full": lost, "paired_estimates": len(deviations),
                "median_absolute_delta_hz": float(np.median(deviations)) if deviations else None,
                "within_one_bin": sum(value <= BIN * (1 + 1e-8) for value in deviations),
                "median_mac_on_shared_channels": float(np.median(assurance)) if assurance else None,
                "abstentions": reasons,
            }
        report[phase] = metrics
    return report


def _acquisition_results(evaluated, flags, records):
    return [
        {
            "hour_utc": record.hour,
            "period": record.period,
            "flag": bool(flag) if np.isfinite(flag) else None,
            "record_reason": record.reason,
            "modes": [
                {"frequency_hz": mode.frequency_hz, "reason": mode.reason}
                for mode in modes
            ] if modes is not None else None,
        }
        for (modes, _), flag, record in zip(evaluated, flags, records, strict=True)
    ]


def pilot(manifest, modal_archive, *, include_acquisitions=False):
    rows = json.loads(manifest.read_text(encoding="utf-8"))
    if [(row["period"], row["scheduled_hour_utc"]) for row in rows] != [
        (period, hour.isoformat() + "Z") for period, hour in scheduled_hours()
    ]:
        raise ValueError("Manifest does not match the prespecified schedule")
    records = [read_record(row, manifest.parent) for row in rows]
    bands, mode_ids, checks, panel, development = _pilot_modes(records, load_tracked_modes(modal_archive))
    layouts = _layouts(development, panel)
    scenarios = [(key, layout, "clean", key) for key, layout in layouts.items()]
    scenarios += [
        (f"{key}_{condition}", layouts[key], condition, key)
        for key in ("full6", "engineered2") for condition in CORRUPTIONS
    ]
    models, results = {}, {}
    for name, layout, condition, clean in scenarios:
        evaluated = [
            _run_fdd(record, layout, condition, index, bands)
            for index, record in enumerate(records)
        ]
        frequencies = [[_frequency(row, j) for j in range(len(mode_ids))] for row, _ in evaluated]
        if condition == "clean":
            models[name] = _fit_change_score(frequencies, records, panel)
        flags = _flags(frequencies, panel, models[clean])
        if name == "full6":
            clean_full, full_flags = evaluated, flags
        results[name] = {
            "channels": [DECK[i] for i in layout],
            "condition": condition, "frozen_model": clean,
            "periods": _scenario_summary(evaluated, clean_full, layout, flags, full_flags, records, mode_ids),
        }
        if include_acquisitions:
            results[name]["acquisitions"] = _acquisition_results(evaluated, flags, records)
    return {
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "sample_rate_hz": SAMPLE_RATE / DECIMATION, "bin_hz": BIN,
        "development_modes": checks, "scoring_panel": [mode_ids[j] for j in panel],
        "excluded_records": [{"hour": r.hour, "reason": r.reason} for r in records if r.reason],
        "models": models, "scenarios": results,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("modal_archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--acquisitions", action="store_true", help="Include per-hour results for replay")
    args = parser.parse_args()
    report = pilot(args.manifest, args.modal_archive, include_acquisitions=args.acquisitions)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(args.output)
