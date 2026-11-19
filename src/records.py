"""Signal provenance and fail-closed availability; no fitted detector in milestone 1."""
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np


@dataclass(frozen=True)
class SignalWindow:
    samples: np.ndarray
    fs_hz: float
    sensor_ids: tuple[str, ...]
    window_id: str
    acquired_at: datetime
    source_kind: str
    units: str = 'm/s^2'
    quality: tuple[str, ...] = ()

    def __post_init__(self):
        data = np.array(self.samples, dtype=float, copy=True)
        ids = tuple(self.sensor_ids)
        if data.ndim != 2 or not data.shape[0] or data.shape[1] < 2:
            raise ValueError('SignalWindow needs [channels, samples], with at least two samples')
        if len(ids) != data.shape[0] or len(set(ids)) != len(ids) or any(not isinstance(s, str) or not s for s in ids):
            raise ValueError('Provide a unique non-empty ID for every channel')
        if not np.isfinite(self.fs_hz) or self.fs_hz <= 0:
            raise ValueError('Sampling rate must be positive and finite')
        if self.acquired_at.tzinfo is None or self.acquired_at.utcoffset() is None:
            raise ValueError('Acquisition time must be timezone-aware')
        if self.units != 'm/s^2':
            raise ValueError('Convert acceleration to m/s^2 explicitly before creating a research window')
        quality = tuple(self.quality) if self.quality else ('valid',)*len(ids)
        if len(quality) != len(ids) or any(q not in ('valid', 'missing', 'invalid') for q in quality):
            raise ValueError('Quality must mark each channel valid, missing or invalid')
        if not self.window_id or not self.source_kind:
            raise ValueError('Window ID and source provenance are required')
        data.setflags(write=False)
        object.__setattr__(self, 'samples', data)
        object.__setattr__(self, 'sensor_ids', ids)
        object.__setattr__(self, 'quality', quality)

    @property
    def end_at(self):
        return self.acquired_at + timedelta(seconds=(self.samples.shape[1]-1)/self.fs_hz)


@dataclass(frozen=True)
class DetectionResult:
    status: str
    coverage: float
    reason: str
    score: float | None = None
    threshold: float | None = None


def assess_availability(window: SignalWindow, *, now: datetime, max_age_s=20.0, required_ids=None):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Evaluation time must be timezone-aware')
    if not np.isfinite(max_age_s) or max_age_s < 0:
        raise ValueError('Maximum age must be finite and non-negative')
    required = tuple(window.sensor_ids if required_ids is None else required_ids)
    if not required or len(set(required)) != len(required):
        raise ValueError('A non-empty set of unique required sensor IDs is needed')
    valid = {s: q == 'valid' and np.isfinite(window.samples[i]).all()
             for i, (s, q) in enumerate(zip(window.sensor_ids, window.quality))}
    coverage = sum(valid.get(s, False) for s in required)/len(required)
    if coverage < 1:
        return DetectionResult('insufficient_data', coverage, 'Required channels are missing or invalid')
    age = (now-window.end_at).total_seconds()
    if age < 0:
        return DetectionResult('invalid_time', coverage, 'Window ends after evaluation time')
    if age > max_age_s:
        return DetectionResult('stale', coverage, 'Window exceeds the permitted age')
    return DetectionResult('not_fitted', coverage, 'No research detector has been fitted')
