import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from src.features import FeatureExtractor
from src.legacy.access import load_original_package, predict_legacy


@pytest.mark.parametrize('module', ['src.main_simulation', 'src.train_model'])
def test_entrypoints_help_and_explicit_legacy_opt_in(module):
    root = Path(__file__).resolve().parents[1]
    help_run = subprocess.run([sys.executable, '-m', module, '--help'], cwd=root, capture_output=True, timeout=30)
    assert help_run.returncode == 0
    blocked = subprocess.run([sys.executable, '-m', module], cwd=root, capture_output=True, timeout=30)
    assert blocked.returncode == 2
    assert b'legacy' in blocked.stderr


def test_preserved_original_model():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'review/legacy_manifest.json').read_text())
    for path, expected in manifest['sha256'].items():
        if path.startswith('artifacts/'):
            assert hashlib.sha256((root / path).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('source', ['beam_verification', 'z24', 'kw51', 'measured', ''])
def test_legacy_boundary_rejects_new_sources_before_loading_or_prediction(source):
    with pytest.raises(ValueError, match='Legacy classifier'):
        load_original_package(source)
    with pytest.raises(ValueError, match='Legacy classifier'):
        predict_legacy(None, None, source_kind=source)


def test_shared_features_preserve_units_and_handle_zero_signal():
    t = np.arange(1000) / 100
    x = np.sin(2 * np.pi * 5 * t)
    frame = FeatureExtractor().extract(np.stack([x, 3*x, np.zeros_like(x)]))
    assert len(frame.columns) == 9
    assert frame.loc[1, 'rms'] == pytest.approx(3 * frame.loc[0, 'rms'])
    assert np.isfinite(frame.to_numpy()).all()
    assert frame.loc[0, 'dominant_freq'] == pytest.approx(5, abs=100/256)

