import RPi.GPIO as GPIO
import time
import threading

# ─── CubeSat Pinout (BCM) ─────────────────────────────────────
NSS  = 8    # GPIO 8  — Chip Select (CE0)
RST  = 17   # GPIO 17 — Reset
DIO0 = 4    # GPIO 4  — RX Done interrupt
SCK  = 11   # GPIO 11 — Clock
MISO = 9    # GPIO 9  — Master In Slave Out
MOSI = 10   # GPIO 10 — Master Out Slave In

# ─── LEDs ─────────────────────────────────────────────────────
LED_RED   = 23   # Power — always ON
LED_GREEN = 25   # Heartbeat — blinks every second
LED_BLUE  = 16   # RX activity — flashes on packet

# ─── LoRa Registers ───────────────────────────────────────────
REG_FIFO            = 0x00
REG_OP_MODE         = 0x01
REG_FRF_MSB         = 0x06
REG_FRF_MID         = 0x07
REG_FRF_LSB         = 0x08
REG_PA_CONFIG       = 0x09
REG_FIFO_RX_BASE    = 0x0F
REG_FIFO_ADDR_PTR   = 0x10
REG_IRQ_FLAGS       = 0x12
REG_RX_NB_BYTES     = 0x13
REG_PKT_RSSI        = 0x1A
REG_FIFO_RX_CURRENT = 0x10
REG_MODEM_CONFIG1   = 0x1D
REG_MODEM_CONFIG2   = 0x1E
REG_MODEM_CONFIG3   = 0x26
REG_FIFO_RX_BYTE    = 0x25
REG_VERSION         = 0x42

MODE_LONG_RANGE = 0x80
MODE_SLEEP      = 0x00
MODE_STDBY      = 0x01
MODE_RXCONT     = 0x05   # Continuous RX

IRQ_RX_DONE     = 0x40
IRQ_CRC_ERROR   = 0x20

# ══════════════════════════════════════════════════════════════
# GPIO SETUP
# ══════════════════════════════════════════════════════════════
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# LoRa pins
GPIO.setup(NSS,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(RST,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SCK,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MOSI, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MISO, GPIO.IN)
GPIO.setup(DIO0, GPIO.IN)

# LED pins
GPIO.setup(LED_RED,   GPIO.OUT, initial=GPIO.HIGH)  # Power ON immediately
GPIO.setup(LED_GREEN, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(LED_BLUE,  GPIO.OUT, initial=GPIO.LOW)

# ══════════════════════════════════════════════════════════════
# SOFTWARE SPI (BIT-BANG) — same as transmitter
# ══════════════════════════════════════════════════════════════
def spi_transfer_byte(data):
    received = 0
    for i in range(8):
        GPIO.output(MOSI, GPIO.HIGH if (data & (0x80 >> i)) else GPIO.LOW)
        GPIO.output(SCK, GPIO.HIGH)
        if GPIO.input(MISO):
            received |= (0x80 >> i)
        GPIO.output(SCK, GPIO.LOW)
    return received

def write_reg(reg, val):
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(reg | 0x80)
    spi_transfer_byte(val)
    GPIO.output(NSS, GPIO.HIGH)

def read_reg(reg):
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(reg & 0x7F)
    val = spi_transfer_byte(0x00)
    GPIO.output(NSS, GPIO.HIGH)
    return val

def read_fifo(length):
    """Burst read bytes from FIFO."""
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO & 0x7F)
    data = [spi_transfer_byte(0x00) for _ in range(length)]
    GPIO.output(NSS, GPIO.HIGH)
    return data

# ══════════════════════════════════════════════════════════════
# LORA INIT — same settings as transmitter
# ══════════════════════════════════════════════════════════════
def reset_lora():
    GPIO.output(RST, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(RST, GPIO.HIGH)
    time.sleep(0.1)

def init_lora():
    reset_lora()

    version = read_reg(REG_VERSION)
    print(f"[LORA] Chip version: {hex(version)}")

    if version != 0x12:
        raise RuntimeError(f"[LORA] Not found! Got {hex(version)} — check wiring!")

    # Sleep + LoRa mode
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
    time.sleep(0.1)

    # 433 MHz — must match tower
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB,  frf        & 0xFF)

    # FIFO base
    write_reg(REG_FIFO_RX_BASE, 0x00)
    write_reg(REG_FIFO_ADDR_PTR, 0x00)

    # BW=125kHz, CR=4/5 — must match tower
    write_reg(REG_MODEM_CONFIG1, 0x72)

    # SF=7, CRC on — must match tower
    write_reg(REG_MODEM_CONFIG2, 0x74)

    # AGC on
    write_reg(REG_MODEM_CONFIG3, 0x04)

    # Standby
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)

    print("[LORA] Init OK — 433 MHz | SF7 | BW125 | CR4/5")

