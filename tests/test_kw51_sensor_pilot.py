"""Checks for the raw clock, input corruption and calibration boundaries."""

from hashlib import sha256
from io import BytesIO
from zipfile import ZipFile

import numpy as np
import pytest
from scipy.io import savemat

from src import kw51_sensor_pilot as pilot
from src.kw51_fetch_raw import _select


def test_choose_first_available_capture_in_scheduled_hour():
    from datetime import datetime

    content = BytesIO()
    with ZipFile(content, "w") as archive:
        for name in ("20190401_001101", "20190401_000954", "20190401_010000"):
            archive.writestr(f"ambient_201904/ambient_{name}.mat", "")
    with ZipFile(content) as archive:
        assert _select(archive, datetime(2019, 4, 1)).endswith("_000954.mat")
        assert _select(archive, datetime(2019, 4, 1, 12)) is None


def test_mat_reader_checks_shared_clock_and_checksum(tmp_path, monkeypatch):
    rate = 64.0
    monkeypatch.setattr(pilot, "SAMPLE_RATE", rate)
    path = tmp_path / "ambient_20190401_000000.mat"
    clock = 737516.0 + np.arange(int(rate * 122)) / rate / 86400
    data = np.tile(np.sin(np.arange(len(clock)) / rate)[:, None], (1, 6))

    def save():
        savemat(path, {"predat_a": {
            "sdn": clock, "tdata": data, "labels": np.array(pilot.DECK, dtype=object), "fs": rate,
        }})
        return {
            "scheduled_hour_utc": "2019-04-01T00:00:00Z", "period": "fit", "status": "downloaded",
            "file": path.name, "sha256": sha256(path.read_bytes()).hexdigest(),
        }

    row = save()
    clean = pilot.read_record(row, tmp_path)
    assert clean.samples.shape == (6, 484)
    assert clean.acquired_at.isoformat() == "2019-04-01T00:00:00+00:00"
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        pilot.read_record({**row, "sha256": "0" * 64}, tmp_path)
    clock[100] = clock[99]
    with pytest.raises(ValueError, match="common time base"):
        pilot.read_record(save(), tmp_path)


def test_noise_pairing_crop_bias_and_burst_do_not_mutate_source():
    size = int(120 * pilot.SAMPLE_RATE / pilot.DECIMATION)
    samples = np.tile(np.arange(size + 8, dtype=float), (6, 1))
    original = samples.copy()
    full, _ = pilot.scenario_data(samples, pilot.ALL_CHANNELS, "noise_5db", 0)
    reduced, _ = pilot.scenario_data(samples, (1, 3), "noise_5db", 0)
    np.testing.assert_array_equal(full[[1, 3]], reduced)
    # The engineered pair (1, 5) must receive different delays.
    shifted, _ = pilot.scenario_data(samples, (1, 5), "timing", 0)
    np.testing.assert_array_equal(shifted[0], samples[1, 4:size+4])
    np.testing.assert_array_equal(shifted[1], samples[5, 1:size+1])
    clean, _ = pilot.scenario_data(samples, (1, 3), "clean", 0)
    biased, _ = pilot.scenario_data(samples, (1, 3), "dc_bias", 0)
    np.testing.assert_allclose(biased - clean, -0.002)
    lost, quality = pilot.scenario_data(samples, (1, 3), "burst", 0)
    assert quality == ("missing", "valid")
    assert np.isnan(lost[0]).sum() == round(2 * pilot.SAMPLE_RATE / pilot.DECIMATION)
    np.testing.assert_array_equal(samples, original)


def test_change_threshold_ignores_test_rows_and_incomplete_panel_abstains():
    records = [pilot.Record("", "fit")] * 8 + [pilot.Record("", "calibration")] * 8
    records += [pilot.Record("", "reference_test")] * 2
    frequencies = np.full((18, 2), 2.0)
    frequencies[15, 0] = 2.03
    model = pilot._fit_change_score(frequencies, records, [0, 1])
    assert model["fit"] == model["calibration"] == 8
    frequencies[16:] = [[3.0, 3.0], [np.nan, 3.0]]
    assert model == pilot._fit_change_score(frequencies, records, [0, 1])
    flags = pilot._flags(frequencies, [0, 1], model)
    assert flags[15] == 0  # Equality is not an exceedance.
    assert flags[16] == 1 and np.isnan(flags[17])
