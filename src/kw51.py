"""Read and audit the published KW51 v1.0 tracked-modal archive."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile

import numpy as np
from scipy.io import loadmat


ARCHIVE_NAME = "trackedmodes.zip"
ARCHIVE_MEMBER = "trackedmodes/trackedmodes.mat"
ARCHIVE_SHA256 = "a379b5ed9836f0250ba126fed7bb2742a1e4e2ea28e11073f43c140f157912b0"
ENVIRONMENT = {
    "tBD31A": "degC",
    "rhBD31A": "%",
    "tVL": "degC",
    "rhVL": "%",
    "vpVL": "Pa",
    "grVL": "W/m²",
    "drVL": "W/m²",
    "dnrVL": "W/m²",
    "raVL": "mm",
    "wsVL": "m/s",
    "wdVL": "deg from North",
}
CHANNELS = (
    "aBD11Az", "aBD17Ay", "aBD17Az", "aBD17Cz", "aBD23Ay", "aBD23Az",
    "aAR0910Ay", "aAR0910Cy", "aAR1516Ay", "aAR1516Cy", "aAR2122Ay", "aAR2122Cy",
)
TEMPERATURES = ("tBD31A", "tVL")
RETROFIT_START_DAY = np.datetime64("2019-05-15", "D")
RETROFIT_END_DAY = np.datetime64("2019-09-27", "D")


@dataclass(frozen=True)
class TrackedModes:
    """Published hourly features. The archive clock is preserved without a timezone shift."""

    hours: np.ndarray
    frequency_hz: np.ndarray
    environment: np.ndarray
    mode_shapes: np.ndarray
    damping_as_published: np.ndarray


def _archive_hours(serial_days: np.ndarray) -> np.ndarray:
    days = np.asarray(serial_days)
    if (
        days.ndim != 1 or not days.size or days.dtype.kind not in "fiu"
        or not np.isfinite(days).all()
    ):
        raise ValueError("modes.sdn must be a finite vector")
    # MATLAB datenum 719529 is 1970-01-01. Round away floating-point noise
    # around exact hour boundaries rather than truncating to the previous hour.
    hours = (days - 719529.0) * 24.0
    rounded = np.rint(hours)
    if np.any(np.abs(hours - rounded) > 1e-6):
        raise ValueError("modes.sdn includes a non-hourly timestamp")
    if np.any(np.diff(rounded) != 1):
        raise ValueError("modes.sdn must be sorted with one row per consecutive hour")
    return rounded.astype("datetime64[h]")


def _parse_modes(modes: dict) -> TrackedModes:
    if tuple(modes["labels_env"]) != tuple(ENVIRONMENT):
        raise ValueError("Unexpected KW51 environmental labels or column order")
    if tuple(modes["labels_m"]) != CHANNELS:
        raise ValueError("Unexpected KW51 mode-shape channel labels or order")
    hours = _archive_hours(modes["sdn"])
    count = len(hours)
    fields = {
        "f": ((count, 14), "f"),
        "xi": ((count, 14), "f"),
        "env": ((count, len(ENVIRONMENT)), "f"),
        "m": ((count, 14, len(CHANNELS)), "fc"),
    }
    arrays = {}
    for field, (shape, kinds) in fields.items():
        values = np.asarray(modes[field])
        if values.shape != shape or values.dtype.kind not in kinds or np.isinf(values).any():
            raise ValueError(f"Unexpected shape, type or infinite value in modes.{field}")
        arrays[field] = values
    frequency = arrays["f"]
    if np.any(frequency[np.isfinite(frequency)] <= 0.0):
        raise ValueError("Identified frequencies must be positive")
    if not np.array_equal(np.isnan(frequency), np.isnan(arrays["xi"])):
        raise ValueError("Frequency and damping availability differ")
    if np.any(np.isfinite(arrays["m"]).any(axis=2) & np.isnan(frequency)):
        raise ValueError("Mode-shape values exist for an unidentified frequency")
    return TrackedModes(hours, frequency, arrays["env"], arrays["m"], arrays["xi"])


def load_tracked_modes(archive: Path) -> TrackedModes:
    """Verify and parse the exact Zenodo release without extracting ZIP members."""
    raw_archive = archive.read_bytes()
    if hashlib.sha256(raw_archive).hexdigest() != ARCHIVE_SHA256:
        raise ValueError(f"SHA-256 mismatch for {archive}. Use KW51 v1.0, Zenodo record 3745914.")
    with ZipFile(BytesIO(raw_archive)) as zipped:
        payload = zipped.read(ARCHIVE_MEMBER)
    loaded = loadmat(BytesIO(payload), variable_names=["modes"], simplify_cells=True)
    return _parse_modes(loaded["modes"])


def period_masks(hours: np.ndarray) -> dict[str, np.ndarray]:
    """Use the published date labels and hold out both undated-time boundaries."""
    days = hours.astype("datetime64[D]")
    return {
        "pre_retrofit": days < RETROFIT_START_DAY,
        "retrofit": (days > RETROFIT_START_DAY) & (days < RETROFIT_END_DAY),
        "post_retrofit": days > RETROFIT_END_DAY,
        "boundary_excluded": (days == RETROFIT_START_DAY) | (days == RETROFIT_END_DAY),
    }


def _bounds(hours: np.ndarray) -> list[str] | None:
    return [str(hours[0]), str(hours[-1])] if hours.size else None


def audit(data: TrackedModes) -> dict:
    """Count coverage against scheduled hours, retaining published missing values."""
    output = {
        "source": "https://zenodo.org/records/3745914",
        "source_sha256": ARCHIVE_SHA256,
        "archive_clock": "MATLAB serial days, preserved on the published hourly grid",
        "hourly_slots": len(data.hours),
        "first_and_last_hour": _bounds(data.hours),
        "mode_ids": list(range(1, data.frequency_hz.shape[1] + 1)),
        "environment_units": ENVIRONMENT,
        "mode_shape_channels": {},
        "periods": {},
    }
    frequency_available = np.isfinite(data.frequency_hz)
    mode_shape_available = np.isfinite(data.mode_shapes)
    for index, name in enumerate(CHANNELS):
        has_component = mode_shape_available[:, :, index].any(axis=1)
        output["mode_shape_channels"][name] = {
            "first_and_last_available_hour": _bounds(data.hours[has_component]),
            "hours_with_any_finite_component": int(has_component.sum()),
        }
    for name, mask in period_masks(data.hours).items():
        available = frequency_available[mask]
        environment = data.environment[mask]
        audited = {
            "first_and_last_hour": _bounds(data.hours[mask]),
            "slots": int(mask.sum()),
            "without_any_frequency": int((~available.any(axis=1)).sum()),
            "available_frequencies_by_mode": available.sum(axis=0).tolist(),
            "available_environment_by_label": dict(
                zip(ENVIRONMENT, np.isfinite(environment).sum(axis=0).tolist(), strict=True)
            ),
            "temperature_coverage": {},
        }
        for label in TEMPERATURES:
            column = environment[:, tuple(ENVIRONMENT).index(label)]
            finite = np.isfinite(column)
            audited["temperature_coverage"][label] = {
                "range_degC": [float(column[finite].min()), float(column[finite].max())] if finite.any() else None,
                "joint_hours_by_mode": available[finite].sum(axis=0).tolist(),
                "hours_with_no_temperature": int((~finite).sum()),
            }
        output["periods"][name] = audited
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path, help="Original Zenodo trackedmodes.zip")
    parser.add_argument("--output", type=Path, help="Write audit JSON here instead of standard output")
    args = parser.parse_args()
    try:
        result = audit(load_tracked_modes(args.archive))
        payload = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.output is None:
            print(payload, end="")
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload, encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, f"KW51 audit failed: {exc}\n")


if __name__ == "__main__":
    main()
