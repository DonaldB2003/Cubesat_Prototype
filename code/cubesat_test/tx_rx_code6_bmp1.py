import RPi.GPIO as GPIO
import time
import smbus2

# ─── PINOUT ─────────────────────────────
NSS  = 5
RST  = 22
SCK  = 18
MISO = 19
MOSI = 23

# ─── REGISTERS ──────────────────────────
REG_FIFO          = 0x00
REG_OP_MODE       = 0x01
REG_FRF_MSB       = 0x06
REG_FRF_MID       = 0x07
REG_FRF_LSB       = 0x08
REG_FIFO_ADDR_PTR = 0x0D
REG_FIFO_RX_CURR  = 0x10
REG_IRQ_FLAGS     = 0x12
REG_RX_NB_BYTES   = 0x13
REG_PAYLOAD_LEN   = 0x22
REG_VERSION       = 0x42

MODE_LONG_RANGE = 0x80
MODE_SLEEP      = 0x00
MODE_STDBY      = 0x01
MODE_TX         = 0x03
MODE_RX_CONT    = 0x05

# ─── GPIO SETUP ─────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup(NSS, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(RST, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(SCK, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MOSI, GPIO.OUT, initial=GPIO.LOW)
GPIO.setup(MISO, GPIO.IN)

# ─── SOFTWARE SPI ───────────────────────
def spi_transfer_byte(data):
    received = 0
    for i in range(8):
        GPIO.output(MOSI, (data & (0x80 >> i)) != 0)
        GPIO.output(SCK, 1)
        if GPIO.input(MISO):
            received |= (0x80 >> i)
        GPIO.output(SCK, 0)
    return received

def write_reg(reg, val):
    GPIO.output(NSS, 0)
    spi_transfer_byte(reg | 0x80)
    spi_transfer_byte(val)
    GPIO.output(NSS, 1)

def read_reg(reg):
    GPIO.output(NSS, 0)
    spi_transfer_byte(reg & 0x7F)
    val = spi_transfer_byte(0x00)
    GPIO.output(NSS, 1)
    return val

def read_fifo(length):
    data = []
    GPIO.output(NSS, 0)
    spi_transfer_byte(REG_FIFO & 0x7F)
    for _ in range(length):
        data.append(spi_transfer_byte(0x00))
    GPIO.output(NSS, 1)
    return data

# ─── LORA INIT ─────────────────────────
def init_lora():
    GPIO.output(RST, 0)
    time.sleep(0.01)
    GPIO.output(RST, 1)
    time.sleep(0.1)

    if read_reg(REG_VERSION) != 0x12:
        raise RuntimeError("LoRa not detected")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP)
    time.sleep(0.1)

    # 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8) & 0xFF)
    write_reg(REG_FRF_LSB, frf & 0xFF)

    # Match ESP32 settings
    write_reg(0x1D, 0x72)
    write_reg(0x1E, 0x74)
    write_reg(0x26, 0x04)

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
    print("✅ LoRa Ready")

# ─── BMP280 ────────────────────────────
bus = smbus2.SMBus(1)
BMP_ADDR = 0x76

cal = bus.read_i2c_block_data(BMP_ADDR, 0x88, 24)

def u16(i): return (cal[i+1] << 8) | cal[i]
def s16(i): v = u16(i); return v - 65536 if v > 32767 else v

dig_T1 = u16(0); dig_T2 = s16(2); dig_T3 = s16(4)
dig_P1 = u16(6)
dig_P2 = s16(8); dig_P3 = s16(10); dig_P4 = s16(12)
dig_P5 = s16(14); dig_P6 = s16(16); dig_P7 = s16(18)
dig_P8 = s16(20); dig_P9 = s16(22)

bus.write_byte_data(BMP_ADDR, 0xF4, 0x27)
bus.write_byte_data(BMP_ADDR, 0xF5, 0xA0)

def read_bmp():
    try:
        d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)

        adc_P = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
        adc_T = (d[3]<<12)|(d[4]<<4)|(d[5]>>4)

        var1 = ((adc_T/16384)-(dig_T1/1024))*dig_T2
        var2 = ((adc_T/131072)-(dig_T1/8192))**2 * dig_T3
        t_fine = var1+var2
        temp = t_fine/5120

        var1 = t_fine/2 - 64000
        var2 = var1*var1*dig_P6/32768
        var2 += var1*dig_P5*2
        var2 = var2/4 + dig_P4*65536
        var1 = (dig_P3*var1*var1/524288 + dig_P2*var1)/524288
        var1 = (1 + var1/32768)*dig_P1

        pressure = 1048576 - adc_P
        pressure = (pressure - var2/4096)*6250/var1
        pressure /= 100

        altitude = 44330*(1-(pressure/1013.25)**0.1903)

        return round(temp,2), round(pressure,2), round(altitude,2)

    except:
        return None, None, None

# ─── SEND ──────────────────────────────
def send_packet(data):
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY)
    write_reg(REG_FIFO_ADDR_PTR, 0)

    GPIO.output(NSS, 0)
    spi_transfer_byte(REG_FIFO | 0x80)
    for b in data:
        spi_transfer_byte(b)
    GPIO.output(NSS, 1)

    write_reg(REG_PAYLOAD_LEN, len(data))
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_TX)

    while not (read_reg(REG_IRQ_FLAGS) & 0x08):
        pass

    write_reg(REG_IRQ_FLAGS, 0xFF)
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

# ─── MAIN LOOP ─────────────────────────
def loop():
    last_send = 0

    while True:
        irq = read_reg(REG_IRQ_FLAGS)

        # ─── RECEIVE ─────────────────────
        if irq & 0x40:
            length = read_reg(REG_RX_NB_BYTES)
            fifo_addr = read_reg(REG_FIFO_RX_CURR)
            write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

            payload = read_fifo(length)
            msg = bytes(payload).decode(errors='ignore')

            print("📥 RX:", msg)

            # RELAY
            parts = msg.split(',')
            if len(parts) >= 6 and parts[4] != "RELAYED":
                parts[4] = "RELAYED"
                new_msg = ",".join(parts)

                print("🔁 RELAY:", new_msg)
                send_packet(new_msg.encode())

            write_reg(REG_IRQ_FLAGS, 0xFF)

        # ─── PERIODIC SENSOR TX ──────────
        if time.time() - last_send > 5:
            temp, press, alt = read_bmp()

            if temp is not None:
                msg_id = int(time.time())
                crc = msg_id + msg_id

                msg = f"{msg_id},{msg_id},{temp},{press},{alt},BASE,{crc}"
                print("📤 TX:", msg)

                send_packet(msg.encode())
            else:
                print("❌ BMP FAIL")

            last_send = time.time()

        time.sleep(0.05)

# ─── START ─────────────────────────────
init_lora()
print("🚀 Relay + Sensor Node Started")

loop()
