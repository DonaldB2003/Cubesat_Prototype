import time
import smbus2
import math
import RPi.GPIO as GPIO
from skyfield.api import load, EarthSatellite

# ─── LED ─────────────────────────────
LED_RED, LED_GREEN, LED_BLUE = 23, 25, 16
GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED, GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE, GPIO.OUT)

# ─── DHT11 (RAW GPIO) ────────────────
DHT_PIN = 24

def read_dht11():
    data = []

    GPIO.setup(DHT_PIN, GPIO.OUT)
    GPIO.output(DHT_PIN, GPIO.LOW)
    time.sleep(0.02)
    GPIO.output(DHT_PIN, GPIO.HIGH)

    GPIO.setup(DHT_PIN, GPIO.IN)

    # Wait for response
    while GPIO.input(DHT_PIN) == 1:
        pass
    while GPIO.input(DHT_PIN) == 0:
        pass
    while GPIO.input(DHT_PIN) == 1:
        pass

    # Read 40 bits
    for i in range(40):
        while GPIO.input(DHT_PIN) == 0:
            pass

        start = time.time()

        while GPIO.input(DHT_PIN) == 1:
            pass

        duration = time.time() - start

        if duration > 0.00005:
            data.append(1)
        else:
            data.append(0)

    # Convert bits
    bytes_data = []
    for i in range(5):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | data[i*8 + j]
        bytes_data.append(byte)

    # Checksum
    if (bytes_data[0] + bytes_data[1] + bytes_data[2] + bytes_data[3]) & 0xFF != bytes_data[4]:
        return None, None

    return bytes_data[2], bytes_data[0]  # temp, humidity

# ─── I2C ─────────────────────────────
bus = smbus2.SMBus(1)

BMP_ADDR = 0x76
MPU_ADDR = 0x69
RTC_ADDR = 0x68

bus.write_byte_data(MPU_ADDR, 0x6B, 0x00)

# ─── TLE ─────────────────────────────
line1 = "1 25544U 98067A   24060.54834491  .00016717  00000+0  10270-3 0  9004"
line2 = "2 25544  51.6423  21.3737 0007417  85.1345  34.3152 15.50012345  1234"

ts = load.timescale()
sat = EarthSatellite(line1, line2)

# ─── Helpers ─────────────────────────
def get_time():
    d = bus.read_i2c_block_data(RTC_ADDR, 0x00, 3)
    s = (d[0] & 0x0F) + ((d[0] >> 4) * 10)
    m = (d[1] & 0x0F) + ((d[1] >> 4) * 10)
    h = (d[2] & 0x0F) + ((d[2] >> 4) * 10)
    return h*3600 + m*60 + s

def get_position():
    t = ts.now()
    geo = sat.at(t)
    sub = geo.subpoint()
    return round(sub.latitude.degrees,5), round(sub.longitude.degrees,5)

def read_mpu():
    def rw(r):
        h = bus.read_byte_data(MPU_ADDR, r)
        l = bus.read_byte_data(MPU_ADDR, r+1)
        v = (h<<8)+l
        return v-65536 if v>=0x8000 else v

    return round(rw(0x3B)/16384,2), round(rw(0x3D)/16384,2), round(rw(0x3F)/16384,2)

def read_bmp():
    d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
    adc = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
    pressure = adc / 25600.0
    altitude = 44330*(1-(pressure/1013.25)**0.1903)
    return round(pressure,2), round(altitude,2)

# ─── LoRa send (USE YOUR EXISTING) ───
def send_packet(data):
    # ⚠️ paste your working send_packet() here
    pass

msg_id = 0

# ─── TELEMETRY ───────────────────────
def send_telemetry():
    global msg_id
    msg_id += 1

    try:
        GPIO.output(LED_RED, GPIO.LOW)

        t = get_time()
        lat, lon = get_position()
        GPIO.output(LED_BLUE, GPIO.HIGH)

        temp, hum = read_dht11()
        if temp is None:
            raise Exception("DHT fail")

        press, alt = read_bmp()
        ax, ay, az = read_mpu()

        crc = msg_id + t

        msg = f"{msg_id},{t},{lat},{lon},{temp},{hum},{press},{alt},{ax},{ay},{az},{crc}"

        print("📡", msg)

        GPIO.output(LED_GREEN, GPIO.HIGH)
        send_packet(msg.encode())
        GPIO.output(LED_GREEN, GPIO.LOW)

    except Exception as e:
        print("❌", e)
        GPIO.output(LED_RED, GPIO.HIGH)

# ─── EMERGENCY ───────────────────────
def send_emergency(t="RESCUE"):
    global msg_id
    msg_id += 1

    ts_ = get_time()
    lat, lon = get_position()
    crc = msg_id + ts_

    msg = f"{msg_id},{ts_},{lat},{lon},{t},{crc}"

    send_packet(msg.encode())

# ─── MAIN ────────────────────────────
print("🛰️ CubeSat running (no board lib)")

try:
    while True:
        send_telemetry()
        time.sleep(2)

except KeyboardInterrupt:
    GPIO.cleanup()
