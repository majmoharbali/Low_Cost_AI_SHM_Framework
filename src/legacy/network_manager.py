"""
network_manager.py
Simulates stochastic packet loss and data caps in LPWAN networks.
"""

import time
import random

class NetworkSimulator:
    def __init__(self, packet_loss_prob=0.15):
        self.loss_prob = packet_loss_prob
        self.daily_bytes = 0
        self.success_count = 0
        self.fail_count = 0

    def transmit(self, payload, power_sys) -> bool:
        """Attempts to transmit data with retries."""
        payload_size = 2500 # Approx bytes
        
        for attempt in range(3):
            power_sys.set_state('transmitting')
            time.sleep(0.1) # Transmission delay
            
            if random.random() > self.loss_prob:
                self.success_count += 1
                self.daily_bytes += payload_size
                power_sys.set_state('idle')
                return True
            
        self.fail_count += 1
        power_sys.set_state('idle')
        return False

    def get_state(self):
        total = self.success_count + self.fail_count
        rate = self.success_count / total if total > 0 else 1.0
        return {
            'daily_bytes_sent': self.daily_bytes,
            'transmission_success_rate': rate
        }
