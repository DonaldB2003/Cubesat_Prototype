import time
import os
import smbus2
import serial
import pynmea2
import RPi.GPIO as GPIO

# ─────────────────────────────────────
# LED SETUP
# ─────────────────────────────────────
LED_RED, LED_GREEN, LED_BLUE = 23, 25, 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED, GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE, GPIO.OUT)

# ─────────────────────────────────────
# I2C BUS
# ─────────────────────────────────────
bus = smbus2.SMBus(1)

BMP_ADDR = 0x76
MPU_ADDR = 0x69
RTC_ADDR = 0x68

# ─────────────────────────────────────
# GPS
# ─────────────────────────────────────
ser = serial.Serial('/dev/serial0', 9600, timeout=1)

# ─────────────────────────────────────
# I2C SELF HEALING
# ─────────────────────────────────────
SCL = 3
SDA = 2

def recover_i2c():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SCL, GPIO.OUT)
    GPIO.setup(SDA, GPIO.IN)

    # Clock pulses to free stuck device
    for i in range(20):
        GPIO.output(SCL, 1)
        time.sleep(0.001)
        GPIO.output(SCL, 0)
        time.sleep(0.001)

    # STOP condition
    GPIO.setup(SDA, GPIO.OUT)
    GPIO.output(SDA, 0)
    GPIO.output(SCL, 1)
    time.sleep(0.001)
    GPIO.output(SDA, 1)

    GPIO.cleanup()

def reset_i2c_driver():
    os.system("sudo rmmod i2c_bcm2835")
    os.system("sudo modprobe i2c_bcm2835")

# ─────────────────────────────────────
# GPS READ
# ─────────────────────────────────────
def read_gps():
    while True:
        line = ser.readline().decode(errors='ignore')
        if line.startswith(('$GPGGA', '$GNGGA')):
            try:
                msg = pynmea2.parse(line)
                if int(msg.gps_qual) > 0:
                    GPIO.output(LED_BLUE, GPIO.HIGH)
                    return float(msg.latitude), float(msg.longitude), float(msg.altitude)
            except:
                pass
        GPIO.output(LED_BLUE, GPIO.LOW)

# ─────────────────────────────────────
# RTC
# ─────────────────────────────────────
def get_time():
    d = bus.read_i2c_block_data(RTC_ADDR, 0x00, 3)
    s = (d[0] & 0x0F) + ((d[0] >> 4) * 10)
    m = (d[1] & 0x0F) + ((d[1] >> 4) * 10)
    h = (d[2] & 0x0F) + ((d[2] >> 4) * 10)
    return h*3600 + m*60 + s

# ─────────────────────────────────────
# MPU6050
# ─────────────────────────────────────
def read_mpu():
    def rw(r):
        h = bus.read_byte_data(MPU_ADDR, r)
        l = bus.read_byte_data(MPU_ADDR, r+1)
        v = (h<<8)+l
        return v-65536 if v>=0x8000 else v

    ax = rw(0x3B)/16384.0
    ay = rw(0x3D)/16384.0
    az = rw(0x3F)/16384.0

    return round(ax,2), round(ay,2), round(az,2)

# ─────────────────────────────────────
# BMP280 (simplified)
# ─────────────────────────────────────
def read_bmp():
    d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
    adc = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
    pressure = adc / 25600.0
    altitude = 44330*(1-(pressure/1013.25)**0.1903)
    return round(pressure,2), round(altitude,2)

# ─────────────────────────────────────
# DHT11 (simple fallback safe version)
# ─────────────────────────────────────
DHT_PIN = 24

def read_dht11():
    try:
        import adafruit_dht
        import board
        dht = adafruit_dht.DHT11(board.D24)
        t = dht.temperature
        h = dht.humidity
        return t, h
    except:
        return None, None

# ─────────────────────────────────────
# LoRa (YOU ALREADY HAVE THIS)
# ─────────────────────────────────────
def send_packet(data):
    pass  # <-- paste your working LoRa function here

# ─────────────────────────────────────
# SAFE SENSOR READ WRAPPER
# ─────────────────────────────────────
def safe_read(func, name):
    try:
        return func()
    except Exception as e:
        print(f"❌ {name} failed:", e)
        GPIO.output(LED_RED, GPIO.HIGH)

        recover_i2c()
        reset_i2c_driver()

        return None

# ─────────────────────────────────────
# TELEMETRY
# ─────────────────────────────────────
msg_id = 0

def send_telemetry():
    global msg_id
    msg_id += 1

    try:
        GPIO.output(LED_RED, GPIO.LOW)

        t = get_time()
        lat, lon, alt = read_gps()

        temp, hum = safe_read(read_dht11, "DHT11")
        press, bmp_alt = safe_read(read_bmp, "BMP280")
        ax, ay, az = safe_read(read_mpu, "MPU6050")

        if None in [temp, hum, press, bmp_alt, ax, ay, az]:
            raise Exception("Sensor failure")

        crc = msg_id + t

        msg = f"{msg_id},{t},{lat},{lon},{alt},{temp},{hum},{press},{bmp_alt},{ax},{ay},{az},{crc}"

        print("📡 TX:", msg)

        GPIO.output(LED_GREEN, GPIO.HIGH)
        send_packet(msg.encode())
        GPIO.output(LED_GREEN, GPIO.LOW)

    except Exception as e:
        print("🚨 SYSTEM ERROR:", e)
        GPIO.output(LED_RED, GPIO.HIGH)

# ─────────────────────────────────────
# EMERGENCY
# ─────────────────────────────────────
def send_emergency(t="RESCUE"):
    global msg_id
    msg_id += 1

    timestamp = get_time()
    lat, lon, alt = read_gps()

    crc = msg_id + timestamp

    msg = f"{msg_id},{timestamp},{lat},{lon},{t},{crc}"

    send_packet(msg.encode())

# ─────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────
print("🛰️ Self-healing CubeSat started")

try:
    while True:
        send_telemetry()
        time.sleep(2)

except KeyboardInterrupt:
    GPIO.cleanup()
    ser.close()
