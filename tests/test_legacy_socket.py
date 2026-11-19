"""Exercise the real finite socket replay, not just the no-server smoke branch."""
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(importlib.util.find_spec('websockets') is None or importlib.util.find_spec('sklearn') is None,
                    reason='Optional legacy dependencies not installed')
def test_legacy_socket_initial_state_frames_and_finite_shutdown():
    from websockets.sync.client import connect
    root = Path(__file__).resolve().parents[1]
    with socket.socket() as reserve:
        reserve.bind(('127.0.0.1', 0))
        port = reserve.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-X', 'utf8', '-m', 'src.main_simulation', '--legacy',
                                '--windows', '1', '--port', str(port)], cwd=root,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
    try:
        client = None
        for _ in range(30):
            try:
                client = connect(f'ws://127.0.0.1:{port}', open_timeout=2, proxy=None)
                break
            except (OSError, TimeoutError):
                if process.poll() is not None:
                    break
                time.sleep(.1)
        if client is None:
            if process.poll() is None:
                process.terminate()
            diagnostic = process.communicate(timeout=5)
            pytest.fail('No loopback connection: ' + repr(diagnostic))
        with client:
            initial = json.loads(client.recv(timeout=10))
            assert initial['sensor_fusion']['aggregated_confidence'] is None
            assert initial['sensor_fusion']['fused_decision'] is None
            frames = [json.loads(client.recv(timeout=10)) for _ in range(3)]
            assert {f['latest_reading']['sensor_id'] for f in frames} == {0,1,2}
            assert all(f['source_kind'] == 'legacy_synthetic' for f in frames)
            assert all(f['sensor_fusion']['fused_decision'] is None for f in frames)
            assert all(len(f['latest_reading']['raw_signal']) == 100 for f in frames)
        stdout, stderr = process.communicate(timeout=25)
        assert process.returncode == 0, stdout + stderr
    finally:
        if process.poll() is None:
            process.terminate()
            process.communicate(timeout=5)
