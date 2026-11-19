"""Frequency residual models fitted to reference modal observations."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import BSpline
from scipy.linalg import solve_triangular

METHODS = ("constant", "linear", "spline")
PENALTIES = (0.00001, 0.001, 0.1, 1.0)


def support(temperature: np.ndarray, bounds: tuple[float, float]) -> np.ndarray:
    return np.isfinite(temperature) & (temperature >= bounds[0]) & (temperature <= bounds[1])


@dataclass(frozen=True)
class ResidualModel:
    method: str
    center: float
    scale: float
    bounds: tuple[float, float]
    knots: list[float]
    coefficients: list[list[float]]
    cholesky: list[list[float]]

    def residuals(self, temperature: np.ndarray, frequency: np.ndarray) -> np.ndarray:
        design = _design(self.method, temperature, self.center, self.scale, self.knots)
        return frequency - design @ np.asarray(self.coefficients)

    def scores(self, temperature: np.ndarray, frequency: np.ndarray) -> np.ndarray:
        """Squared Mahalanobis residual scores; unavailable rows remain NaN."""
        valid = np.isfinite(frequency).all(axis=1)
        if self.method != "constant":
            valid &= support(temperature, self.bounds)
        scores = np.full(len(frequency), np.nan)
        if valid.any():
            residuals = self.residuals(temperature[valid], frequency[valid])
            whitened = solve_triangular(np.asarray(self.cholesky), residuals.T, lower=True)
            scores[valid] = np.square(whitened).sum(axis=0)
        return scores


def _design(method, temperature, center, scale, knots):
    if method == "constant":
        return np.ones((len(temperature), 1))
    if method == "linear":
        return np.column_stack((np.ones(len(temperature)), (temperature - center) / scale))
    if method == "spline":
        return BSpline.design_matrix(temperature, knots, k=3).toarray()
    raise ValueError(f"Unknown model method {method!r}")


def fit_model(method, temperature, frequency, *, penalty=None) -> ResidualModel:
    """Use a shared complete reference training sample for means and covariance."""
    if (
        temperature.ndim != 1 or frequency.ndim != 2 or not frequency.shape[1]
        or len(frequency) != len(temperature) or len(frequency) <= frequency.shape[1]
        or not np.isfinite(temperature).all() or not np.isfinite(frequency).all()
    ):
        raise ValueError("Expected aligned complete temperature and modal fitting rows")
    center = float(np.mean(temperature))
    scale = float(np.std(temperature))
    if scale <= 0:
        raise ValueError("Fitting temperature has no variation")
    bounds = (float(temperature.min()), float(temperature.max()))
    knots = []
    if method == "spline":
        if penalty is None or penalty <= 0:
            raise ValueError("A positive spline penalty is required")
        interior = np.quantile(temperature, [0.25, 0.5, 0.75])
        if np.any(np.diff([bounds[0], *interior, bounds[1]]) <= 0):
            raise ValueError("Fitting temperature quartiles must define distinct spline knots")
        knots = [bounds[0]] * 4 + interior.tolist() + [bounds[1]] * 4
    design = _design(method, temperature, center, scale, knots)
    if method == "spline":
        difference = np.diff(np.eye(design.shape[1]), n=2, axis=0)
        augmented = np.vstack((design, np.sqrt(len(design) * penalty) * difference))
        response = np.vstack((frequency, np.zeros((len(difference), frequency.shape[1]))))
        coefficients = np.linalg.lstsq(augmented, response, rcond=None)[0]
    else:
        coefficients = np.linalg.lstsq(design, frequency, rcond=None)[0]
    residuals = frequency - design @ coefficients
    covariance = np.atleast_2d(np.cov(residuals, rowvar=False))
    diagonal = np.diag(covariance)
    if np.any(diagonal <= np.finfo(float).eps):
        raise ValueError("A fitted mode has effectively zero residual variance")
    cholesky = np.linalg.cholesky(0.95 * covariance + 0.05 * np.diag(diagonal))
    return ResidualModel(method, center, scale, bounds, knots, coefficients.tolist(), cholesky.tolist())


def spline_penalty(temperature, frequency, *, purge_hours):
    """Tune only within the scheduled fitting block using expanding validation."""
    complete = np.isfinite(frequency).all(axis=1) & np.isfinite(temperature)
    cuts = [int(len(temperature) * fraction) for fraction in (0.4, 0.6, 0.8)] + [len(temperature)]
    errors = {penalty: [] for penalty in PENALTIES}
    fold_rows = []
    indices = np.arange(len(temperature))
    for start, end in zip(cuts[:-1], cuts[1:], strict=True):
        train = complete & (indices < start - purge_hours)
        if train.sum() < 200:
            raise ValueError("Spline tuning needs at least 200 common training hours per fold")
        t_train, f_train = temperature[train], frequency[train]
        valid = complete & (indices >= start) & (indices < end)
        valid &= support(temperature, (t_train.min(), t_train.max()))
        if valid.sum() < 72:
            raise ValueError("Spline tuning needs at least 72 supported validation hours per fold")
        scale = np.std(f_train, axis=0)
        if np.any(scale <= 0):
            raise ValueError("A tuning fold has a constant modal frequency")
        fold_rows.append({"fit": int(train.sum()), "validation": int(valid.sum())})
        for penalty in PENALTIES:
            model = fit_model("spline", t_train, f_train, penalty=penalty)
            residuals = model.residuals(temperature[valid], frequency[valid])
            errors[penalty].append(float(np.mean(np.square(residuals / scale))))
    means = {penalty: float(np.mean(values)) for penalty, values in errors.items()}
    best = min(PENALTIES, key=lambda penalty: (means[penalty], -penalty))
    return best, {"fold_rows": fold_rows, "mean_standardised_mse": means}
