"""Linear simply supported Euler–Bernoulli verification model in SI units.

Consistent FE mass, mass-normalised modal reduction and exact zero-order-hold
state propagation. This is not an identified bridge model or a safety check.
"""
from dataclasses import dataclass

import numpy as np
from scipy.linalg import eigh
from scipy.signal import cont2discrete


@dataclass(frozen=True)
class BeamConfig:
    length_m: float = 20.0
    width_m: float = 0.30
    height_m: float = 0.50
    young_pa: float = 30e9
    density_kg_m3: float = 2500.0
    elements: int = 20
    modes: int = 3
    damping_ratio: float = 0.02

    def __post_init__(self):
        for name in ('length_m', 'width_m', 'height_m', 'young_pa', 'density_kg_m3'):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f'{name} must be positive and finite')
        if not isinstance(self.elements, int) or self.elements < 2:
            raise ValueError('At least two elements are required')
        if not isinstance(self.modes, int) or not 1 <= self.modes <= 2*self.elements:
            raise ValueError('Retained modes must be in 1..2*elements')
        if not np.isfinite(self.damping_ratio) or not 0 <= self.damping_ratio < 1:
            raise ValueError('Underdamped modal damping must be in [0, 1)')


@dataclass
class BeamResponse:
    time_s: np.ndarray
    acceleration_m_s2: np.ndarray
    modal_displacement: np.ndarray
    modal_velocity: np.ndarray
    modal_acceleration: np.ndarray
    fs_hz: float
    sensor_locations_m: np.ndarray
    source_kind: str = 'beam_verification'


