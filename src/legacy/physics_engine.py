"""
physics_engine.py

Core Module: Structural Dynamics Simulation
-------------------------------------------
Implements a Multi-Degree-of-Freedom (MDOF) system approximation using
Modal Superposition. This module generates synthetic vibration data 
representative of a simply supported beam under stochastic excitation.

Research Context:
Models damage not as additive noise, but as parametric changes in the
stiffness matrix, resulting in eigenfrequency shifts and damping variations.
[Reference: Salawu, O. S. (1997). Detection of structural damage through changes in frequency.]
"""

import numpy as np
from scipy import signal

class ModalDamageSimulator:
    def __init__(self, n_modes: int = 3, num_sensors: int = 3, fs: int = 100):
        self.n_modes = n_modes
        self.num_sensors = num_sensors
        self.fs = fs
        
        # [ACADEMIC NOTE]
        # Base natural frequencies (Hz) for a conceptual steel beam span.
        # These represent the eigenvalues of the healthy system (λ = ω²).
        self.base_freqs = np.array([5.0, 12.0, 23.0])
        
        # Modal damping ratios (ξ). Damage is expected to increase ξ due to
        # micro-cracking and friction at joints.
        self.base_damping = np.array([0.02, 0.03, 0.04]) 
        
        self.current_stiffness_reduction = 0.0
        # Sensor placement at 10%, 50%, 90% of span length
        self.sensor_locs = np.linspace(0.1, 0.9, num_sensors)
        
        print(f"[Physics] Modal Simulator Initialized: {n_modes} modes, {num_sensors} sensors.")

    def apply_damage(self, severity: float):
        """
        Updates global stiffness parameter α (0.0 = Healthy, 1.0 = Failure).
        In this approximation, K_damaged = (1 - α) * K_initial
        """
        self.current_stiffness_reduction = severity

    def generate_response(self, t_vector: np.ndarray) -> np.ndarray:
        """
        Generates response u(x,t) via Modal Superposition:
        u(x,t) = Σ φ_i(x) * q_i(t)
        
        Where:
        - φ_i(x): Mode shape function (Sinusoidal for simply supported beam)
        - q_i(t): Modal coordinate (Time-domain response of SDOF system)
        """
        response = np.zeros((self.num_sensors, len(t_vector)))
        
        for i in range(self.n_modes):
            # [ACADEMIC NOTE]
            # Frequency shift relation: Δf/f ≈ 0.5 * ΔK/K
            # We model damage as a non-linear function of mode order to simulate
            # complex structural behavior.
            freq_shift = 1.0 - (0.5 * self.current_stiffness_reduction / (i + 1))
            mode_freq = self.base_freqs[i] * freq_shift
            
            # Damage increases energy dissipation (Damping)
            mode_damp = self.base_damping[i] + (self.current_stiffness_reduction * 0.05)
            
            # 1. Generate stochastic excitation (Wind/Traffic load)
            excitation = np.random.normal(0, 1, len(t_vector))
            
            # 2. Solve equation of motion for q_i(t) using digital filter
            # Bandpass filter approximates the SDOF transfer function around resonance
            b, a = signal.butter(2, [mode_freq*0.8, mode_freq*1.2], btype='bandpass', fs=self.fs)
            q_i = signal.lfilter(b, a, excitation) * np.exp(-mode_damp)
            
            # 3. Superposition
            for s_idx, x_loc in enumerate(self.sensor_locs):
                # Mode shape φ_i(x) = sin(n * π * x / L)
                phi_i = np.sin((i + 1) * np.pi * x_loc)
                response[s_idx] += phi_i * q_i

        # Normalize to sensor voltage range (-1.5V to 1.5V)
        return response / (np.max(np.abs(response)) + 1e-9)
