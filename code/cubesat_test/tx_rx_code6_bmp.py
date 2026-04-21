import time
import os
import smbus2
import serial
import pynmea2
import RPi.GPIO as GPIO

# ─────────────────────────────────────
# LED SETUP
# ─────────────────────────────────────
LED_RED, LED_GREEN, LED_BLUE = 27, 25, 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED, GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE, GPIO.OUT)

# ─────────────────────────────────────
# I2C
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
# BMP280 INIT (CALIBRATED)
# ─────────────────────────────────────
cal = bus.read_i2c_block_data(BMP_ADDR, 0x88, 24)

def u16(i): return (cal[i+1] << 8) | cal[i]
def s16(i): v = u16(i); return v - 65536 if v > 32767 else v

dig_T1 = u16(0);  dig_T2 = s16(2);  dig_T3 = s16(4)
dig_P1 = u16(6)
dig_P2 = s16(8);  dig_P3 = s16(10); dig_P4 = s16(12)
dig_P5 = s16(14); dig_P6 = s16(16); dig_P7 = s16(18)
dig_P8 = s16(20); dig_P9 = s16(22)

bus.write_byte_data(BMP_ADDR, 0xF4, 0x27)
bus.write_byte_data(BMP_ADDR, 0xF5, 0xA0)
time.sleep(0.5)

# ─────────────────────────────────────
# BMP280 READ
# ─────────────────────────────────────
def read_bmp280():
    try:
        d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)

        adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)

        var1 = ((adc_T / 16384.0) - (dig_T1 / 1024.0)) * dig_T2
        var2 = ((adc_T / 131072.0) - (dig_T1 / 8192.0)) ** 2 * dig_T3
        t_fine = var1 + var2
        bmp_temp = t_fine / 5120.0

        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * dig_P6 / 32768.0
        var2 = var2 + var1 * dig_P5 * 2.0
        var2 = var2 / 4.0 + dig_P4 * 65536.0
        var1 = (dig_P3 * var1 * var1 / 524288.0 + dig_P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * dig_P1

        if var1 == 0:
            return None, None, None

        pressure = 1048576.0 - adc_P
        pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
        pressure = pressure / 100.0

        altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** (1.0 / 5.255))

        return round(bmp_temp,2), round(pressure,2), round(altitude,2)

    except:
        return None, None, None

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
# DHT11
# ─────────────────────────────────────
def read_dht11():
    try:
        import adafruit_dht
        import board
        dht = adafruit_dht.DHT11(board.D24)
        return dht.temperature, dht.humidity
    except:
        return None, None

# ─────────────────────────────────────
# GPS
# ─────────────────────────────────────
def read_gps(timeout=5):
    start = time.time()
    while time.time() - start < timeout:
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
    return None, None, None

# ─────────────────────────────────────
# SAFE READ
# ─────────────────────────────────────
def safe_read(func):
    try:
        return func()
    except:
        GPIO.output(LED_RED, GPIO.HIGH)
        return None

# ─────────────────────────────────────
# LORA SEND (PUT YOUR FUNCTION)
# ─────────────────────────────────────
def send_packet(data):
    pass

# ─────────────────────────────────────
# TELEMETRY
# ─────────────────────────────────────
msg_id = 0

def send_telemetry():
    global msg_id
    msg_id += 1

    GPIO.output(LED_RED, GPIO.LOW)

    t = int(time.time())

    lat, lon, gps_alt = read_gps()
    dht_temp, hum = safe_read(read_dht11)
    bmp_temp, press, bmp_alt = safe_read(read_bmp280)
    ax, ay, az = safe_read(read_mpu)

    if None in [lat, lon, gps_alt, dht_temp, hum, bmp_temp, press, bmp_alt, ax, ay, az]:
        print("❌ Sensor failure")
        GPIO.output(LED_RED, GPIO.HIGH)
        return

    crc = msg_id + t

    msg = f"{msg_id},{t},{lat},{lon},{gps_alt},{dht_temp},{hum},{bmp_temp},{press},{bmp_alt},{ax},{ay},{az},{crc}"

    print("📡 TX:", msg)

    GPIO.output(LED_GREEN, GPIO.HIGH)
    send_packet(msg.encode())
    GPIO.output(LED_GREEN, GPIO.LOW)

# ─────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────
print("🛰️ Telemetry system started")

try:
    while True:
        send_telemetry()
        time.sleep(2)

except KeyboardInterrupt:
    GPIO.cleanup()
    ser.close()