class LinearBeamSimulator:
    def __init__(self, config=None, *, uniform_reduction=0.0, element_reductions=None):
        self.config = config or BeamConfig()
        c = self.config
        if not np.isfinite(uniform_reduction) or not 0 <= uniform_reduction < 1:
            raise ValueError('Uniform stiffness reduction must be in [0, 1)')
        reduction = np.zeros(c.elements)
        for element, value in (element_reductions or {}).items():
            if not isinstance(element, int) or not 0 <= element < c.elements:
                raise ValueError('Invalid element index')
            if not np.isfinite(value) or not 0 <= value < 1:
                raise ValueError('Element stiffness reduction must be in [0, 1)')
            reduction[element] = value
        self.stiffness_factors = (1-uniform_reduction)*(1-reduction)
        self.mass, self.stiffness, self.free_dofs = self._assemble()
        eigenvalues, modes = eigh(self.stiffness, self.mass, subset_by_index=(0, c.modes-1))
        if np.any(eigenvalues <= 0):
            raise ValueError('The constrained model must have positive eigenvalues')
        self.omega_rad_s = np.sqrt(eigenvalues)
        self.frequencies_hz = self.omega_rad_s/(2*np.pi)
        self.modes = modes
        self.full_modes = np.zeros((2*(c.elements+1), c.modes))
        self.full_modes[self.free_dofs] = modes
        # Deterministic signs; output-only shape comparisons remain scale/sign invariant.
        for j in range(c.modes):
            if self.full_modes[np.argmax(abs(self.full_modes[::2, j]))*2, j] < 0:
                self.modes[:, j] *= -1
                self.full_modes[:, j] *= -1

    def _assemble(self):
        c = self.config
        h = c.length_m/c.elements
        area = c.width_m*c.height_m
        inertia = c.width_m*c.height_m**3/12
        k = c.young_pa*inertia/h**3*np.array([
            [12, 6*h, -12, 6*h], [6*h, 4*h*h, -6*h, 2*h*h],
            [-12, -6*h, 12, -6*h], [6*h, 2*h*h, -6*h, 4*h*h],
        ])
        m = c.density_kg_m3*area*h/420*np.array([
            [156, 22*h, 54, -13*h], [22*h, 4*h*h, 13*h, -3*h*h],
            [54, 13*h, 156, -22*h], [-13*h, -3*h*h, -22*h, 4*h*h],
        ])
        size = 2*(c.elements+1)
        M, K = np.zeros((size, size)), np.zeros((size, size))
        for e in range(c.elements):
            dofs = np.arange(2*e, 2*e+4)
            M[np.ix_(dofs, dofs)] += m
            K[np.ix_(dofs, dofs)] += self.stiffness_factors[e]*k
        free = np.setdiff1d(np.arange(size), [0, 2*c.elements])
        return M[np.ix_(free, free)], K[np.ix_(free, free)], free

    def analytical_frequencies_hz(self):
        """Healthy uniform-beam reference; not an analytical damaged-beam solution."""
        c = self.config
        inertia = c.width_m*c.height_m**3/12
        return np.arange(1, c.modes+1)**2*np.pi/(2*c.length_m**2)*np.sqrt(
            c.young_pa*inertia/(c.density_kg_m3*c.width_m*c.height_m))

    def sensor_mode_shapes(self, locations_m):
        """Cubic Hermite displacement interpolation, including non-nodal sensors."""
        x = np.asarray(locations_m, dtype=float)
        if x.ndim != 1 or not len(x) or not np.isfinite(x).all() or np.any((x < 0) | (x > self.config.length_m)):
            raise ValueError('Sensor locations must be finite and within the span')
        h = self.config.length_m/self.config.elements
        rows = []
        for location in x:
            e = min(int(location/h), self.config.elements-1)
            xi = (location-e*h)/h
            shape = np.array([1-3*xi**2+2*xi**3, h*(xi-2*xi**2+xi**3),
                              3*xi**2-2*xi**3, h*(-xi**2+xi**3)])
            rows.append(shape @ self.full_modes[2*e:2*e+4])
        return np.asarray(rows)

    def nodal_forces(self, samples, *, node_ids=(6,), std_n=100.0, seed=42):
        """Sampled independent nodal loads; std_n is not a continuous noise density."""
        if not isinstance(samples, int) or samples < 2 or not np.isfinite(std_n) or std_n < 0:
            raise ValueError('Need at least two samples and non-negative force standard deviation')
        ids = tuple(node_ids)
        if not ids or len(set(ids)) != len(ids) or any(not isinstance(i, int) or not 0 < i < self.config.elements for i in ids):
            raise ValueError('Loads require unique interior node indices')
        force = np.zeros((2*(self.config.elements+1), samples))
        force[np.array(ids)*2] = np.random.default_rng(seed).normal(0, std_n, (len(ids), samples))
        return force

    def simulate(self, force_n, *, fs_hz=100.0, sensor_locations_m=(2.0, 10.0, 18.0),
                 initial_modal_displacement=None, initial_modal_velocity=None, noise_std_m_s2=0.0, noise_seed=43):
        force = np.asarray(force_n, dtype=float)
        c = self.config
        if force.ndim != 2 or force.shape[0] != 2*(c.elements+1) or force.shape[1] < 2 or not np.isfinite(force).all():
            raise ValueError('Forces must be finite [full nodal DOFs, samples]')
        if np.any(force[1::2] != 0) or np.any(force[[0, 2*c.elements]] != 0):
            raise ValueError('Only interior nodal forces in N are supported; no moments or support loads')
        if not np.isfinite(fs_hz) or fs_hz <= 2*self.frequencies_hz.max():
            raise ValueError('Sampling rate must exceed twice the highest retained frequency')
        if not np.isfinite(noise_std_m_s2) or noise_std_m_s2 < 0:
            raise ValueError('Noise RMS must be finite and non-negative')
        sensors = np.asarray(sensor_locations_m, dtype=float)
        phi = self.sensor_mode_shapes(sensors)
        n = c.modes
        damping = 2*c.damping_ratio*self.omega_rad_s
        A = np.block([[np.zeros((n,n)), np.eye(n)], [-np.diag(self.omega_rad_s**2), -np.diag(damping)]])
        B = np.vstack([np.zeros((n,n)), np.eye(n)])
        Ad, Bd, _, _, _ = cont2discrete((A, B, np.eye(2*n), np.zeros((2*n,n))), 1/fs_hz)
        def initial(value):
            v = np.zeros(n) if value is None else np.asarray(value, dtype=float)
            if v.shape != (n,) or not np.isfinite(v).all():
                raise ValueError('Initial modal state must have one finite entry per retained mode')
            return v
        states = np.empty((2*n, force.shape[1]))
        states[:, 0] = np.r_[initial(initial_modal_displacement), initial(initial_modal_velocity)]
        modal_force = self.modes.T @ force[self.free_dofs]
        for k in range(force.shape[1]-1):
            states[:, k+1] = Ad @ states[:, k] + Bd @ modal_force[:, k]
        q, velocity = states[:n], states[n:]
        acceleration = modal_force-self.omega_rad_s[:, None]**2*q-damping[:, None]*velocity
        measured = phi @ acceleration
        if noise_std_m_s2:
            measured += np.random.default_rng(noise_seed).normal(0, noise_std_m_s2, measured.shape)
        return BeamResponse(np.arange(force.shape[1])/fs_hz, measured, q, velocity,
                            acceleration, float(fs_hz), sensors)
