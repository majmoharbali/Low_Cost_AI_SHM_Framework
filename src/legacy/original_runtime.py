"""
main_simulation.py

Runtime: Digital Twin Simulation
--------------------------------
Orchestrates the full-stack simulation:
1. Physics Engine (Data Generation)
2. Edge Processing (Inference + XAI)
3. Sensor Fusion (Bayesian Update)
4. WebSocket Server (Dashboard Link)
"""

import os
import sys
import json
import time
import pickle
import threading
import queue
import asyncio
import signal as sys_signal
import numpy as np
import pandas as pd
import websockets
import shap
from datetime import datetime
from scipy import signal
from scipy.stats import skew, kurtosis

# Fix path imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.physics_engine import ModalDamageSimulator
from core.sensor_fusion import BayesianSensorFusion
from core.xai_engine import PhysicalExplanationEngine
from utils.power_manager import PowerSubsystem
from utils.network_manager import NetworkSimulator

# --- CONFIGURATION ---
ARTIFACTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'artifacts')
MODEL_PATH = os.path.join(ARTIFACTS_DIR, 'shm_deployment_package_enhanced.pkl')

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating, np.bool_)): return obj.item()
        if isinstance(obj, np.ndarray): return obj.tolist()
        return super().default(obj)

class AdvancedDataStreamer:
    def __init__(self):
        self.modal_sim = ModalDamageSimulator(n_modes=3)
        self.t = np.linspace(0, 10, 1000, endpoint=False)
        self.schedule = queue.Queue()

    def stream(self, queues, stop_event):
        iteration = 0
        while not stop_event.is_set():
            iteration += 1
            self._check_schedule()
            full_resp = self.modal_sim.generate_response(self.t)
            print(f"\n[Data Stream] Iteration #{iteration} - Generating sensor data...")
            for i in range(3):
                # Add sensor noise
                queues[i].put(full_resp[i] + np.random.normal(0, 0.05, 1000))
            print(f"[Data Stream] ✓ Pushed data to 3 sensor queues (Damage Level: {self.modal_sim.current_stiffness_reduction:.2%})")
            time.sleep(10)

    def schedule_event(self, delay, severity, msg):
        self.schedule.put((time.time() + delay, severity, msg))

    def _check_schedule(self):
        if not self.schedule.empty():
            t, sev, msg = self.schedule.queue[0]
            if time.time() >= t:
                print(f"\n[Physics Event] {msg} (Severity: {sev})")
                self.modal_sim.apply_damage(sev)
                self.schedule.get()

class EdgeProcessor:
    def __init__(self, s_id, q_in, q_out, pkg):
        self.id = s_id
        self.q_in = q_in
        self.q_out = q_out
        self.model = pkg['model']
        self.scaler = pkg['scaler']
        self.sel = pkg['feature_selector']
        self.explainer = shap.TreeExplainer(pkg['explainer_model'])

    def process(self, stop_evt, power):
        while not stop_evt.is_set():
            try:
                sig = self.q_in.get(timeout=1)
                power.set_state('processing')
                
                # Feature Extraction (Must match training exactly)
                f, Pxx = signal.welch(sig, 100, nperseg=256)
                rms = np.sqrt(np.mean(sig**2))
                feats = pd.DataFrame([{
                    'mean': np.mean(sig), 'std_dev': np.std(sig), 'rms': rms,
                    'peak': np.max(np.abs(sig)), 'skewness': skew(sig), 'kurtosis': kurtosis(sig),
                    'crest_factor': np.max(np.abs(sig))/(rms+1e-9),
                    'dominant_freq': f[np.argmax(Pxx)],
                    'spectral_centroid': np.sum(f*Pxx)/(np.sum(Pxx)+1e-9)
                }])
                
                # Inference
                X_s = self.scaler.transform(feats)
                X_sel = self.sel.transform(X_s)
                pred = self.model.predict(X_sel)[0]
                proba = self.model.predict_proba(X_sel)[0]
                
                # Log prediction
                health_labels = ['Healthy', 'Minor Damage', 'Severe Damage']
                print(f"  [Sensor {self.id}] Prediction: {health_labels[pred]} (Confidence: {proba[pred]:.2%})")
                
                # XAI
                shap_vals = self.explainer.shap_values(X_sel)
                if isinstance(shap_vals, list): sv = shap_vals[pred][0]
                else: sv = shap_vals[0, :, pred] if shap_vals.ndim == 3 else shap_vals[0]
                
                all_names = self.scaler.get_feature_names_out() if hasattr(self.scaler, 'get_feature_names_out') else feats.columns
                sel_names = np.array(all_names)[self.sel.get_support()]
                
                # Log top SHAP features
                top_idx = np.argsort(np.abs(sv))[-2:][::-1]
                print(f"  [Sensor {self.id}] Top Features: {sel_names[top_idx[0]]}={sv[top_idx[0]]:.3f}, {sel_names[top_idx[1]]}={sv[top_idx[1]]:.3f}")

                power.set_state('idle')
                self.q_out.put({
                    'sensor_id': self.id, 'prediction_idx': pred, 'prediction_proba': proba,
                    'raw_signal': sig[::10].tolist(), 'features': feats.to_dict('records')[0],
                    'explanation': {'feature_names': sel_names.tolist(), 'feature_contributions': sv.tolist()}
                })
            except queue.Empty:
                power.set_state('idle')

