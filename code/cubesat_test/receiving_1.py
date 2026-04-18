"""
CubeSat Flight Software — Phase 1
Role   : Receive LoRa packets from Rescue Tower
Display: Print decoded packet to terminal
LEDs   : Red=Power | Green=Running | Blue=RX Activity
"""

import time
import RPi.GPIO as GPIO
from SX127x.LoRa import *
from SX127x.board_config import BOARD

# ─── GPIO Pin Definitions ───────────────────────────────────────
LED_RED   = 23   # Power indicator  → always ON
LED_GREEN = 25   # Running          → blinks every second
LED_BLUE  = 16   # RX activity      → flashes on packet received

# ─── LoRa Board Config (RA-02 via SPI) ─────────────────────────
BOARD.led_on  = lambda: None   # We handle LEDs manually
BOARD.led_off = lambda: None

# ─── GPIO Setup ─────────────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LED_RED,   GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE,  GPIO.OUT)

GPIO.output(LED_RED,   GPIO.HIGH)   # Power LED always ON
GPIO.output(LED_GREEN, GPIO.LOW)
GPIO.output(LED_BLUE,  GPIO.LOW)

# ─── Packet Parser ──────────────────────────────────────────────
def parse_packet(raw: str) -> dict | None:
    """
    Expected format from tower:
    msgID, timestamp_ms, lat, lon, type, checksum
    e.g. → 3,12400,22.57,88.36,RESCUE,12403
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

# ─── Checksum Validator ─────────────────────────────────────────
def validate_checksum(p: dict) -> bool:
    expected = p["msg_id"] + p["timestamp"]
    return expected == p["checksum"]

# ─── Display Packet ─────────────────────────────────────────────
def display_packet(p: dict, rssi: int):
    divider = "─" * 42
    print(f"\n{divider}")
    print(f"  📡  PACKET RECEIVED")
    print(f"{divider}")
    print(f"  Msg ID     : {p['msg_id']}")
    print(f"  Type       : ⚠️  {p['type']}")
    print(f"  Location   : {p['lat']}°N, {p['lon']}°E")
    print(f"  Uptime (ms): {p['timestamp']}")
    print(f"  RSSI       : {rssi} dBm")
    print(f"  Checksum   : {'✅ OK' if validate_checksum(p) else '❌ FAIL'}")
    print(f"{divider}\n")

# ─── LoRa Receiver Class ────────────────────────────────────────
class CubeSatReceiver(LoRa):

    def __init__(self, verbose=False):
        super().__init__(verbose)
        # Must match Rescue Tower settings
        self.set_mode(MODE.SLEEP)
        self.set_freq(433.0)                    # 433 MHz
        self.set_bw(BW.BW125)                   # 125 kHz bandwidth
        self.set_coding_rate(CODING_RATE.CR4_5) # 4/5 coding rate
        self.set_spreading_factor(7)            # SF7
        self.set_rx_crc(True)
        self.set_low_data_rate_optim(False)
        self.set_pa_config(pa_select=1)
        print("[BOOT] LoRa initialized at 433 MHz | SF7 | BW125")
        print("[BOOT] Waiting for packets from Rescue Tower...\n")

    def on_rx_done(self):
        """Called automatically when a packet arrives."""
        # Pull raw bytes
        payload = self.read_payload(nocheck=False)
        raw_str = bytes(payload).decode("utf-8", errors="ignore")
        rssi    = self.get_pkt_rssi_value()

        # Flash blue LED
        GPIO.output(LED_BLUE, GPIO.HIGH)

        # Parse and display
        packet = parse_packet(raw_str)
        if packet:
            display_packet(packet, rssi)
        else:
            print(f"[WARN] Unreadable packet: {raw_str}")

        GPIO.output(LED_BLUE, GPIO.LOW)

        # Re-arm receiver
        self.reset_ptr_rx()
        self.set_mode(MODE.RXCONT)

# ─── Green LED Heartbeat ────────────────────────────────────────
def heartbeat():
    """Blinks green LED every second to show system is alive."""
    while True:
        GPIO.output(LED_GREEN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(LED_GREEN, GPIO.LOW)
        time.sleep(0.9)

# ─── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    import threading

    print("=" * 42)
    print("   CUBESAT FLIGHT SOFTWARE — PHASE 1")
    print("   LoRa Receiver | 433 MHz")
    print("=" * 42)

    # Start heartbeat in background
    hb = threading.Thread(target=heartbeat, daemon=True)
    hb.start()

    # Init board and receiver
    BOARD.setup()
    lora = CubeSatReceiver(verbose=False)

    try:
        lora.set_mode(MODE.RXCONT)   # Continuous receive mode
        print("[INFO] Receiver armed. Listening...\n")
        while True:
            time.sleep(0.1)          # Main thread just idles

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Ctrl+C received.")
    finally:
        lora.set_mode(MODE.SLEEP)
        BOARD.teardown()
        GPIO.output(LED_RED,   GPIO.LOW)
        GPIO.output(LED_GREEN, GPIO.LOW)
        GPIO.output(LED_BLUE,  GPIO.LOW)
        GPIO.cleanup()
        print("[SHUTDOWN] Clean exit.")
