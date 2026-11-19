"""Shared descriptive features; dominant spectral peaks are not identified modes."""
import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import kurtosis, skew


class FeatureExtractor:
    """Nine legacy-compatible features, in a fixed column order."""

    def extract(self, X: np.ndarray, fs: float = 100) -> pd.DataFrame:
        X = np.asarray(X, dtype=float)
        if X.ndim != 2 or X.shape[1] < 4 or not np.isfinite(X).all():
            raise ValueError("Expected finite [windows, samples] with at least four samples")
        if not np.isfinite(fs) or fs <= 0:
            raise ValueError("Sampling rate must be positive and finite")
        rows = []
        for values in X:
            f, psd = signal.welch(values, fs=fs, nperseg=min(256, len(values)))
            rms = np.sqrt(np.mean(values ** 2))
            variable = np.std(values) > 0
            rows.append({
                'mean': np.mean(values), 'std_dev': np.std(values), 'rms': rms,
                'peak': np.max(np.abs(values)),
                'skewness': skew(values) if variable else 0.0,
                'kurtosis': kurtosis(values) if variable else 0.0,
                'crest_factor': np.max(np.abs(values)) / (rms + 1e-9),
                'dominant_freq': f[np.argmax(psd)],
                'spectral_centroid': np.sum(f * psd) / (np.sum(psd) + 1e-9),
            })
        return pd.DataFrame(rows)

