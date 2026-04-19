import time
import board
import adafruit_dht
import smbus2
import math
import RPi.GPIO as GPIO

from skyfield.api import load, EarthSatellite

# ─── LED SETUP ─────────────────────────
LED_RED, LED_GREEN, LED_BLUE = 23, 25, 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED, GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE, GPIO.OUT)

# ─── DHT11 ────────────────────────────
dht = adafruit_dht.DHT11(board.D24)

# ─── I2C ─────────────────────────────
bus = smbus2.SMBus(1)

# BMP280
BMP_ADDR = 0x76

# MPU6050
MPU_ADDR = 0x69
bus.write_byte_data(MPU_ADDR, 0x6B, 0x00)

# RTC
RTC_ADDR = 0x68

# ─── LoRa (reuse your existing functions) ─────────
# ⚠️ Use your previous SPI + send_packet() here

msg_id = 0

# ─── TLE (example ISS — replace with your satellite) ───
line1 = "1 25544U 98067A   24060.54834491  .00016717  00000+0  10270-3 0  9004"
line2 = "2 25544  51.6423  21.3737 0007417  85.1345  34.3152 15.50012345  1234"

ts = load.timescale()
sat = EarthSatellite(line1, line2)

# ─── Helpers ──────────────────────────
def get_rtc_time():
    d = bus.read_i2c_block_data(RTC_ADDR, 0x00, 3)
    s = (d[0] & 0x0F) + ((d[0] >> 4) * 10)
    m = (d[1] & 0x0F) + ((d[1] >> 4) * 10)
    h = (d[2] & 0x0F) + ((d[2] >> 4) * 10)
    return h*3600 + m*60 + s

def read_mpu():
    def rw(reg):
        h = bus.read_byte_data(MPU_ADDR, reg)
        l = bus.read_byte_data(MPU_ADDR, reg+1)
        v = (h<<8)+l
        return v-65536 if v>=0x8000 else v

    ax = rw(0x3B)/16384.0
    ay = rw(0x3D)/16384.0
    az = rw(0x3F)/16384.0

    return round(ax,2), round(ay,2), round(az,2)

def read_bmp():
    d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
    adc_P = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
    pressure = adc_P / 25600.0
    altitude = 44330*(1-(pressure/1013.25)**0.1903)
    return round(pressure,2), round(altitude,2)

def get_position():
    t = ts.now()
    geocentric = sat.at(t)
    subpoint = geocentric.subpoint()

    lat = subpoint.latitude.degrees
    lon = subpoint.longitude.degrees

    return round(lat,5), round(lon,5)

# ─── TELEMETRY SEND ───────────────────
def send_telemetry():
    global msg_id
    msg_id += 1

    try:
        GPIO.output(LED_RED, GPIO.LOW)

        timestamp = get_rtc_time()
        lat, lon = get_position()

        GPIO.output(LED_BLUE, GPIO.HIGH)

        temp = dht.temperature or 0
        hum  = dht.humidity or 0

        press, alt = read_bmp()
        ax, ay, az = read_mpu()

        crc = msg_id + timestamp

        msg = f"{msg_id},{timestamp},{lat},{lon},{temp},{hum},{press},{alt},{ax},{ay},{az},{crc}"

        print("📡 TX:", msg)

        GPIO.output(LED_GREEN, GPIO.HIGH)
        send_packet(msg.encode())   # ← your existing function
        GPIO.output(LED_GREEN, GPIO.LOW)

    except Exception as e:
        print("❌ ERROR:", e)
        GPIO.output(LED_RED, GPIO.HIGH)

# ─── EMERGENCY SEND (same format) ─────
def send_emergency(msg_type="RESCUE"):
    global msg_id
    msg_id += 1

    timestamp = get_rtc_time()
    lat, lon = get_position()

    crc = msg_id + timestamp

    msg = f"{msg_id},{timestamp},{lat},{lon},{msg_type},{crc}"

    print("🚨 EMERGENCY:", msg)

    send_packet(msg.encode())

# ─── MAIN LOOP ────────────────────────
print("🛰️ CubeSat Flight Code Started")

try:
    while True:
        send_telemetry()

        # Example: trigger emergency manually
        # send_emergency("MEDICAL")

        time.sleep(2)

except KeyboardInterrupt:
    GPIO.cleanup()