def start_rx():
    """Put LoRa into continuous receive mode."""
    write_reg(REG_FIFO_ADDR_PTR, 0x00)
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RXCONT)
    print("[LORA] Listening for packets...\n")

# ══════════════════════════════════════════════════════════════
# PACKET HANDLING
# ══════════════════════════════════════════════════════════════
def parse_rescue_packet(raw: str):
    """
    Rescue Tower format: msgID,timestamp,lat,lon,type,checksum
    Example: 3,12400,22.57,88.36,RESCUE,12403
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
    except:
        return None

def validate_checksum(p: dict) -> bool:
    return (p["msg_id"] + p["timestamp"]) == p["checksum"]

def display_packet(raw: str, rssi: int):
    print("─" * 46)
    packet = parse_rescue_packet(raw)

    if packet:
        # Rescue Tower packet
        valid = validate_checksum(packet)
        print(f"  📡  RESCUE TOWER PACKET")
        print(f"─" * 46)
        print(f"  Msg ID     : {packet['msg_id']}")
        print(f"  Alert Type : ⚠️  {packet['type']}")
        print(f"  Location   : {packet['lat']}°N  {packet['lon']}°E")
        print(f"  Tower Up   : {packet['timestamp']} ms")
        print(f"  RSSI       : {rssi} dBm")
        print(f"  Checksum   : {'✅ VALID' if valid else '❌ CORRUPT'}")
    else:
        # Generic / test packet
        print(f"  📡  RAW PACKET")
        print(f"─" * 46)
        print(f"  Data       : {raw}")
        print(f"  RSSI       : {rssi} dBm")

    print("─" * 46 + "\n")

def check_rx():
    """Check IRQ flags and read packet if RX done."""
    irq = read_reg(REG_IRQ_FLAGS)

    if irq & IRQ_RX_DONE:
        # Clear all IRQ flags
        write_reg(REG_IRQ_FLAGS, 0xFF)

        # CRC error check
        if irq & IRQ_CRC_ERROR:
            print("[WARN] CRC error — packet dropped")
            write_reg(REG_FIFO_ADDR_PTR, 0x00)
            return

        # Flash blue LED
        GPIO.output(LED_BLUE, GPIO.HIGH)

        # Read how many bytes arrived
        nb_bytes = read_reg(REG_RX_NB_BYTES)

        # Read RSSI
        rssi = read_reg(REG_PKT_RSSI) - 157

        # Set FIFO pointer to start of received packet
        write_reg(REG_FIFO_ADDR_PTR, 0x00)

        # Read payload
        payload = read_fifo(nb_bytes)
        raw_str = bytes(payload).decode("utf-8", errors="ignore")

        # Display
        display_packet(raw_str, rssi)

        GPIO.output(LED_BLUE, GPIO.LOW)

        # Reset FIFO pointer
        write_reg(REG_FIFO_ADDR_PTR, 0x00)

# ══════════════════════════════════════════════════════════════
# GREEN LED HEARTBEAT
# ══════════════════════════════════════════════════════════════
def heartbeat():
    while True:
        GPIO.output(LED_GREEN, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(LED_GREEN, GPIO.LOW)
        time.sleep(0.9)

# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
def main():
    print("=" * 46)
    print("   CUBESAT FLIGHT SOFTWARE — PHASE 1")
    print("   LoRa Receiver | Software SPI | 433 MHz")
    print("=" * 46)
    print(f"  NSS  → GPIO {NSS}  |  RST  → GPIO {RST}")
    print(f"  DIO0 → GPIO {DIO0}  |  SCK  → GPIO {SCK}")
    print(f"  MISO → GPIO {MISO}  |  MOSI → GPIO {MOSI}")
    print("=" * 46 + "\n")

    # Start heartbeat
    threading.Thread(target=heartbeat, daemon=True).start()

    # Init LoRa
    init_lora()
    start_rx()

    try:
        while True:
            check_rx()
            time.sleep(0.05)   # Poll every 50ms

    except KeyboardInterrupt:
        print("\n[SHUTDOWN] Ctrl+C received.")
    finally:
        write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
        GPIO.output(LED_RED,   GPIO.LOW)
        GPIO.output(LED_GREEN, GPIO.LOW)
        GPIO.output(LED_BLUE,  GPIO.LOW)
        GPIO.cleanup()
        print("[SHUTDOWN] Clean exit.")

if __name__ == "__main__":
    main()