class Orchestrator:
    def __init__(self):
        if not os.path.exists(MODEL_PATH):
            print(f"[Error] Model not found at {MODEL_PATH}. Run train_model.py first.")
            sys.exit(1)
            
        with open(MODEL_PATH, 'rb') as f: self.pkg = pickle.load(f)
        self.stop_evt = threading.Event()
        self.shutdown_requested = False
        self.clients = set()
        
        self.fusion = BayesianSensorFusion(3)
        self.streamer = AdvancedDataStreamer()
        self.power = PowerSubsystem()
        self.net = NetworkSimulator()
        self.xai = PhysicalExplanationEngine()
        
        self.res_queue = queue.Queue()
        self.queues = [queue.Queue() for _ in range(3)]
        self.processors = [EdgeProcessor(i, self.queues[i], self.res_queue, self.pkg) for i in range(3)]
        
        # Register signal handlers for graceful shutdown
        sys_signal.signal(sys_signal.SIGINT, self._signal_handler)
        sys_signal.signal(sys_signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        signal_name = 'SIGINT' if signum == sys_signal.SIGINT else 'SIGTERM'
        print(f"\n[System] Received {signal_name}, initiating graceful shutdown...")
        self.shutdown_requested = True
        self.stop_evt.set()

    async def ws_handler(self, ws):
        self.clients.add(ws)
        try: await ws.wait_closed()
        finally: self.clients.remove(ws)

    async def broadcast(self):
        broadcast_count = 0
        while not self.stop_evt.is_set() and not self.shutdown_requested:
            try:
                # Non-blocking check of result queue
                while not self.res_queue.empty():
                    res = self.res_queue.get()
                    self.fusion.update_sensor_state(res['sensor_id'], res['prediction_idx'], res['prediction_proba'])
                    
                    fusion_state = self.fusion.get_state()
                    fused_health = ['Healthy', 'Minor Damage', 'Severe Damage'][fusion_state['fused_decision']]
                    # Get confidence from aggregated_confidence (posterior probability of the fused decision)
                    confidence = fusion_state['aggregated_confidence'][fusion_state['fused_decision']]
                    print(f"  [Fusion] Bayesian Update → Fused State: {fused_health} (Confidence: {confidence:.2%})")
                    
                    if self.net.transmit(res, self.power):
                        # Generate XAI Text
                        res['text_explanation'] = self.xai.generate_explanation(
                            res['prediction_idx'], res['explanation']['feature_contributions'],
                            res['explanation']['feature_names'], pd.DataFrame([res['features']])
                        )
                        
                        state = {
                            'power': self.power.get_state(),
                            'network': self.net.get_state(),
                            'sensor_fusion': self.fusion.get_state(),
                            'latest_reading': res
                        }
                        if self.clients:
                            broadcast_count += 1
                            msg = json.dumps(state, cls=NumpyEncoder)
                            await asyncio.gather(*[c.send(msg) for c in self.clients])
                            print(f"  [WebSocket] ✓ Broadcast #{broadcast_count} sent to {len(self.clients)} client(s)")
                
                self.power.update()
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"Error in broadcast loop: {e}")
                if self.shutdown_requested:
                    break

    async def async_main(self):
        """Async main function to run WebSocket server and broadcast loop concurrently"""
        # Start WebSocket server
        async with websockets.serve(self.ws_handler, "localhost", 8765):
            print("[Network] WebSocket Server running on ws://localhost:8765")
            # Run broadcast loop
            await self.broadcast()

    def run(self):
        print("="*70)
        print("[System] Starting Digital Twin Simulation...")
        print("="*70)
        self.streamer.schedule_event(30, 0.2, "Incipient Damage")
        self.streamer.schedule_event(60, 0.6, "Severe Damage")
        print("[Schedule] Damage events scheduled at t=30s (20% severity) and t=60s (60% severity)")
        print("[System] Initializing worker threads...")

        # Start Threads
        threads = [threading.Thread(target=p.process, args=(self.stop_evt, self.power)) for p in self.processors]
        threads.append(threading.Thread(target=self.streamer.stream, args=(self.queues, self.stop_evt)))
        for t in threads: t.start()
        print(f"[System] ✓ Started {len(threads)} worker threads (3 edge processors + 1 data streamer)")
        print("[System] Starting WebSocket server and broadcast loop...")
        print("="*70)

        # Start Asyncio Loop
        try:
            asyncio.run(self.async_main())
        except KeyboardInterrupt:
            print("\n[System] Keyboard interrupt received...")
        except Exception as e:
            print(f"\n[System] Unexpected error: {e}")
        finally:
            print("[System] Shutting down gracefully...")
            self.stop_evt.set()
            
            # Close all WebSocket clients
            if self.clients:
                print(f"[Network] Closing {len(self.clients)} WebSocket connection(s)...")
                for client in list(self.clients):
                    try:
                        asyncio.run(client.close())
                    except:
                        pass
            
            # Wait for all threads to finish
            print("[System] Waiting for worker threads to complete...")
            for t in threads: 
                t.join(timeout=2)
            
            print("[System] Shutdown complete. Port 8765 is now free.")

if __name__ == "__main__":
    Orchestrator().run()
