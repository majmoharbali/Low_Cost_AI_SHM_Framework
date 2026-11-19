"""Finite, explicitly synthetic replay of the preserved classifier on sensor 0 only.

Original threaded runtime is retained in original_runtime.py for historical review.
No global health assessment, causal SHAP explanation or hardware metrics are issued.
"""
import asyncio
import json
import time
from datetime import datetime, timezone

import numpy as np

from .access import LEGACY_SOURCE, load_original_package, predict_legacy
from .physics_engine import ModalDamageSimulator


def no_assessment():
    return {
        'status': 'not_assessed', 'fused_decision': None,
        'aggregated_confidence': None, 'uncertainty_entropy': None,
        'sensor_states': {i: {'class': None, 'confidence': None} for i in range(3)},
    }


def frames(seed, windows):
    np.random.seed(seed)
    package = load_original_package(LEGACY_SOURCE)
    simulator = ModalDamageSimulator()
    for index in range(windows):
        severity = [0.0, 0.2, 0.6][min(2, 3*index//windows)]
        simulator.apply_damage(severity)
        values = simulator.generate_response(np.arange(1000)/100)
        values += np.random.normal(0, .05, values.shape)
        # Only sensor 0 matches the location used to train the original classifier.
        features, probabilities = predict_legacy(package, values[:1], source_kind=LEGACY_SOURCE)
        p = probabilities[0]
        for sensor_id in range(3):
            message = f'Legacy synthetic window {index}. No structural safety or measured-data inference.'
            if sensor_id == 0:
                message += f' Original S0 classifier: synthetic class {int(np.argmax(p))}; scores {p.round(3).tolist()}.'
            yield {
                'source_kind': LEGACY_SOURCE, 'window_id': index,
                'acquired_at': datetime.now(timezone.utc).isoformat(),
                'sensor_fusion': no_assessment(),
                'latest_reading': {
                    'sensor_id': sensor_id,
                    # Display only: anti-alias before decimating. Not a research signal.
                    'raw_signal': __import__('scipy').signal.resample_poly(values[sensor_id], 1, 10).tolist(),
                    'features': features.iloc[0].to_dict() if sensor_id == 0 else {},
                    'text_explanation': message,
                },
            }


def run(seed=42, windows=6, port=8765, smoke=False):
    print('LEGACY SYNTHETIC DEMO ONLY. Saved classifier is excluded from the research path.')
    if smoke:
        messages = list(frames(seed, windows))
        print(json.dumps({'status': 'completed', 'windows': windows, 'messages': len(messages), 'global_assessment': None}))
        return

    import websockets

    async def replay():
        clients = set()

        async def handler(socket):
            clients.add(socket)
            try:
                await socket.send(json.dumps({'sensor_fusion': no_assessment()}))
                await socket.wait_closed()
            finally:
                clients.discard(socket)

        async with websockets.serve(handler, '127.0.0.1', port):
            print(f'ws://localhost:{port}; {windows} windows, then automatic shutdown')
            await asyncio.sleep(1)
            for frame in frames(seed, windows):
                if clients:
                    await asyncio.gather(*(c.send(json.dumps(frame)) for c in tuple(clients)), return_exceptions=True)
                if frame['latest_reading']['sensor_id'] == 2:
                    await asyncio.sleep(10)
    asyncio.run(replay())
