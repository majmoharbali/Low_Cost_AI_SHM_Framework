"""
sensor_fusion.py

Core Module: Probabilistic Data Fusion
--------------------------------------
Implements a centralized Bayesian Fusion engine to aggregate decision
probabilities from distributed edge sensors.

Research Context:
Addresses the 'Portfolio Risk' problem by combining uncertain evidence 
from heterogeneous sensors using Bayesian Inference, weighted by 
a-priori sensor reliability estimates.
"""

import numpy as np
from typing import Tuple, Dict, Any

class BayesianSensorFusion:
    def __init__(self, num_sensors: int):
        self.num_sensors = num_sensors
        
        # [ACADEMIC NOTE]
        # Prior Probability Distribution P(H)
        # We initialize with a strong prior for 'Healthy' state (State 0).
        # States: [0: Healthy, 1: Incipient, 2: Severe]
        self.prior = np.array([0.90, 0.08, 0.02]) 
        
        # Sensor Reliability Matrix P(E|H)
        # Represents the confidence in the specific sensor hardware/location.
        self.reliability = np.array([0.95] * num_sensors)
        
        # Current State Memory
        self.sensor_states = {
            i: {'class': 0, 'confidence': np.array([1.0, 0.0, 0.0])} 
            for i in range(num_sensors)
        }
        
        print(f"[Logic] Bayesian Fusion Engine Initialized. Prior: {self.prior}")

    def update_sensor_state(self, sensor_id: int, prediction_idx: int, confidence: list):
        """Updates the local belief state for a specific sensor node."""
        self.sensor_states[sensor_id] = {
            'class': prediction_idx,
            'confidence': np.array(confidence)
        }

    def get_fused_decision(self) -> Tuple[int, np.ndarray, float]:
        """
        Computes the Posterior Probability using Bayes' Rule:
        P(H|E) ∝ P(E|H) * P(H)
        
        Returns:
            - MAP Decision (Maximum A Posteriori)
            - Posterior Distribution
            - System Entropy (Uncertainty Metric)
        """
        # Work in Log-Space to prevent floating point underflow
        log_posterior = np.log(self.prior + 1e-10)
        
        for i in range(self.num_sensors):
            probs = self.sensor_states[i]['confidence']
            
            # [ACADEMIC NOTE]
            # Reliability weighting:
            # If a sensor is unreliable, its likelihood is flattened towards uniform distribution,
            # reducing its impact on the final decision.
            weighted_likelihood = (probs * self.reliability[i]) + \
                                  ((1 - self.reliability[i]) * np.array([0.33, 0.33, 0.33]))
            
            log_posterior += np.log(weighted_likelihood + 1e-10)
            
        # Convert back to linear probability space and normalize
        posterior = np.exp(log_posterior - np.max(log_posterior))
        posterior /= np.sum(posterior)
        
        # [ACADEMIC NOTE]
        # Calculate Shannon Entropy as a metric of epistemic uncertainty.
        # High entropy indicates conflicting sensor data.
        entropy = -np.sum(posterior * np.log(posterior + 1e-10))
        
        # Maximum A Posteriori (MAP) Decision
        decision = np.argmax(posterior)
        
        return decision, posterior, entropy

    def get_state(self) -> Dict[str, Any]:
        """Returns serializable state object for the Digital Twin."""
        decision, posterior, entropy = self.get_fused_decision()
        return {
            'fused_decision': int(decision),
            'aggregated_confidence': posterior.tolist(),
            'uncertainty_entropy': float(entropy),
            'sensor_states': {
                k: {'class': int(v['class']), 'confidence': v['confidence'].tolist()} 
                for k,v in self.sensor_states.items()
            }
        }
