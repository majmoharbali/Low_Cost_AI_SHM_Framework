"""
xai_engine.py

Core Module: Physical Explanation Engine
----------------------------------------
Translates abstract mathematical outputs (SHAP values) into human-readable,
physically-grounded explanations.

Research Context:
Addresses the 'Black Box' problem in infrastructure AI by mapping
statistical features (e.g., Kurtosis) to physical phenomena (e.g., Impulsiveness).
"""

import pandas as pd
from typing import Dict, List, Any

class PhysicalExplanationEngine:
    def __init__(self):
        self.class_names = {0: 'Healthy', 1: 'Incipient Damage', 2: 'Severe Damage'}
        
        # Knowledge Graph: Mapping ML Features to Physical Meaning
        self.feature_map = {
            'dominant_freq': {'name': 'Dominant Frequency', 'physics': 'primary oscillation', 'unit': 'Hz'},
            'spectral_centroid': {'name': 'Spectral Centroid', 'physics': 'frequency center of mass', 'unit': ''},
            'kurtosis': {'name': 'Kurtosis', 'physics': 'signal impulsiveness', 'unit': ''},
            'skewness': {'name': 'Skewness', 'physics': 'signal asymmetry', 'unit': ''},
            'rms': {'name': 'RMS', 'physics': 'vibration energy', 'unit': 'g'},
            'crest_factor': {'name': 'Crest Factor', 'physics': 'impact intensity', 'unit': ''},
            'peak': {'name': 'Peak Amplitude', 'physics': 'maximum displacement', 'unit': 'g'},
            'std_dev': {'name': 'Standard Deviation', 'physics': 'variability', 'unit': 'g'},
            'mean': {'name': 'Mean', 'physics': 'DC offset', 'unit': 'g'}
        }

    def generate_explanation(self, prediction_idx: int, shap_values: List[float], feature_names: List[str], feature_values_df: pd.DataFrame) -> str:
        """Generates a text narrative based on the highest-impact features."""
        
        # 1. Get Top 3 Contributors
        contributions = zip(feature_names, shap_values)
        # Sort by absolute impact
        sorted_feats = sorted(contributions, key=lambda x: abs(x[1]), reverse=True)[:3]
        
        state_name = self.class_names[prediction_idx]
        narrative = [f"Conclusion: The structure's current state is assessed as **{state_name}**."]
        
        if prediction_idx == 0:
            return narrative[0] + " Vibration signatures are within nominal operational bounds."

        narrative.append("This is due to significant deviations in the following vibration characteristics:")
        
        details = []
        for feat_name, impact in sorted_feats:
            if feat_name in self.feature_map:
                meta = self.feature_map[feat_name]
                # Extract actual value from the DataFrame passed from simulation
                try:
                    raw_val = feature_values_df[feat_name].values[0]
                    val_str = f"{raw_val:.2f} {meta['unit']}".strip()
                except (KeyError, IndexError):
                    val_str = "anomalous"

                desc = f"a **{meta['name']} ({meta['physics']})** of **{val_str}**"
                
                if impact > 0:
                    desc += " (strongly indicating potential damage)"
                else:
                    desc += " (counter-indicating damage)"
                details.append(desc)
                
        return " ".join(narrative) + " " + ", ".join(details) + "."
