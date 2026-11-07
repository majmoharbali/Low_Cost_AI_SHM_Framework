"""
train_model.py

Pipeline: Physics-Informed Model Training
-----------------------------------------
1. Generates synthetic training data using the Physics Engine.
2. Extracts features (PSD, Statistical Moments).
3. Trains a Calibrated Random Forest Classifier.
4. Optimizes decision thresholds using Cost-Sensitive ROC Analysis.

Output: artifacts/shm_deployment_package_enhanced.pkl
"""

import os
import sys
import pickle
import numpy as np
import pandas as pd
from scipy import signal
from scipy.stats import skew, kurtosis

# Import Machine Learning Libraries
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_curve, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV

# Fix path to allow importing from core/
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from .physics_engine import ModalDamageSimulator
from ..features import FeatureExtractor
from .access import MODEL

# --- CONFIGURATION ---
MODEL_PATH = str(MODEL)

class DataGeneratorWrapper:
    """Wrapper to generate large datasets using the ModalDamageSimulator."""
    def __init__(self, n_samples=4500):
        self.sim = ModalDamageSimulator(n_modes=3)
        self.n_samples = n_samples
        self.t = np.linspace(0, 10, 1000, endpoint=False) # 10 seconds at 100Hz

    def generate_dataset(self):
        X, y = [], []
        samples_per_class = self.n_samples // 3
        print(f"[Training] Generating {self.n_samples} physics-based samples...")

        # 1. Healthy
        self.sim.apply_damage(0.0)
        for _ in range(samples_per_class):
            # Simulate random sensor read from the beam
            resp = self.sim.generate_response(self.t)
            X.append(resp[0] + np.random.normal(0, 0.05, len(self.t))) # Use Sensor 0
            y.append(0)

        # 2. Incipient (10-30% Stiffness Loss)
        for _ in range(samples_per_class):
            self.sim.apply_damage(np.random.uniform(0.1, 0.3))
            resp = self.sim.generate_response(self.t)
            X.append(resp[0] + np.random.normal(0, 0.05, len(self.t)))
            y.append(1)

        # 3. Severe (40-80% Stiffness Loss)
        for _ in range(samples_per_class):
            self.sim.apply_damage(np.random.uniform(0.4, 0.8))
            resp = self.sim.generate_response(self.t)
            X.append(resp[0] + np.random.normal(0, 0.05, len(self.t)))
            y.append(2)

        return np.array(X), np.array(y)

class StatisticalThresholdCalculator:
    """Optimizes decision boundaries using Cost-Sensitive ROC Analysis."""
    def __init__(self, cost_fp=1000, cost_fn=50000):
        self.cost_fp = cost_fp
        self.cost_fn = cost_fn

    def calculate(self, y_true, y_probs):
        thresholds = {}
        for cls, name in [(1, 'incipient'), (2, 'severe')]:
            y_bin = (y_true == cls).astype(int)
            probs = y_probs[:, cls]
            fpr, tpr, thresh = roc_curve(y_bin, probs)
            # Minimize Expected Cost
            costs = (self.cost_fp * fpr) + (self.cost_fn * (1 - tpr))
            best_idx = np.argmin(costs)
            thresholds[f'{name}_threshold'] = float(thresh[best_idx])
            print(f"  > Optimized {name.title()} Threshold: {thresh[best_idx]:.4f} (weighted in-sample error: {costs[best_idx]:,.0f}; not expected financial loss)")
        return thresholds

def main(samples=4500, seed=42, output=None, trees=100):
    from pathlib import Path
    np.random.seed(seed)
    output = Path(output or "outputs/legacy/retrained.pkl").resolve()
    if output == Path(MODEL_PATH).resolve():
        raise ValueError("The original model must not be overwritten")
    print("LEGACY SYNTHETIC REPRODUCTION: no independent evaluation; not research evidence")
    # 1. Generate Data
    gen = DataGeneratorWrapper(n_samples=samples)
    X_raw, y = gen.generate_dataset()
    
    # 2. Extract Features
    extractor = FeatureExtractor()
    X_feats = extractor.extract(X_raw)
    
    # 3. Train Model
    print("[Training] Training Calibrated Random Forest...")
    base_rf = RandomForestClassifier(n_estimators=trees, max_depth=10, class_weight='balanced', random_state=42)
    model = CalibratedClassifierCV(base_rf, method='isotonic', cv=3)
    
    # Explainer model (SHAP needs standard RF)
    explainer_rf = RandomForestClassifier(n_estimators=trees, max_depth=10, random_state=42)
    
    scaler = StandardScaler()
    selector = SelectKBest(f_classif, k=8)
    
    # Pipeline
    X_scaled = scaler.fit_transform(X_feats)
    X_sel = selector.fit_transform(X_scaled, y)
    
    model.fit(X_sel, y)
    explainer_rf.fit(X_sel, y)
    
    # 4. Optimize Thresholds
    probs = model.predict_proba(X_sel)
    calc = StatisticalThresholdCalculator()
    thresholds = calc.calculate(y, probs)
    
    # 5. Save Artifacts
    package = {
        'model': model,
        'scaler': scaler,
        'feature_selector': selector,
        'explainer_model': explainer_rf,
        'confidence_stats': thresholds
    }
    
    package['source_kind'] = 'legacy_synthetic'
    package['evaluation_status'] = 'legacy_in_sample_only'
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('wb') as f:
        pickle.dump(package, f)
    print(f"[Success] Legacy reproduction saved to {output}")

if __name__ == "__main__":
    raise SystemExit("Use python -m src.train_model --legacy")
