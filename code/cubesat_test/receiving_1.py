"""
CubeSat Flight Software — Phase 1
Receive LoRa packets from Rescue Tower → print to terminal
"""

import time
import threading
import RPi.GPIO as GPIO
from SX127x.LoRa import *
from board_config_cubesat import BOARD

# ─── LED Pins (BCM) ────────────────────────────────────────────
LED_RED   = 23   # Power — always ON
LED_GREEN = 25   # Heartbeat — blinks every second
LED_BLUE  = 16   # RX activity — flashes on packet

# ─── GPIO Setup ────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LED_RED,   GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE,  GPIO.OUT)

GPIO.output(LED_RED,   GPIO.HIGH)  # Power always ON
GPIO.output(LED_GREEN, GPIO.LOW)
GPIO.output(LED_BLUE,  GPIO.LOW)

# ─── Packet Parser ─────────────────────────────────────────────
def parse_packet(raw: str):
    """
    Tower format: msgID,timestamp_ms,lat,lon,type,checksum
    Example:      3,12400,22.57,88.36,RESCUE,12403
    """
    try:
        parts = raw.strip().split(",")
        if len(parts) != 6:
            return None
        return {
            "msg_id"    : int(parts[0]),
            "timestamp" : int(parts[1]),
            "lat"       : float(parts[2]),
            "lon"       : float(parts[3]),
            "type"      : parts[4],
            "checksum"  : int(parts[5]),
        }
    except Exception as e:
        print(f"[PARSE ERROR] {e} | raw='{raw}'")
        return None

def validate_checksum(p: dict) -> bool:
    return (p["msg_id"] + p["timestamp"]) == p["checksum"]

# ─── Display ───────────────────────────────────────────────────
def display_packet(p: dict, rssi: int):
    print("\n" + "─" * 44)
    print("  📡  PACKET RECEIVED FROM RESCUE TOWER")
    print("─" * 44)
    print(f"  Msg ID     : {p['msg_id']}")
    print(f"  Alert Type : ⚠️  {p['type']}")
    print(f"  Location   : {p['lat']}°N  {p['lon']}°E")
    print(f"  Tower Up   : {p['timestamp']} ms")
    print(f"  RSSI       : {rssi} dBm")
    print(f"  Checksum   : {'✅ VALID' if validate_checksum(p) else '❌ CORRUPT'}")
    print("─" * 44 + "\n")

# ─── LoRa Receiver ─────────────────────────────────────────────
class CubeSatReceiver(LoRa):

    def __init__(self, verbose=False):
        super().__init__(verbose)
        self.set_mode(MODE.SLEEP)
        self.set_freq(433.0)
        self.set_bw(BW.BW125)
        self.set_coding_rate(CODING_RATE.CR4_5)
        self.set_spreading_factor(7)
        self.set_rx_crc(True)
        self.set_low_data_rate_optim(False)
        self.set_pa_config(pa_select=1)
        print("[LORA] Initialized — 433 MHz | SF7 | BW125 | CR4/5")
        print("[LORA] Waiting for packets...\n")

    def on_rx_done(self):
        payload = self.read_payload(nocheck=False)
        raw_str = bytes(payload).decode("utf-8", errors="ignore")
        rssi    = self.get_pkt_rssi_value()

        GPIO.output(LED_BLUE, GPIO.HIGH)

        packet = parse_packet(raw_str)
        if packet:
            display_packet(packet, rssi)
        else:
            print(f"[WARN] Bad packet: '{raw_str}'")

        GPIO.output(LED_BLUE, GPIO.LOW)

        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)

# ─── Heartbeat ─────────────────────────────────────────────────
def heartbeat():
    while True:
        GPIO.output(LED_GREEN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(LED_GREEN, GPIO.LOW)
        time.sleep(0.9)

# ─── Main ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 44)
    print("   CUBESAT FLIGHT SOFTWARE — PHASE 1")
    print("   LoRa RX | 433 MHz | RPi Zero W")
    print("=" * 44 + "\n")

    threading.Thread(target=heartbeat, daemon=True).start()

    BOARD.setup()
    lora = CubeSatReceiver(verbose=False)

    try:
        lora.set_mode(MODE.RXCONT)
        print("[INFO] Receiver armed. Listening...\n")
        while True:
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Ctrl+C")
    finally:
        lora.set_mode(MODE.SLEEP)
        BOARD.teardown()
        GPIO.output(LED_RED,   GPIO.LOW)
        GPIO.output(LED_GREEN, GPIO.LOW)
        GPIO.output(LED_BLUE,  GPIO.LOW)
        GPIO.cleanup()
        print("[SHUTDOWN] Clean exit.")
