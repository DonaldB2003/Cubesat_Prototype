import RPi.GPIO as GPIO
import time

# ─── PIN CONFIG ───────────────────────
NSS  = 5
RST  = 14
DIO0 = 2
SCK  = 18
MISO = 19
MOSI = 23

# ─── REGISTERS ───────────────────────
REG_FIFO          = 0x00
REG_OP_MODE       = 0x01
REG_FRF_MSB       = 0x06
REG_FRF_MID       = 0x07
REG_FRF_LSB       = 0x08
REG_PA_CONFIG     = 0x09
REG_FIFO_TX_BASE  = 0x0E
REG_FIFO_RX_BASE  = 0x0F
REG_FIFO_ADDR_PTR = 0x10
REG_IRQ_FLAGS     = 0x12
REG_RX_NB_BYTES   = 0x13
REG_PKT_RSSI      = 0x1A
REG_PKT_SNR       = 0x1B
REG_MODEM_CONFIG1 = 0x1D
REG_MODEM_CONFIG2 = 0x1E
REG_MODEM_CONFIG3 = 0x26
REG_PAYLOAD_LEN   = 0x22
REG_VERSION       = 0x42

MODE_LONG_RANGE   = 0x80
MODE_SLEEP        = 0x00
MODE_STDBY        = 0x01
MODE_TX           = 0x03
MODE_RX_CONT      = 0x05

# ─── NODE ID ─────────────────────────
NODE_ID = "2"   # Raspberry Pi relay

# ─── GPIO SETUP ──────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(NSS,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(RST,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SCK,  GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MOSI, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MISO, GPIO.IN)
GPIO.setup(DIO0, GPIO.IN)

# ═════════════════════════════════════
# SOFTWARE SPI
# ═════════════════════════════════════
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

def write_fifo(payload):
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO | 0x80)
    for b in payload:
        spi_transfer_byte(b)
    GPIO.output(NSS, GPIO.HIGH)

def read_fifo(length):
    data = []
    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO & 0x7F)
    for _ in range(length):
        data.append(spi_transfer_byte(0x00))
    GPIO.output(NSS, GPIO.HIGH)
    return data

# ═════════════════════════════════════
# LORA INIT
# ═════════════════════════════════════
def reset_lora():
    GPIO.output(RST, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(RST, GPIO.HIGH)
    time.sleep(0.1)

def init_lora():
    reset_lora()

    version = read_reg(REG_VERSION)
    print("LoRa version:", hex(version))

    if version != 0x12:
        raise RuntimeError("LoRa not detected")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
    time.sleep(0.1)

    # 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB, frf & 0xFF)

    write_reg(REG_FIFO_TX_BASE, 0x00)
    write_reg(REG_FIFO_RX_BASE, 0x00)

    write_reg(REG_PA_CONFIG, 0x8F)

    write_reg(REG_MODEM_CONFIG1, 0x72)
    write_reg(REG_MODEM_CONFIG2, 0x74)
    write_reg(REG_MODEM_CONFIG3, 0x04)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)

    print("LoRa Ready")

# ═════════════════════════════════════
# RELAY FUNCTION
# ═════════════════════════════════════
def relay_packet(raw_msg):

    # Prevent infinite loop (ignore already relayed packets)
    if raw_msg.startswith(NODE_ID + ","):
        return

    print("🔁 Relaying...")

    # Add relay ID at beginning
    new_msg = NODE_ID + "," + raw_msg
    payload = new_msg.encode('utf-8')

    # Switch to TX
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)
    write_reg(REG_FIFO_ADDR_PTR, 0x00)
    write_reg(REG_PAYLOAD_LEN, len(payload))

    write_fifo(payload)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_TX)

    # Wait TX done
    timeout = time.time() + 2
    while time.time() < timeout:
        if read_reg(REG_IRQ_FLAGS) & 0x08:
            write_reg(REG_IRQ_FLAGS, 0xFF)
            break

    time.sleep(0.05)

    # Back to RX
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

# ═════════════════════════════════════
# RECEIVE LOOP
# ═════════════════════════════════════
def receive_loop():
    print("📡 Listening...")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

    try:
        while True:
            irq = read_reg(REG_IRQ_FLAGS)

            if irq & 0x40:  # RxDone

                length = read_reg(REG_RX_NB_BYTES)
                fifo_addr = read_reg(0x10)
                write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

                payload = read_fifo(length)
                raw_msg = bytes(payload).decode('utf-8', errors='ignore')

                print("\n📥 Received:", raw_msg)

                # Parse (optional but useful)
                try:
                    parts = raw_msg.split(',')

                    if len(parts) >= 6:
                        msg_id = parts[0]
                        timestamp = parts[1]
                        lat = parts[2]
                        lon = parts[3]
                        msg_type = parts[4]

                        print(f"ID: {msg_id} | Type: {msg_type}")
                except:
                    pass

                # Relay packet
                relay_packet(raw_msg)

                # Clear IRQ
                write_reg(REG_IRQ_FLAGS, 0xFF)

            time.sleep(0.05)

    except KeyboardInterrupt:
        print("\nStopped")

    finally:
        GPIO.cleanup()

# ═════════════════════════════════════
# MAIN
# ═════════════════════════════════════
def main():
    print("=================================")
    print("   LoRa Relay Node (Pi)")
    print("=================================")

    init_lora()
    receive_loop()

if __name__ == "__main__":
    main()
