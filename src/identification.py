"""Welch cross-spectral matrices and FDD with explicit verification-band QC.

Band and prominence settings are identification assumptions, not confidence levels.
Plain FDD supplies no damping estimate or damage probability.
"""
from dataclasses import dataclass

import numpy as np
from scipy import signal

from .records import SignalWindow, assess_availability


@dataclass
class SpectralEstimate:
    frequencies_hz: np.ndarray
    density: np.ndarray  # [frequency, channel, channel], (m/s^2)^2 / Hz
    singular_values: np.ndarray
    singular_vectors: np.ndarray
    resolution_hz: float


@dataclass
class ModeEstimate:
    band_hz: tuple[float, float]
    status: str
    frequency_hz: float | None = None
    shape: np.ndarray | None = None
    reason: str = ''


def welch_matrix(window: SignalWindow, *, nperseg=4096, overlap=.5):
    if any(q != 'valid' for q in window.quality) or not np.isfinite(window.samples).all():
        raise ValueError('Spectral estimation requires finite, valid synchronous channels')
    if not isinstance(nperseg, int) or not 8 <= nperseg <= window.samples.shape[1]:
        raise ValueError('nperseg must be an integer in [8, available sample count]')
    if not np.isfinite(overlap) or not 0 <= overlap < 1:
        raise ValueError('Overlap must be in [0, 1)')
    channels = window.samples.shape[0]
    density = np.empty((nperseg//2+1, channels, channels), dtype=complex)
    for i in range(channels):
        for j in range(i, channels):
            # scipy.csd(y, x) gives conj(Y)*X, matching S_ij=E[X_i conj(X_j)].
            frequencies, cross = signal.csd(window.samples[j], window.samples[i], fs=window.fs_hz,
                                           window='hann', nperseg=nperseg, noverlap=int(overlap*nperseg),
                                           detrend='constant', scaling='density')
            density[:, i, j] = cross
            density[:, j, i] = np.conj(cross)
    u, s, _ = np.linalg.svd(density, hermitian=True)
    return SpectralEstimate(frequencies, density, s, u, window.fs_hz/nperseg)


def identify_modes(window: SignalWindow, bands_hz, *, now, max_age_s=20.0, nperseg=4096,
                   relative_prominence=.1, minimum_relative_power=1e-4):
    bands = [tuple(float(x) for x in band) for band in bands_hz]
    if not bands or any(len(b) != 2 or not np.isfinite(b).all() or not 0 < b[0] < b[1] < window.fs_hz/2 for b in bands):
        raise ValueError('Mode bands must be finite positive intervals below Nyquist')
    if any(max(a[0], b[0]) <= min(a[1], b[1]) for i, a in enumerate(bands) for b in bands[i+1:]):
        raise ValueError('Mode bands must not overlap')
    if not 0 < relative_prominence <= 1 or not 0 < minimum_relative_power <= 1:
        raise ValueError('Power and prominence fractions must be in (0, 1]')
    availability = assess_availability(window, now=now, max_age_s=max_age_s)
    if availability.status != 'not_fitted':
        return [ModeEstimate(b, 'unavailable', reason=availability.reason) for b in bands]
    if window.samples.shape[1] < nperseg:
        return [ModeEstimate(b, 'unavailable', reason='Too few samples for configured spectral resolution') for b in bands]
    spectrum = welch_matrix(window, nperseg=nperseg)
    power = spectrum.singular_values[:, 0]
    global_peak = power.max()
    output = []
    for band in bands:
        bins = np.flatnonzero((spectrum.frequencies_hz >= band[0]) & (spectrum.frequencies_hz <= band[1]))
        if len(bins) < 3 or global_peak <= 0 or power[bins].max() < minimum_relative_power*global_peak:
            output.append(ModeEstimate(band, 'unavailable', reason='No observable spectral peak at the configured sensitivity'))
            continue
        peaks, _ = signal.find_peaks(power[bins], prominence=relative_prominence*power[bins].max())
        if not len(peaks):
            output.append(ModeEstimate(band, 'unavailable', reason='No interior peak; boundary peaks are not identified'))
            continue
        candidates = bins[peaks]
        candidates = candidates[np.argsort(power[candidates])[::-1]]
        if len(candidates) > 1 and power[candidates[1]] >= .8*power[candidates[0]]:
            output.append(ModeEstimate(band, 'ambiguous', reason='Competing peaks require narrower bands or a different identification method'))
            continue
        index = candidates[0]
        shape = spectrum.singular_vectors[index, :, 0].copy()
        anchor = np.argmax(abs(shape))
        shape *= np.exp(-1j*np.angle(shape[anchor]))
        output.append(ModeEstimate(band, 'identified', float(spectrum.frequencies_hz[index]), shape,
                                   'FDD peak within supplied band; not proof of a structural mode'))
    return output


def modal_assurance(a, b):
    a, b = np.asarray(a), np.asarray(b)
    denominator = np.vdot(a,a).real*np.vdot(b,b).real
    return float(abs(np.vdot(a,b))**2/denominator) if denominator > 0 else 0.0
