import csv
import hashlib
import json

import pytest

from src.bench_fixture import write_fixture
from src.bench_validation import compare


def _rewrite_capture(manifest, role, edit_rows):
    spec = json.loads(manifest.read_text())
    path = manifest.parent / spec[role]["file"]
    with path.open(newline="") as file:
        header, *rows = csv.reader(file)
    with path.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(edit_rows(rows))
    spec[role]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(spec))


def test_compare_recovers_known_gain_phase_and_frequency(tmp_path):
    manifest = write_fixture(tmp_path / "fixture")
    result = compare(manifest)
    assert result["source_kind"] == "synthetic_fixture"
    assert result["complete_paired_blocks"] == 8
    assert result["timing"]["relative_max_abs_ms"] == pytest.approx(0.5)
    assert result["spectrum"]["reference_band_rms_m_s2"] == pytest.approx(0.008 / 2**0.5)
    tone = result["tone"]
    assert tone["status"] == "meets_pilot_targets"
    assert tone["reference_peak_hz"] == tone["candidate_peak_hz"] == 3.125
    assert tone["gain_candidate_over_reference"] == pytest.approx(1.04, abs=0.001)
    assert tone["candidate_phase_relative_to_reference_deg"] == pytest.approx(-6, abs=0.02)
    assert tone["coherence"] > 0.999


def test_clock_skew_blocks_phase_and_spectra(tmp_path):
    manifest = write_fixture(tmp_path / "fixture")

    def delay(rows):
        for index, stamp, value, quality in rows:
            yield index, float(stamp) + 0.003, value, quality

    _rewrite_capture(manifest, "candidate", delay)
    result = compare(manifest)
    assert result["timing"]["relative_max_abs_ms"] == pytest.approx(3.5)
    assert result["valid_paired_samples"] == result["expected_samples_per_instrument"]
    assert result["spectrum"]["status"] == "unavailable"
    assert "tone" not in result


@pytest.mark.parametrize("clip_extra_block", [False, True])
def test_missing_endpoints_and_clipping_keep_scheduled_denominator(tmp_path, clip_extra_block):
    manifest = write_fixture(tmp_path / "fixture")

    def lose_samples(rows):
        if clip_extra_block:
            rows[2048][3] = "clipped"
        return rows[1:-1]

    _rewrite_capture(manifest, "candidate", lose_samples)
    result = compare(manifest)
    assert result["scheduled_blocks"] == 8
    assert result["candidate"]["missing_slots"] == 2
    assert result["candidate"]["clipped"] == int(clip_extra_block)
    assert result["valid_paired_samples"] == 8 * 2048 - 2 - int(clip_extra_block)
    assert result["complete_paired_blocks"] == 6 - int(clip_extra_block)
    assert result["spectrum"]["status"] == ("unavailable" if clip_extra_block else "available")


def test_weak_reference_abstains_from_tone_comparison(tmp_path):
    manifest = write_fixture(tmp_path / "fixture")

    def attenuate(rows):
        for index, stamp, value, quality in rows:
            yield index, stamp, float(value) / 100, quality

    _rewrite_capture(manifest, "reference", attenuate)
    result = compare(manifest)
    assert result["spectrum"]["status"] == "available"
    assert result["tone"]["status"] == "unavailable"


def test_clear_tone_can_miss_gain_target(tmp_path):
    manifest = write_fixture(tmp_path / "fixture")

    def attenuate(rows):
        for index, stamp, value, quality in rows:
            yield index, stamp, float(value) * 0.7, quality

    _rewrite_capture(manifest, "candidate", attenuate)
    tone = compare(manifest)["tone"]
    assert tone["status"] == "misses_pilot_targets"
    assert not tone["checks"]["gain_within_10_percent"]
    assert tone["checks"]["coherence_at_least_0_95"]


def test_rejects_modified_capture(tmp_path):
    manifest = write_fixture(tmp_path / "fixture")
    with (manifest.parent / "candidate.csv").open("a") as capture:
        capture.write("\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        compare(manifest)
