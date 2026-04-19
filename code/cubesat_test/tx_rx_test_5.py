import time
import smbus2
import math
import serial
import pynmea2
import RPi.GPIO as GPIO

# ─── LED SETUP ─────────────────────────
LED_RED, LED_GREEN, LED_BLUE = 23, 25, 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED, GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE, GPIO.OUT)

# ─── DHT11 ────────────────────────────
DHT_PIN = 24

def read_dht11():
    data = []

    GPIO.setup(DHT_PIN, GPIO.OUT)
    GPIO.output(DHT_PIN, GPIO.LOW)
    time.sleep(0.02)
    GPIO.output(DHT_PIN, GPIO.HIGH)
    GPIO.setup(DHT_PIN, GPIO.IN)

    while GPIO.input(DHT_PIN) == 1: pass
    while GPIO.input(DHT_PIN) == 0: pass
    while GPIO.input(DHT_PIN) == 1: pass

    for i in range(40):
        while GPIO.input(DHT_PIN) == 0: pass
        start = time.time()
        while GPIO.input(DHT_PIN) == 1: pass
        if (time.time() - start) > 0.00005:
            data.append(1)
        else:
            data.append(0)

    bytes_data = []
    for i in range(5):
        byte = 0
        for j in range(8):
            byte = (byte << 1) | data[i*8+j]
        bytes_data.append(byte)

    if (sum(bytes_data[:4]) & 0xFF) != bytes_data[4]:
        return None, None

    return bytes_data[2], bytes_data[0]

# ─── I2C SETUP ────────────────────────
bus = smbus2.SMBus(1)

BMP_ADDR = 0x76
MPU_ADDR = 0x69
RTC_ADDR = 0x68

bus.write_byte_data(MPU_ADDR, 0x6B, 0x00)

# ─── GPS SETUP ────────────────────────
ser = serial.Serial('/dev/serial0', 9600, timeout=1)

def read_gps():
    while True:
        line = ser.readline().decode('ascii', errors='ignore')
        if line.startswith(('$GPGGA', '$GNGGA')):
            try:
                msg = pynmea2.parse(line)
                if int(msg.gps_qual) > 0:
                    lat = float(msg.latitude)
                    lon = float(msg.longitude)
                    alt = float(msg.altitude)
                    GPIO.output(LED_BLUE, GPIO.HIGH)
                    return lat, lon, alt
            except:
                pass
        GPIO.output(LED_BLUE, GPIO.LOW)

# ─── RTC ──────────────────────────────
def get_time():
    d = bus.read_i2c_block_data(RTC_ADDR, 0x00, 3)
    s = (d[0]&0x0F)+((d[0]>>4)*10)
    m = (d[1]&0x0F)+((d[1]>>4)*10)
    h = (d[2]&0x0F)+((d[2]>>4)*10)
    return h*3600 + m*60 + s

# ─── MPU6050 ──────────────────────────
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

# ─── BMP280 (simplified) ──────────────
def read_bmp():
    d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
    adc = (d[0]<<12)|(d[1]<<4)|(d[2]>>4)
    pressure = adc / 25600.0
    altitude = 44330*(1-(pressure/1013.25)**0.1903)
    return round(pressure,2), round(altitude,2)

# ─── LoRa SEND ────────────────────────
def send_packet(data):
    # 🔴 PASTE YOUR WORKING LoRa send_packet() HERE
    pass

msg_id = 0

# ─── TELEMETRY ────────────────────────
def send_telemetry():
    global msg_id
    msg_id += 1

    try:
        GPIO.output(LED_RED, GPIO.LOW)

        timestamp = get_time()
        lat, lon, gps_alt = read_gps()

        temp, hum = read_dht11()
        if temp is None:
            raise Exception("DHT fail")

        press, bmp_alt = read_bmp()
        ax, ay, az = read_mpu()

        crc = msg_id + timestamp

        msg = f"{msg_id},{timestamp},{lat},{lon},{gps_alt},{temp},{hum},{press},{bmp_alt},{ax},{ay},{az},{crc}"

        print("📡", msg)

        GPIO.output(LED_GREEN, GPIO.HIGH)
        send_packet(msg.encode())
        GPIO.output(LED_GREEN, GPIO.LOW)

    except Exception as e:
        print("❌ ERROR:", e)
        GPIO.output(LED_RED, GPIO.HIGH)

# ─── EMERGENCY (same format as your system) ───
def send_emergency(msg_type="RESCUE"):
    global msg_id
    msg_id += 1

    timestamp = get_time()
    lat, lon, _ = read_gps()

    crc = msg_id + timestamp

    msg = f"{msg_id},{timestamp},{lat},{lon},{msg_type},{crc}"

    print("🚨", msg)
    send_packet(msg.encode())

# ─── MAIN LOOP ────────────────────────
print("🛰️ CubeSat Flight Code Started (GPS Mode)")

try:
    while True:
        send_telemetry()

        # Example manual trigger:
        # send_emergency("MEDICAL")

        time.sleep(2)

except KeyboardInterrupt:
    GPIO.cleanup()
    ser.close()
