import RPi.GPIO as GPIO
import time
import smbus2
import serial

# ─────────────────────────────────────
# PIN CONFIG (YOUR MAPPING)
# ─────────────────────────────────────
NSS  = 5
RST  = 22
DIO0 = 4
SCK  = 18
MISO = 19
MOSI = 23

LED_R = 27
LED_G = 25
LED_B = 16

DHT_PIN = 24
MOSFET  = 17

# ─────────────────────────────────────
# GPIO SETUP
# ─────────────────────────────────────
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup([NSS, RST, SCK, MOSI, LED_R, LED_G, LED_B, MOSFET], GPIO.OUT)
GPIO.setup(MISO, GPIO.IN)

GPIO.output(NSS, 1)
GPIO.output(SCK, 0)

# ─────────────────────────────────────
# I2C (BMP280)
# ─────────────────────────────────────
bus = smbus2.SMBus(1)
BMP_ADDR = 0x76

# ─────────────────────────────────────
# GPS
# ─────────────────────────────────────
gps = serial.Serial("/dev/serial0", 9600, timeout=1)

# ─────────────────────────────────────
# SPI BIT-BANG
# ─────────────────────────────────────
def spi_transfer(byte):
    recv = 0
    for i in range(8):
        GPIO.output(MOSI, (byte & (0x80 >> i)) != 0)
        GPIO.output(SCK, 1)
        time.sleep(0.00001)
        if GPIO.input(MISO):
            recv |= (0x80 >> i)
        GPIO.output(SCK, 0)
    return recv

def write_reg(reg, val):
    GPIO.output(NSS, 0)
    spi_transfer(reg | 0x80)
    spi_transfer(val)
    GPIO.output(NSS, 1)

def read_reg(reg):
    GPIO.output(NSS, 0)
    spi_transfer(reg & 0x7F)
    val = spi_transfer(0x00)
    GPIO.output(NSS, 1)
    return val

# ─────────────────────────────────────
# LORA INIT
# ─────────────────────────────────────
def init_lora():
    GPIO.output(RST, 0)
    time.sleep(0.01)
    GPIO.output(RST, 1)
    time.sleep(0.1)

    if read_reg(0x42) != 0x12:
        raise Exception("LoRa not detected")

    write_reg(0x01, 0x80)  # Sleep LoRa
    time.sleep(0.1)

    # 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(0x06, (frf >> 16) & 0xFF)
    write_reg(0x07, (frf >> 8) & 0xFF)
    write_reg(0x08, frf & 0xFF)

    # Match ESP32
    write_reg(0x1D, 0x72)
    write_reg(0x1E, 0x74)
    write_reg(0x26, 0x04)
    write_reg(0x1D, read_reg(0x1D) & 0xFE)
    write_reg(0x01, 0x81)  # Standby

# ─────────────────────────────────────
# SEND PACKET
# ─────────────────────────────────────
def send_packet(data):
    GPIO.output(LED_G, 1)

    write_reg(0x01, 0x81)
    write_reg(0x0D, 0x00)

    GPIO.output(NSS, 0)
    spi_transfer(0x80)
    for b in data:
        spi_transfer(b)
    GPIO.output(NSS, 1)

    write_reg(0x22, len(data))
    write_reg(0x01, 0x83)

    while not (read_reg(0x12) & 0x08):
        pass

    write_reg(0x12, 0xFF)
    write_reg(0x01, 0x85)

    GPIO.output(LED_G, 0)
    print("TX DONE")

# ─────────────────────────────────────
# BMP280 (SIMPLE)
# ─────────────────────────────────────
def read_bmp():
    try:
        d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
        adc_P = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
        adc_T = (d[3]<<12)|(d[4]<<4)|(d[5]>>4)

        temp = adc_T / 1000.0
        pressure = adc_P / 25600.0
        altitude = 44330*(1-(pressure/1013.25)**0.1903)

        return round(temp,2), round(pressure,2), round(altitude,2)
    except:
        GPIO.output(LED_R, 1)
        return None, None, None

# ─────────────────────────────────────
# DHT22
# ─────────────────────────────────────
def read_dht():
    try:
        import Adafruit_DHT
        h, t = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, DHT_PIN)
        return t, h
    except:
        return None, None

# ─────────────────────────────────────
# GPS
# ─────────────────────────────────────
def read_gps():
    try:
        line = gps.readline().decode(errors="ignore")
        if "$GPGGA" in line:
            parts = line.split(',')
            if parts[2] and parts[4]:
                lat = float(parts[2]) / 100
                lon = float(parts[4]) / 100
                GPIO.output(LED_B, 1)
                return lat, lon
        GPIO.output(LED_B, 0)
    except:
        pass
    return 0, 0

# ─────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────
msg_id = 0

def loop():
    global msg_id

    while True:
        msg_id += 1

        temp_bmp, press, alt = read_bmp()
        temp_dht, hum = read_dht()
        lat, lon = read_gps()

        if temp_bmp is None:
            print("❌ BMP FAIL")
            continue

        timestamp = int(time.time())
        crc = msg_id + timestamp

        msg = f"{msg_id},{timestamp},{lat},{lon},{temp_bmp},{press},{alt},{temp_dht},{hum},{crc}"

        print("📤 TX:", msg)

        send_packet(msg.encode())

        time.sleep(5)

# ─────────────────────────────────────
# START
# ─────────────────────────────────────
init_lora()
print("🚀 Full Sensor LoRa Node Started")

try:
    loop()
except KeyboardInterrupt:
    GPIO.cleanup()
