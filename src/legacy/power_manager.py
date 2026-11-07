"""
power_manager.py
Simulates the energy constraints of an edge device (Battery + Solar).
"""

import time
import numpy as np
import threading
from typing import Literal

DeviceState = Literal['idle', 'sensing', 'processing', 'transmitting']

class PowerSubsystem:
    def __init__(self, battery_capacity_mah: int = 2000, voltage: float = 3.7):
        self.initial_capacity_wh = (battery_capacity_mah / 1000) * voltage
        self.current_charge_wh = self.initial_capacity_wh
        self.max_capacity_wh = self.initial_capacity_wh
        self.state = 'idle'
        self.last_update_time = time.time()
        self.is_cloudy = False
        self.solar_rate = 0.0
        self.lock = threading.Lock()

    def set_state(self, new_state: DeviceState):
        with self.lock:
            self.state = new_state

    def update(self):
        now = time.time()
        elapsed = now - self.last_update_time
        if elapsed < 1: return

        # Power Draw Model (Watts)
        draw_map = {'idle': 0.025, 'sensing': 0.1, 'processing': 1.8, 'transmitting': 0.45}
        draw = draw_map.get(self.state, 0.1)
        
        # Simple Solar Model
        self.solar_rate = 0.5 if not self.is_cloudy else 0.1 # Simplified diurnal
        
        with self.lock:
            drain = (draw * elapsed) / 3600
            charge = (self.solar_rate * elapsed) / 3600
            self.current_charge_wh = np.clip(self.current_charge_wh - drain + charge, 0, self.max_capacity_wh)
        
        self.last_update_time = now

    def get_state(self):
        with self.lock:
            pct = (self.current_charge_wh / self.max_capacity_wh) * 100
            return {
                'battery_percentage': pct,
                'solar_rate_w': self.solar_rate,
                'state': self.state
            }
