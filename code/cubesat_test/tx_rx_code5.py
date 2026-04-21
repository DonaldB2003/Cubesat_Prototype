import RPi.GPIO as GPIO
import time

# ─── PINOUT (FINAL - NO CONFLICTS) ─────────────────────
NSS  = 5
RST  = 22
DIO0 = 4
SCK  = 18
MISO = 19
MOSI = 23

# ─── REGISTERS ─────────────────────────────────────────
REG_FIFO          = 0x00
REG_OP_MODE       = 0x01
REG_FRF_MSB       = 0x06
REG_FRF_MID       = 0x07
REG_FRF_LSB       = 0x08
REG_FIFO_TX_BASE  = 0x0E
REG_FIFO_RX_BASE  = 0x0F
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_RX_CURR  = 0x10
REG_IRQ_FLAGS     = 0x12
REG_RX_NB_BYTES   = 0x13
REG_PKT_RSSI      = 0x1A
REG_PKT_SNR       = 0x1B
REG_PAYLOAD_LEN   = 0x22
REG_MODEM_CONFIG1 = 0x1D
REG_MODEM_CONFIG2 = 0x1E
REG_MODEM_CONFIG3 = 0x26
REG_VERSION       = 0x42

MODE_LONG_RANGE   = 0x80
MODE_SLEEP        = 0x00
MODE_STDBY        = 0x01
MODE_TX           = 0x03
MODE_RX_CONT      = 0x05

# ─── GPIO SETUP ────────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(NSS,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(RST,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SCK,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MOSI, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MISO, GPIO.IN)
GPIO.setup(DIO0, GPIO.IN)

# ═══════════════════════════════════════════════════════
# SOFTWARE SPI
# ═══════════════════════════════════════════════════════
def spi_transfer_byte(data):
    received = 0
    for i in range(8):
        GPIO.output(MOSI, (data & (0x80 >> i)) != 0)
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
    data = []
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO & 0x7F)
    for _ in range(length):
        data.append(spi_transfer_byte(0x00))
    GPIO.output(NSS, GPIO.HIGH)
    return data

# ═══════════════════════════════════════════════════════
# LORA INIT
# ═══════════════════════════════════════════════════════
def reset_lora():
    GPIO.output(RST, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(RST, GPIO.HIGH)
    time.sleep(0.1)

def init_lora():
    reset_lora()

    version = read_reg(REG_VERSION)
    print(f"LoRa version: {hex(version)}")

    if version != 0x12:
        raise RuntimeError("❌ LoRa not detected")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
    time.sleep(0.1)

    # 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB,  frf        & 0xFF)

    write_reg(REG_FIFO_TX_BASE, 0x00)
    write_reg(REG_FIFO_RX_BASE, 0x00)

    write_reg(REG_MODEM_CONFIG1, 0x72)
    write_reg(REG_MODEM_CONFIG2, 0x74)
    write_reg(REG_MODEM_CONFIG3, 0x04)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)

    print("✅ Receiver init OK")

# ═══════════════════════════════════════════════════════
# SEND FUNCTION (WITH TIMEOUT)
# ═══════════════════════════════════════════════════════
def send_packet(data_bytes):
    print("📡 Forwarding packet...")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)
    write_reg(REG_FIFO_ADDR_PTR, 0x00)

    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO | 0x80)
    for b in data_bytes:
        spi_transfer_byte(b)
    GPIO.output(NSS, GPIO.HIGH)

    write_reg(REG_PAYLOAD_LEN, len(data_bytes))
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_TX)

    # Timeout-safe TX wait
    start = time.time()
    while True:
        irq = read_reg(REG_IRQ_FLAGS)

        if irq & 0x08:
            write_reg(REG_IRQ_FLAGS, 0xFF)
            print("✅ Forwarded")
            break

        if time.time() - start > 2:
            print("❌ TX Timeout")
            break

    time.sleep(0.05)

# ═══════════════════════════════════════════════════════
# RECEIVE + RELAY LOOP
# ═══════════════════════════════════════════════════════
def receive_loop():
    print("📡 Listening + Relaying...\n")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

    try:
        while True:
            irq = read_reg(REG_IRQ_FLAGS)

            if irq & 0x40:  # RxDone

                length = read_reg(REG_RX_NB_BYTES)
                fifo_addr = read_reg(REG_FIFO_RX_CURR)
                write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

                payload = read_fifo(length)
                raw_msg = bytes(payload).decode('utf-8', errors='ignore')

                print("\n📦 RAW:", raw_msg)

                try:
                    parts = raw_msg.strip().split(',')

                    if len(parts) != 6:
                        print("⚠️ Invalid format")
                        write_reg(REG_IRQ_FLAGS, 0xFF)
                        continue

                    msg_id   = int(parts[0])
                    timestamp= int(parts[1])
                    lat      = float(parts[2])
                    lon      = float(parts[3])
                    msg_type = parts[4]
                    rx_crc   = int(parts[5])

                    calc_crc = msg_id + timestamp

                    print("=================================")
                    print(f"ID       : {msg_id}")
                    print(f"Time     : {timestamp}")
                    print(f"Location : {lat}, {lon}")
                    print(f"Type     : {msg_type}")

                    if calc_crc == rx_crc:
                        print("CRC      : ✅ OK")
                    else:
                        print("CRC      : ❌ FAIL")

                    rssi = read_reg(REG_PKT_RSSI) - 157
                    snr  = read_reg(REG_PKT_SNR) / 4.0

                    print(f"RSSI     : {rssi} dBm")
                    print(f"SNR      : {snr} dB")

                    # ─── RELAY LOGIC ─────────────────────
                    if msg_type != "RELAYED":
                        parts[4] = "RELAYED"
                        new_msg = ",".join(map(str, parts))

                        print("🔁 Relaying packet...")
                        time.sleep(0.1)

                        send_packet(new_msg.encode())

                        write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
                    else:
                        print("⛔ Already relayed, skipping")

                    print("=================================\n")

                except Exception as e:
                    print("❌ Parse Error:", e)

                write_reg(REG_IRQ_FLAGS, 0xFF)

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\n🛑 Stopped")
    finally:
        GPIO.cleanup()

# ═══════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════
def main():
    print("=================================")
    print("      LoRa RELAY NODE")
    print("=================================")

    init_lora()
    receive_loop()

if __name__ == "__main__":
    main()
