"""Small MATLAB fixtures exercise the KW51 import without needing a download."""

import hashlib
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pytest
from scipy.io import savemat

from src import kw51


@pytest.fixture
def archive(tmp_path, monkeypatch):
    def write(*, invalid_clock=False, swap_labels=False):
        # 2019-05-14 23:00 through 2019-05-16 00:00 on the archive clock.
        hours = np.arange(
            np.datetime64("2019-05-14T23"), np.datetime64("2019-05-16T01"),
            np.timedelta64(1, "h"),
        )
        serial = hours.astype(np.int64) / 24.0 + 719529.0
        if invalid_clock:
            serial[1] = serial[0]
        count = len(hours)
        frequencies = np.full((count, 14), np.nan)
        damping = frequencies.copy()
        shapes = np.full((count, 14, 12), np.nan + 0j)
        environment = np.full((count, 11), np.nan)
        frequencies[0, 3], damping[0, 3], shapes[0, 3, 0] = 2.4, 0.7, 1 + 0.1j
        environment[0, 2] = -2.0
        labels = list(kw51.ENVIRONMENT)
        if swap_labels:
            labels[0], labels[2] = labels[2], labels[0]
        member = BytesIO()
        savemat(member, {"modes": {
            "sdn": serial.reshape(-1, 1), "f": frequencies, "xi": damping,
            "m": shapes, "env": environment, "labels_env": np.array(labels, dtype=object),
            "labels_m": np.array(kw51.CHANNELS, dtype=object),
        }})
        path = tmp_path / "trackedmodes.zip"
        with ZipFile(path, "w") as zipped:
            zipped.writestr(kw51.ARCHIVE_MEMBER, member.getvalue())
        monkeypatch.setattr(kw51, "ARCHIVE_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
        return path

    return write


def test_audit_keeps_missing_hours_and_uses_the_archive_day(archive):
    data = kw51.load_tracked_modes(archive())
    summary = kw51.audit(data)
    assert summary["first_and_last_hour"] == ["2019-05-14T23", "2019-05-16T00"]
    assert summary["hourly_slots"] == 26
    before = summary["periods"]["pre_retrofit"]
    assert before["slots"] == 1
    assert before["available_frequencies_by_mode"][3] == 1
    assert before["temperature_coverage"]["tVL"]["joint_hours_by_mode"][3] == 1
    assert before["temperature_coverage"]["tBD31A"]["range_degC"] is None
    assert summary["periods"]["boundary_excluded"]["slots"] == 24
    assert summary["periods"]["retrofit"]["without_any_frequency"] == 1
    assert np.isnan(data.frequency_hz[1, 3])
    assert data.mode_shapes[0, 3, 0] == 1 + 0.1j


def test_rejects_modified_archive(archive):
    path = archive()
    path.write_bytes(path.read_bytes() + b"changed")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        kw51.load_tracked_modes(path)


@pytest.mark.parametrize(
    ("options", "error"), [
        ({"invalid_clock": True}, "one row per consecutive hour"),
        ({"swap_labels": True}, "environmental labels or column order"),
    ],
)
def test_refuses_clock_or_column_inconsistency(archive, options, error):
    with pytest.raises(ValueError, match=error):
        kw51.load_tracked_modes(archive(**options))
