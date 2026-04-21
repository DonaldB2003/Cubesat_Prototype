import RPi.GPIO as GPIO
import time
import smbus2

# ─────────────────────────────────────
# BMP280 SETUP (CALIBRATED)
# ─────────────────────────────────────
bus = smbus2.SMBus(1)
ADDR = 0x76

cal = bus.read_i2c_block_data(ADDR, 0x88, 24)

def u16(i): return (cal[i+1] << 8) | cal[i]
def s16(i): v = u16(i); return v - 65536 if v > 32767 else v

dig_T1 = u16(0);  dig_T2 = s16(2);  dig_T3 = s16(4)
dig_P1 = u16(6)
dig_P2 = s16(8);  dig_P3 = s16(10); dig_P4 = s16(12)
dig_P5 = s16(14); dig_P6 = s16(16); dig_P7 = s16(18)
dig_P8 = s16(20); dig_P9 = s16(22)

bus.write_byte_data(ADDR, 0xF4, 0x27)
bus.write_byte_data(ADDR, 0xF5, 0xA0)
time.sleep(0.5)

def read_bmp280():
    try:
        d = bus.read_i2c_block_data(ADDR, 0xF7, 6)

        adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)

        # Temperature
        var1 = ((adc_T / 16384.0) - (dig_T1 / 1024.0)) * dig_T2
        var2 = ((adc_T / 131072.0) - (dig_T1 / 8192.0)) ** 2 * dig_T3
        t_fine = var1 + var2
        temp = t_fine / 5120.0

        # Pressure
        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * dig_P6 / 32768.0
        var2 = var2 + var1 * dig_P5 * 2.0
        var2 = var2 / 4.0 + dig_P4 * 65536.0
        var1 = (dig_P3 * var1 * var1 / 524288.0 + dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * dig_P1

        if var1 == 0:
            return 0, 0, 0

        pressure = 1048576.0 - adc_P
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        pressure = pressure / 100.0

        altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** (1.0 / 5.255))

        return round(temp, 2), round(pressure, 2), round(altitude, 2)

    except Exception as e:
        print("BMP Error:", e)
        return 0, 0, 0


# ─────────────────────────────────────
# LORA SETUP (SX1278‑style)
# ─────────────────────────────────────
NSS  = 5
RST  = 22
DIO0 = 4
SCK  = 18
MISO = 19
MOSI = 23

REG_FIFO        = 0x00
REG_OP_MODE     = 0x01
REG_FRF_MSB     = 0x06
REG_FRF_MID     = 0x07
REG_FRF_LSB     = 0x08
REG_FIFO_TX_BASE= 0x0E
REG_FIFO_RX_BASE= 0x0F
REG_FIFO_ADDR_PTR=0x0D
REG_FIFO_RX_CURR=0x10
REG_IRQ_FLAGS   = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_RSSI    = 0x1A
REG_PKT_SNR     = 0x1B
REG_PAYLOAD_LEN = 0x22
REG_MODEM_CONFIG1=0x1D
REG_MODEM_CONFIG2=0x1E
REG_MODEM_CONFIG3=0x26
REG_VERSION     = 0x42

MODE_LONG_RANGE = 0x80
MODE_SLEEP      = 0x00
MODE_STDBY      = 0x01
MODE_TX         = 0x03
MODE_RX_CONT    = 0x05

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(NSS,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(RST,  GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SCK,  GPIO.OUT)
GPIO.setup(MOSI, GPIO.OUT)
GPIO.setup(MISO, GPIO.IN)
GPIO.setup(DIO0, GPIO.IN)


# ─── SPI ─────────────────────────────
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


# ─── INIT ─────────────────────────────
def reset_lora():
    GPIO.output(RST, GPIO.LOW)
    time.sleep(0.01)
    GPIO.output(RST, GPIO.HIGH)
    time.sleep(0.1)

def init_lora():
    reset_lora()

    if read_reg(REG_VERSION) != 0x12:
        raise RuntimeError("LoRa not detected")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
    time.sleep(0.1)

    # RX frequency = 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB, frf & 0xFF)

    write_reg(REG_FIFO_TX_BASE, 0x00)
    write_reg(REG_FIFO_RX_BASE, 0x00)

    write_reg(REG_MODEM_CONFIG1, 0x72)
    write_reg(REG_MODEM_CONFIG2, 0x74)
    write_reg(REG_MODEM_CONFIG3, 0x04)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

    print("✅ LoRa + BMP280 Ready")


# ─── SEND PACKET ─────────────────────
def send_packet(data_bytes):
    # Switch to TX = 434 MHz
    frf = int(434e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB, frf & 0xFF)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)
    write_reg(REG_FIFO_ADDR_PTR, 0x00)

    GPIO.output(NSS, GPIO.LOW)
    spi_transfer_byte(REG_FIFO | 0x80)
    for b in data_bytes:
        spi_transfer_byte(b)
    GPIO.output(NSS, GPIO.HIGH)

    write_reg(REG_PAYLOAD_LEN, len(data_bytes))
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_TX)

    time.sleep(0.3)

    # Back to RX = 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB, frf & 0xFF)


# ─── MAIN LOOP: listen and relay ─────
def receive_loop():
    print("📡 Listening + Relaying...\n")

    while True:
        irq = read_reg(REG_IRQ_FLAGS)

        if irq & 0x40:
            length   = read_reg(REG_RX_NB_BYTES)
            fifo_addr = read_reg(REG_FIFO_RX_CURR)
            write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

            payload  = read_fifo(length)
            raw_msg  = bytes(payload).decode('utf-8', errors='ignore')

            print("\n📦 RAW:", raw_msg)

            parts = raw_msg.strip().split(',')

            if len(parts) != 6:
                print("⚠️ Invalid format")
                write_reg(REG_IRQ_FLAGS, 0xFF)
                continue

            msg_id    = int(parts[0])
            timestamp = int(parts[1])
            lat       = parts[2]
            lon       = parts[3]

            # ─── BMP280 READ ─────────────────
            temp, pressure, altitude = read_bmp280()

            # ─── NEW PACKET (format your ESP32 expects) ───
            # FORMAT: msg_id,timestamp,lat,lon,type,rx_crc,temp,pressure,altitude
            new_crc = msg_id + timestamp

            new_msg = f"{msg_id},{timestamp},{lat},{lon},RELAYED,{new_crc},{temp},{pressure},{altitude}"

            print("🔁 Sending 9‑field packet:", new_msg)

            send_packet(new_msg.encode())

            write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
            write_reg(REG_IRQ_FLAGS, 0xFF)

        time.sleep(0.05)


# ─── MAIN ENTRY ──────────────────────
def main():
    print("=================================")
    print("   LoRa RELAY NODE + BMP280")
    print("=================================")

    init_lora()
    receive_loop()

if __name__ == "__main__":
    main()
