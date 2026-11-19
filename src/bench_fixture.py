"""Write a synthetic two-instrument bench fixture for checking the comparison CLI."""

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

from .bench_validation import FIELDS


def write_fixture(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=False)
    fs, segment = 100, 2048
    samples = 8 * segment
    time = np.arange(samples) / fs
    angle = 2 * np.pi * 3.125 * time
    reference = 0.008 * np.sin(angle)
    candidate = 0.008 * 1.04 * np.sin(angle - np.deg2rad(6))
    candidate += np.random.default_rng(202612).normal(0, 1e-5, samples)
    spec = {
        "schema_version": 1,
        "source_kind": "synthetic_fixture",
        "capture_id": "synthetic-tone-01",
        "session_id": "synthetic-session-01",
        "mounting": "Simulated mounting for one signed axis",
        "shared_time_reference": "Simulated trigger and 0.5 ms candidate timestamp offset",
        "start_utc": "2026-01-01T00:00:00Z",
        "fs_hz": fs,
        "expected_samples": samples,
        "segment_samples": segment,
        "evaluation_band_hz": [1, 8],
        "tone": {"search_band_hz": [2.8, 3.45], "minimum_reference_rms_m_s2": 0.001},
    }
    for role, values, offset in (("reference", reference, 0), ("candidate", candidate, 0.0005)):
        path = directory / f"{role}.csv"
        with path.open("x", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, lineterminator="\n")
            writer.writerow(FIELDS)
            writer.writerows((i, stamp, value, "valid") for i, (stamp, value) in enumerate(zip(time + offset, values)))
        spec[role] = {
            "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "axis": "+Z", "instrument": f"synthetic-{role}",
        }
    spec["reference"]["calibration_record"] = "Synthetic amplitude, no instrument calibration"
    spec["candidate"]["firmware_and_configuration"] = "Synthetic fixture generator"
    manifest = directory / "manifest.json"
    manifest.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="New output directory")
    args = parser.parse_args()
    try:
        print(write_fixture(args.directory))
    except OSError as exc:
        parser.exit(2, f"Bench fixture generation failed: {exc}\n")


if __name__ == "__main__":
    main()
