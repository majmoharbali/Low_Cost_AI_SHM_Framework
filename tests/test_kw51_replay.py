"""Exercise split integrity, frozen calibration and scheduled-hour persistence."""

from copy import deepcopy

import numpy as np
import pytest

from src.environment_baseline import fit_model
from src.kw51 import TrackedModes
from src.kw51_replay import alarm_trace, evaluate, freeze, partitions


@pytest.fixture
def modal_series():
    hours = np.arange("2018-10-01T00", "2019-10-03T00", dtype="datetime64[h]")
    sequence = np.arange(len(hours))
    air = 9 + 5 * np.sin(sequence * 2 * np.pi / 24)
    env = np.full((len(hours), 11), np.nan)
    env[:, 0] = air + np.cos(sequence * 2 * np.pi / 24)
    env[:, 2] = air
    rng = np.random.default_rng(42)
    frequency = np.full((len(hours), 14), np.nan)
    frequency[:, :2] = (
        [2, 4] + 0.003 * air[:, None] + rng.normal(0, 0.003, (len(hours), 2))
    )
    frequency[1::11, 0] = np.nan
    frequency[4::12, 1] = np.nan
    return TrackedModes(hours, frequency, env, np.empty(0), np.empty(0))


def test_split_uses_clock_and_excludes_boundaries(modal_series):
    hours = modal_series.hours
    split = partitions(hours)
    assert len(np.unique(np.concatenate(list(split.values())))) == len(hours)
    assert len(split["fit_purge"]) == len(split["calibration_purge"]) == 24
    assert hours[split["calibration"][0]] - hours[split["fit"][-1]] == np.timedelta64(25, "h")
    assert hours[split["reference_test"][0]] - hours[split["calibration"][-1]] == np.timedelta64(25, "h")
    assert hours[split["retrofit"][0]] == np.datetime64("2019-05-16T00")
    assert hours[split["post_retrofit"][0]] == np.datetime64("2019-09-28T00")
    assert len(split["boundary_excluded"]) == 48


def test_future_changes_do_not_influence_frozen_parameters(modal_series):
    frozen = freeze(modal_series)
    assert frozen["mode_ids"] == [1, 2]
    corrupt = deepcopy(modal_series)
    after_calibration = partitions(corrupt.hours)["calibration"][-1] + 1
    corrupt.frequency_hz[after_calibration:] = 100.0
    corrupt.environment[after_calibration:] = -99.0
    assert freeze(corrupt) == frozen
    snapshot = deepcopy(frozen)
    results = evaluate(corrupt, frozen)
    assert frozen == snapshot
    for period in results["periods"].values():
        assert period["models"]["linear"]["operating"]["scored"] == 0
        assert period["models"]["constant"]["operating"]["coverage"] == 1.0
        assert period["models"]["constant"]["common"]["scored"] == 0


def test_calibration_shift_changes_cutoffs_without_refitting(modal_series):
    initial = freeze(modal_series)
    cal = partitions(modal_series.hours)["calibration"]
    modal_series.frequency_hz[cal, :2] += 1.0
    shifted = freeze(modal_series)
    for name, result in initial["primary_models"].items():
        assert shifted["primary_models"][name]["model"] == result["model"]
        assert shifted["primary_models"][name]["threshold"] > result["threshold"]
        assert shifted["primary_models"][name]["calibration_hours"] == result["calibration_hours"]
    assert shifted["spline_tuning"] == initial["spline_tuning"]


def test_two_consecutive_exceedances_reset_on_missing_values_and_time_gaps():
    hours = np.datetime64("2019-01-01T00") + np.array([0, 1, 2, 3, 4, 6, 7, 8, 9, 10])
    scores = np.array([9.0, 9.0, 9.0, np.nan, 9.0, 9.0, 9.0, 4.0, 9.0, 9.0])
    exceed, persisted, onsets = alarm_trace(hours, scores, threshold=4.0)
    assert not exceed[7]
    assert np.flatnonzero(persisted).tolist() == [1, 2, 6, 9]
    assert np.flatnonzero(onsets).tolist() == [1, 6, 9]


def test_temperature_conditioning_fits_signal_and_abstains_beyond_support():
    rng = np.random.default_rng(4)
    temp = np.linspace(0, 25, 301)
    frequency = (2 + temp * 0.04 + rng.normal(0, 0.002, len(temp)))[:, None]
    linear = fit_model("linear", temp, frequency)
    constant = fit_model("constant", temp, frequency)
    assert np.std(linear.residuals(temp, frequency)) < 0.003
    assert np.std(constant.residuals(temp, frequency)) > 0.25
    assert np.isfinite(linear.scores(np.array([0., 25.]), np.array([[2.], [3.]]))).all()
    cases = linear.scores(np.array([-0.01, np.nan, 5.]), np.array([[2.], [2.], [np.nan]]))
    assert np.isnan(cases).all()
