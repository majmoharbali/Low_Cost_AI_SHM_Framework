"""Compare co-mounted accelerometers using independently recorded sample timing."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
import hashlib
from io import StringIO
import json
from pathlib import Path

import numpy as np
from scipy import signal


FIELDS = ("sample_index", "time_s", "acceleration_m_s2", "quality")
MIN_BLOCKS = 6


@dataclass(frozen=True)
class Capture:
    time: np.ndarray
    acceleration: np.ndarray
    present: np.ndarray
    clipped: int


def _nonempty(metadata, fields):
    for field in fields:
        if not isinstance(metadata[field], str) or not metadata[field].strip():
            raise ValueError(f"Manifest field {field!r} needs a non-empty value")


def _read_capture(directory, spec, count):
    _nonempty(spec, ("file", "instrument", "axis", "sha256"))
    name = Path(spec["file"])
    if name.name != spec["file"]:
        raise ValueError("Capture paths must be local filenames")
    raw = (directory / name).read_bytes()
    if hashlib.sha256(raw).hexdigest() != spec["sha256"]:
        raise ValueError(f"SHA-256 mismatch for {name}")
    rows = csv.DictReader(StringIO(raw.decode("utf-8-sig"), newline=""))
    if tuple(rows.fieldnames or ()) != FIELDS:
        raise ValueError(f"Wrong CSV header in {name}. Expected: {', '.join(FIELDS)}")
    time = np.full(count, np.nan)
    acceleration = np.full(count, np.nan)
    present = np.zeros(count, dtype=bool)
    clipped = 0
    last_index, last_time = -1, -np.inf
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Wrong number of CSV fields in {name}")
        index, stamp = int(row["sample_index"]), float(row["time_s"])
        if not last_index < index < count or not np.isfinite(stamp) or stamp <= last_time:
            raise ValueError(f"{name} has repeated, unordered or invalid sample indices or times")
        quality = row["quality"]
        if quality == "valid":
            value = float(row["acceleration_m_s2"])
            if not np.isfinite(value):
                raise ValueError("A valid sample must have finite SI acceleration")
            acceleration[index] = value
        elif quality == "clipped":
            clipped += 1
        elif quality != "invalid":
            raise ValueError(f"Unknown sample quality {quality!r}")
        time[index], present[index] = stamp, True
        last_index, last_time = index, stamp
    return Capture(time, acceleration, present, clipped)


def _capture_counts(capture):
    sent = int(capture.present.sum())
    valid = int(np.isfinite(capture.acceleration).sum())
    return {
        "recorded": sent, "missing_slots": len(capture.present) - sent,
        "valid": valid, "invalid_or_clipped": sent - valid, "clipped": capture.clipped,
    }


def _clock_report(reference, candidate, fs):
    nominal = np.arange(len(reference.time)) / fs
    if not reference.present.any() or not candidate.present.any():
        return {"supported": False, "reason": "Missing clock data from one or both instruments"}
    overlap = reference.present & candidate.present
    if not overlap.any():
        return {"supported": False, "reason": "No shared sample indices for checking clock skew"}
    relative = candidate.time[overlap] - reference.time[overlap]
    t = nominal[overlap]
    centered = t - t.mean()
    drift = float(centered @ relative / (centered @ centered) * 1e6) if len(t) > 1 else None
    deviation = [float(np.nanmax(np.abs(x.time - nominal))) for x in (reference, candidate)]
    skew = float(np.max(np.abs(relative)))
    bound = 0.25 / fs
    return {
        "supported": max(skew, *deviation) <= bound,
        "paired_timestamp_slots": len(relative),
        "relative_max_abs_ms": skew * 1000,
        "relative_median_ms": float(np.median(relative) * 1000),
        "relative_drift_ppm": drift,
        "reference_max_grid_error_ms": deviation[0] * 1000,
        "candidate_max_grid_error_ms": deviation[1] * 1000,
        "max_allowed_error_ms": bound * 1000,
    }


def _band_indices(frequencies, band, *, minimum):
    indices = np.flatnonzero((frequencies >= band[0]) & (frequencies <= band[1]))
    if len(indices) < minimum:
        raise ValueError(f"Frequency band {band} needs at least {minimum} spectral bins")
    return indices


def _tone_comparison(frequencies, reference, candidate, cross, band, min_reference_rms, df):
    indices = _band_indices(frequencies, band, minimum=3)
    ref_index = indices[np.argmax(reference[indices])]
    candidate_index = indices[np.argmax(candidate[indices])]
    reference_rms = float(np.sqrt(reference[indices].sum() * df))
    if reference_rms < min_reference_rms or ref_index in (indices[0], indices[-1]):
        return {"status": "unavailable", "reason": "Reference tone is weak or at the search band boundary",
                "reference_tone_rms_m_s2": reference_rms}
    denominator = reference[ref_index] * candidate[ref_index]
    coherence = float(np.clip(abs(cross[ref_index]) ** 2 / denominator, 0, 1)) if denominator > 0 else 0.0
    transfer = cross[ref_index] / reference[ref_index]
    gain = float(abs(transfer))
    phase = float(np.angle(transfer, deg=True)) if gain > 0 else None
    frequency_error = float(abs(frequencies[candidate_index] - frequencies[ref_index]))
    checks = {
        "frequency_within_one_bin": frequency_error <= df * (1 + 1e-10),
        "candidate_peak_inside_band": bool(candidate_index not in (indices[0], indices[-1])),
        "gain_within_10_percent": 0.90 <= gain <= 1.10,
        "phase_within_10_degrees": phase is not None and abs(phase) <= 10,
        "coherence_at_least_0_95": coherence >= 0.95,
    }
    return {
        "status": "meets_pilot_targets" if all(checks.values()) else "misses_pilot_targets",
        "reference_tone_rms_m_s2": reference_rms,
        "reference_peak_hz": float(frequencies[ref_index]), "candidate_peak_hz": float(frequencies[candidate_index]),
        "absolute_frequency_error_hz": frequency_error,
        "gain_candidate_over_reference": gain, "candidate_phase_relative_to_reference_deg": phase,
        "coherence": coherence, "checks": checks,
    }


def _band(metadata, key, fs):
    low, high = map(float, metadata[key])
    if not 0 < low < high < fs / 2:
        raise ValueError(f"{key} must be a positive band below Nyquist")
    return low, high


def compare(manifest):
    """Return an auditable single-axis comparison without filling or aligning away gaps."""
    raw = manifest.read_bytes()
    spec = json.loads(raw)
    source = spec["source_kind"]
    if spec["schema_version"] != 1 or source not in ("bench_measured", "synthetic_fixture"):
        raise ValueError("Use schema version 1 and an explicit bench_measured or synthetic_fixture source")
    _nonempty(spec, ("capture_id", "session_id", "mounting", "shared_time_reference", "start_utc"))
    start = datetime.fromisoformat(spec["start_utc"])
    if start.utcoffset() is None or start.utcoffset().total_seconds() != 0:
        raise ValueError("start_utc must specify UTC explicitly")
    _nonempty(spec["reference"], ("calibration_record",))
    _nonempty(spec["candidate"], ("firmware_and_configuration",))
    if spec["reference"]["file"] == spec["candidate"]["file"] or spec["reference"]["sha256"] == spec["candidate"]["sha256"]:
        raise ValueError("Use distinct instrument captures")
    fs, count, segment = float(spec["fs_hz"]), spec["expected_samples"], spec["segment_samples"]
    if (
        not np.isfinite(fs) or fs <= 0 or type(count) is not int or type(segment) is not int
        or not 16 <= segment <= count <= 1_000_000
    ):
        raise ValueError("Sampling rate, expected count and spectral segment length must be valid")
    evaluation_band = _band(spec, "evaluation_band_hz", fs)
    tone = spec["tone"]
    tone_band = None if tone is None else _band(tone, "search_band_hz", fs)
    if tone_band is not None:
        minimum_rms = float(tone["minimum_reference_rms_m_s2"])
        if (
            not np.isfinite(minimum_rms) or minimum_rms <= 0
            or not evaluation_band[0] <= tone_band[0] < tone_band[1] <= evaluation_band[1]
        ):
            raise ValueError("Tone requires positive reference RMS and a search band inside the evaluation band")

    reference = _read_capture(manifest.parent, spec["reference"], count)
    candidate = _read_capture(manifest.parent, spec["candidate"], count)
    clock = _clock_report(reference, candidate, fs)
    valid = np.isfinite(reference.acceleration) & np.isfinite(candidate.acceleration)
    blocks = count // segment
    complete = valid[:blocks * segment].reshape(blocks, segment).all(axis=1)
    report = {
        "schema_version": 1, "capture_id": spec["capture_id"], "session_id": spec["session_id"],
        "source_kind": source, "start_utc": spec["start_utc"],
        "fs_hz": fs, "segment_samples": segment,
        "manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "input_sha256": {role: spec[role]["sha256"] for role in ("reference", "candidate")},
        "expected_samples_per_instrument": count,
        "reference": _capture_counts(reference), "candidate": _capture_counts(candidate),
        "valid_paired_samples": int(valid.sum()), "scheduled_blocks": blocks,
        "complete_paired_blocks": int(complete.sum()), "tail_samples_outside_blocks": count % segment,
        "timing": clock,
    }
    if not clock["supported"] or complete.sum() < MIN_BLOCKS:
        report["spectrum"] = {"status": "unavailable", "reason": (
            "Sample times exceed support or have no overlap" if not clock["supported"]
            else f"Fewer than {MIN_BLOCKS} complete paired blocks"
        )}
        return report

    x, y = (c.acceleration[:blocks * segment].reshape(blocks, segment)[complete] for c in (reference, candidate))
    options = {"fs": fs, "window": "hann", "nperseg": segment, "noverlap": 0, "detrend": "constant"}
    frequency, reference_psd = signal.welch(x, **options)
    _, candidate_psd = signal.welch(y, **options)
    _, difference_psd = signal.welch(y - x, **options)
    _, cross = signal.csd(x, y, **options)
    a, b, d, cross = (s.mean(axis=0) for s in (reference_psd, candidate_psd, difference_psd, cross))
    df = fs / segment
    band = _band_indices(frequency, evaluation_band, minimum=2)
    report["spectrum"] = {
        "status": "available", "bin_hz": df, "evaluation_band_hz": evaluation_band,
        "reference_band_rms_m_s2": float(np.sqrt(a[band].sum() * df)),
        "candidate_band_rms_m_s2": float(np.sqrt(b[band].sum() * df)),
        "paired_difference_band_rms_m_s2": float(np.sqrt(d[band].sum() * df)),
    }
    if tone_band is not None:
        report["tone"] = _tone_comparison(frequency, a, b, cross, tone_band, minimum_rms, df)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, help="Write a new JSON report instead of standard output")
    args = parser.parse_args()
    try:
        payload = json.dumps(compare(args.manifest), indent=2, allow_nan=False) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(payload)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        parser.exit(2, f"Bench comparison failed: {exc}\n")


if __name__ == "__main__":
    main()
