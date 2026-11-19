"""Explicit boundary around the original synthetic classifier."""
from pathlib import Path
import hashlib
import json
import pickle

LEGACY_SOURCE = 'legacy_synthetic'
ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / 'artifacts/shm_deployment_package_enhanced.pkl'


def require_legacy_source(source_kind: str) -> None:
    if source_kind != LEGACY_SOURCE:
        raise ValueError('Legacy classifier accepts only legacy_synthetic data; never beam or measured data')


def load_original_package(source_kind: str):
    require_legacy_source(source_kind)
    manifest = json.loads((ROOT / 'review/legacy_manifest.json').read_text(encoding='utf-8'))
    expected = manifest['sha256']['artifacts/shm_deployment_package_enhanced.pkl']
    if hashlib.sha256(MODEL.read_bytes()).hexdigest() != expected:
        raise ValueError('Original legacy model checksum differs from the recorded artifact')
    # Only the user-supplied, checksum-verified original artifact is loaded here.
    with MODEL.open('rb') as stream:
        return pickle.load(stream)


def predict_legacy(package, samples, *, source_kind: str):
    require_legacy_source(source_kind)
    from ..features import FeatureExtractor
    features = FeatureExtractor().extract(samples)
    selected = package['feature_selector'].transform(package['scaler'].transform(features))
    return features, package['model'].predict_proba(selected)

