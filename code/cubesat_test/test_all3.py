import RPi.GPIO as GPIO
import time
import smbus2
import serial

# ═══════════════════════════════════════════════════
#  PIN CONFIG
# ═══════════════════════════════════════════════════
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

# ═══════════════════════════════════════════════════
#  REGISTER MAP
# ═══════════════════════════════════════════════════
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
REG_PA_CONFIG     = 0x09
REG_VERSION       = 0x42

MODE_LONG_RANGE   = 0x80
MODE_SLEEP        = 0x00
MODE_STDBY        = 0x01
MODE_TX           = 0x03
MODE_RX_CONT      = 0x05

# ═══════════════════════════════════════════════════
#  GPIO SETUP
# ═══════════════════════════════════════════════════
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

GPIO.setup([NSS, RST, SCK, MOSI, LED_R, LED_G, LED_B, MOSFET], GPIO.OUT)
GPIO.setup([MISO, DIO0], GPIO.IN)

GPIO.output(NSS,   GPIO.HIGH)
GPIO.output(SCK,   GPIO.LOW)
GPIO.output(LED_R, GPIO.LOW)
GPIO.output(LED_G, GPIO.LOW)
GPIO.output(LED_B, GPIO.LOW)

# ═══════════════════════════════════════════════════
#  I2C — BMP280 (0x76) + MPU6050 (0x68) share bus 1
# ═══════════════════════════════════════════════════
bus      = smbus2.SMBus(1)
BMP_ADDR = 0x76
MPU_ADDR = 0x69          # AD0 pin high -> 0x69 (AD0 low -> 0x68)

def load_bmp280_calibration():
    cal = bus.read_i2c_block_data(BMP_ADDR, 0x88, 24)

    def u16(i): return (cal[i+1] << 8) | cal[i]
    def s16(i): v = u16(i); return v - 65536 if v > 32767 else v

    c = {
        'T1': u16(0),  'T2': s16(2),  'T3': s16(4),
        'P1': u16(6),  'P2': s16(8),  'P3': s16(10),
        'P4': s16(12), 'P5': s16(14), 'P6': s16(16),
        'P7': s16(18), 'P8': s16(20), 'P9': s16(22),
    }

    bus.write_byte_data(BMP_ADDR, 0xF4, 0x27)
    bus.write_byte_data(BMP_ADDR, 0xF5, 0xA0)
    time.sleep(0.5)
    print("✅ BMP280 calibration loaded")
    return c

bmp_cal = load_bmp280_calibration()

def read_bmp():
    try:
        d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)
        adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)

        T1=bmp_cal['T1']; T2=bmp_cal['T2']; T3=bmp_cal['T3']
        var1 = ((adc_T / 16384.0) - (T1 / 1024.0)) * T2
        var2 = ((adc_T / 131072.0) - (T1 / 8388608.0)) ** 2 * T3
        t_fine = var1 + var2
        temp = t_fine / 5120.0

        P1=bmp_cal['P1']; P2=bmp_cal['P2']; P3=bmp_cal['P3']
        P4=bmp_cal['P4']; P5=bmp_cal['P5']; P6=bmp_cal['P6']
        P7=bmp_cal['P7']; P8=bmp_cal['P8']; P9=bmp_cal['P9']

        var1 = t_fine / 2.0 - 64000.0
        var2 = var1 * var1 * P6 / 32768.0
        var2 = var2 + var1 * P5 * 2.0
        var2 = var2 / 4.0 + P4 * 65536.0
        var1 = (P3 * var1 * var1 / 524288.0 + P2 * var1) / 524288.0
        var1 = (1.0 + var1 / 32768.0) * P1

        if var1 == 0:
            return None, None, None

        pressure = 1048576.0 - adc_P
        pressure = ((pressure - var2 / 4096.0) * 6250.0) / var1
        var1 = P9 * pressure * pressure / 2147483648.0
        var2 = pressure * P8 / 32768.0
        pressure = (pressure + (var1 + var2 + P7) / 16.0) / 100.0

        altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903)

        return round(temp, 2), round(pressure, 2), round(altitude, 2)

    except Exception as e:
        print(f"❌ BMP error: {e}")
        return None, None, None

# ═══════════════════════════════════════════════════
#  MPU6050 — accelerometer (g) + gyroscope (deg/s)
# ═══════════════════════════════════════════════════
MPU_PWR_MGMT_1   = 0x6B
MPU_WHO_AM_I     = 0x75
MPU_ACCEL_XOUT_H = 0x3B
MPU_ACCEL_CONFIG = 0x1C
MPU_GYRO_CONFIG  = 0x1B

ACCEL_SCALE = 16384.0    # LSB per g        (range +/-2 g)
GYRO_SCALE  = 131.0      # LSB per deg/s    (range +/-250 deg/s)

# Offsets from mpu6050_test.py (sensor flat and still, Z up).
# AZ_OFF already has the 1 g of gravity removed.
AX_OFF = -0.0842
AY_OFF = -0.1885
AZ_OFF =  0.0105
GX_OFF = -0.7912
GY_OFF =  4.2234
GZ_OFF =  0.2652

mpu_ok = False

def init_mpu6050():
    global mpu_ok
    try:
        bus.write_byte_data(MPU_ADDR, MPU_PWR_MGMT_1, 0x00)   # wake up
        time.sleep(0.1)
        bus.write_byte_data(MPU_ADDR, MPU_ACCEL_CONFIG, 0x00) # +/-2 g
        bus.write_byte_data(MPU_ADDR, MPU_GYRO_CONFIG,  0x00) # +/-250 deg/s

        who = bus.read_byte_data(MPU_ADDR, MPU_WHO_AM_I)
        if who not in (0x68, 0x69, 0x70, 0x71, 0x72):  # some clones report other IDs
            print(f"⚠️ MPU6050 unexpected WHO_AM_I: 0x{who:02X} (continuing)")
        mpu_ok = True
        print("✅ MPU6050 ready")
    except Exception as e:
        mpu_ok = False
        print(f"⚠️ MPU6050 init failed: {e} (will send zeros)")

def read_mpu6050():
    if not mpu_ok:
        return None
    try:
        d = bus.read_i2c_block_data(MPU_ADDR, MPU_ACCEL_XOUT_H, 14)

        def s16(h, l):
            v = (h << 8) | l
            return v - 65536 if v > 32767 else v

        ax = s16(d[0],  d[1])  / ACCEL_SCALE - AX_OFF
        ay = s16(d[2],  d[3])  / ACCEL_SCALE - AY_OFF
        az = s16(d[4],  d[5])  / ACCEL_SCALE - AZ_OFF
        # d[6], d[7] = temperature (not sent)
        gx = s16(d[8],  d[9])  / GYRO_SCALE - GX_OFF
        gy = s16(d[10], d[11]) / GYRO_SCALE - GY_OFF
        gz = s16(d[12], d[13]) / GYRO_SCALE - GZ_OFF

        return (round(ax, 2), round(ay, 2), round(az, 2),
                round(gx, 1), round(gy, 1), round(gz, 1))
    except Exception as e:
        print(f"❌ MPU6050 error: {e}")
        return None

init_mpu6050()

# ═══════════════════════════════════════════════════
#  DHT11 — USING ADAFRUIT LIBRARY (STABLE)
# ═══════════════════════════════════════════════════
def read_dht():
    try:
        import Adafruit_DHT
        h, t = Adafruit_DHT.read_retry(Adafruit_DHT.DHT11, DHT_PIN)

        if h is not None and t is not None:
            return round(t, 2), round(h, 2)

        else:
            print("⚠️ DHT11 read failed")
            return None, None

    except Exception as e:
        print(f"⚠️ DHT read error: {e}")
        return None, None

# ═══════════════════════════════════════════════════
#  GPS
# ═══════════════════════════════════════════════════
try:
    gps_serial = serial.Serial("/dev/serial0", 9600, timeout=1)
    print("✅ GPS serial opened")
except Exception as e:
    print(f"⚠️ GPS init failed: {e}")
    gps_serial = None

def nmea_to_decimal(val_str, direction):
    try:
        val     = float(val_str)
        degrees = int(val / 100)
        minutes = val - degrees * 100
        decimal = degrees + minutes / 60.0
        if direction in ('S', 'W'):
            decimal = -decimal
        return round(decimal, 6)
    except:
        return 0.0

def read_gps():
    if gps_serial is None:
        return 0.0, 0.0
    try:
        for _ in range(10):
            line = gps_serial.readline().decode(errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                parts = line.split(',')
                if len(parts) >= 6 and parts[2] and parts[4]:
                    lat = nmea_to_decimal(parts[2], parts[3])
                    lon = nmea_to_decimal(parts[4], parts[5])
                    if lat != 0.0 or lon != 0.0:
                        GPIO.output(LED_B, GPIO.HIGH)
                        return lat, lon
        GPIO.output(LED_B, GPIO.LOW)
    except Exception as e:
        print(f"⚠️ GPS error: {e}")
    return 0.0, 0.0

# ═══════════════════════════════════════════════════
#  SPI BIT-BANG
# ═══════════════════════════════════════════════════
def spi_byte(data):
    recv = 0
    for i in range(8):
        GPIO.output(MOSI, (data & (0x80 >> i)) != 0)
        GPIO.output(SCK, GPIO.HIGH)
        time.sleep(0.00001)
        if GPIO.input(MISO):
            recv |= (0x80 >> i)
        GPIO.output(SCK, GPIO.LOW)
        time.sleep(0.00001)
    return recv

def write_reg(reg, val):
    GPIO.output(NSS, GPIO.LOW)
    spi_byte(reg | 0x80)
    spi_byte(val)
    GPIO.output(NSS, GPIO.HIGH)
    time.sleep(0.000005)

def read_reg(reg):
    GPIO.output(NSS, GPIO.LOW)
    spi_byte(reg & 0x7F)
    val = spi_byte(0x00)
    GPIO.output(NSS, GPIO.HIGH)
    time.sleep(0.000005)
    return val

def read_fifo(length):
    data = []
    GPIO.output(NSS, GPIO.LOW)
    spi_byte(REG_FIFO & 0x7F)
    for _ in range(length):
        data.append(spi_byte(0x00))
    GPIO.output(NSS, GPIO.HIGH)
    return data

# ═══════════════════════════════════════════════════
#  SET FREQUENCY
# ═══════════════════════════════════════════════════
def set_frequency(freq_hz):
    frf = int(freq_hz / (32e6 / 524288))
    write_reg(REG_FRF_MSB, (frf >> 16) & 0xFF)
    write_reg(REG_FRF_MID, (frf >> 8)  & 0xFF)
    write_reg(REG_FRF_LSB,  frf        & 0xFF)

# ═══════════════════════════════════════════════════
#  LORA INIT
# ═══════════════════════════════════════════════════
def init_lora():
    print("🔄 Resetting LoRa...")
    GPIO.output(RST, GPIO.LOW);  time.sleep(0.01)
    GPIO.output(RST, GPIO.HIGH); time.sleep(0.1)

    ver = read_reg(REG_VERSION)
    if ver != 0x12:
        raise RuntimeError(f"LoRa not found! Got 0x{ver:02X}")

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_SLEEP); time.sleep(0.1)

    set_frequency(433e6)

    write_reg(REG_FIFO_TX_BASE,  0x00)
    write_reg(REG_FIFO_RX_BASE,  0x00)

    write_reg(REG_MODEM_CONFIG1, 0x72)   # BW=125kHz, CR=4/5, explicit header
    write_reg(REG_MODEM_CONFIG2, 0x74)   # SF=7, RxCrcOn=1
    write_reg(REG_MODEM_CONFIG3, 0x04)   # AgcAutoOn

    write_reg(REG_PA_CONFIG, 0x8F)       # PA_BOOST +17dBm
    write_reg(0x23, 0xFF)                # max payload length

    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)

    print("✅ LoRa ready — 433 MHz, SF7, BW125, CR4/5, CRC ON")

# ═══════════════════════════════════════════════════
#  CRC16
# ═══════════════════════════════════════════════════
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF

# ═══════════════════════════════════════════════════
#  SEND MERGED PACKET TO GROUND STATION
#
#  FORMAT (21 fields):
#  relay_id, unix_time,
#  rescue_lat, rescue_lon, emergency_type,
#  rescue_msg_id, rescue_millis,
#  bmp_temp, pressure, altitude,
#  dht_temp, humidity,
#  pi_lat, pi_lon,
#  accel_x, accel_y, accel_z,      (g)        <- NEW
#  gyro_x,  gyro_y,  gyro_z,       (deg/s)    <- NEW
#  crc16
#
#  Fields 1-14 are unchanged; the MPU6050 values sit
#  between pi_lon and the CRC.
# ═══════════════════════════════════════════════════
relay_id = 0

def send_merged_packet(rescue_parts, bmp_temp, pressure, altitude,
                        dht_temp, humidity, pi_lat, pi_lon, mpu):
    global relay_id
    relay_id += 1

    rescue_msg_id  = rescue_parts[0]
    rescue_millis  = rescue_parts[1]
    rescue_lat     = rescue_parts[2]
    rescue_lon     = rescue_parts[3]
    emergency_type = rescue_parts[4]

    ax, ay, az, gx, gy, gz = mpu

    unix_time = int(time.time())

    payload = (
        f"{relay_id},{unix_time},"
        f"{rescue_lat},{rescue_lon},{emergency_type},"
        f"{rescue_msg_id},{rescue_millis},"
        f"{bmp_temp},{pressure},{altitude},"
        f"{dht_temp},{humidity},"
        f"{pi_lat},{pi_lon},"
        f"{ax},{ay},{az},{gx},{gy},{gz}"
    )

    crc = crc16(payload.encode())
    full_msg = f"{payload},{crc}"

    print(f"\n📤 Sending merged packet [{relay_id}] ({len(full_msg)} bytes):")
    print(f"   {full_msg}\n")

    if len(full_msg) > 255:
        print("⚠️ Packet longer than 255 bytes — LoRa will truncate it!")

    # ── Switch to TX ──────────────────────────────
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_STDBY); time.sleep(0.01)
    write_reg(REG_FIFO_TX_BASE,  0x00)
    write_reg(REG_FIFO_ADDR_PTR, 0x00)

    GPIO.output(LED_G, GPIO.HIGH)

    encoded = full_msg.encode()
    GPIO.output(NSS, GPIO.LOW)
    spi_byte(REG_FIFO | 0x80)
    for b in encoded:
        spi_byte(b)
    GPIO.output(NSS, GPIO.HIGH)

    write_reg(REG_PAYLOAD_LEN, len(encoded))
    write_reg(REG_IRQ_FLAGS, 0xFF)
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_TX)

    # Wait for TxDone
    start = time.time()
    while True:
        if read_reg(REG_IRQ_FLAGS) & 0x08:
            break
        if time.time() - start > 5:
            print("⚠️ TX timeout!")
            GPIO.output(LED_R, GPIO.HIGH)
            time.sleep(0.1)
            GPIO.output(LED_R, GPIO.LOW)
            break

    write_reg(REG_IRQ_FLAGS, 0xFF)
    GPIO.output(LED_G, GPIO.LOW)

    # ── Back to RX ────────────────────────────────
    write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
    print("✅ TX done — back to RX")

def receive_loop():
    print("\n📡 Relay node active — listening for rescue tower...\n")

    last_rx_time = time.time()

    while True:
        irq = read_reg(REG_IRQ_FLAGS)
        rescue_parts = None

        # ──────────────── CHECK FOR INCOMING PACKET ────────────────
        if irq & 0x40:  # RxDone

            if irq & 0x20:
                print("⚠️ CRC error — discarding")
            else:
                length    = read_reg(REG_RX_NB_BYTES)
                fifo_addr = read_reg(REG_FIFO_RX_CURR)
                write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

                payload = read_fifo(length)
                raw_msg = bytes(payload).decode('utf-8', errors='ignore').strip()

                print(f"📦 Received: {raw_msg}")

                parts = raw_msg.split(',')

                if len(parts) == 6:
                    rescue_parts = parts
                    last_rx_time = time.time()
                else:
                    print("⚠️ Invalid rescue packet")

            write_reg(REG_IRQ_FLAGS, 0xFF)

        # ──────────────── IF NO DATA → USE ZERO VALUES ────────────────
        if rescue_parts is None:
            rescue_parts = ["0", "0", "0.0", "0.0", "NONE", "0"]

        # ──────────────── READ SENSORS ALWAYS ────────────────
        bmp_temp, pressure, altitude = read_bmp()
        dht_temp, humidity           = read_dht()
        pi_lat, pi_lon              = read_gps()
        mpu                          = read_mpu6050()

        if bmp_temp  is None: bmp_temp  = 0.0
        if pressure  is None: pressure  = 0.0
        if altitude  is None: altitude  = 0.0
        if dht_temp  is None: dht_temp  = 0.0
        if humidity  is None: humidity  = 0.0
        if mpu       is None: mpu       = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

        print(f"📊 Sending Sensor Data (with fallback):")
        print(f"   BMP280: {bmp_temp}°C, {pressure}hPa, {altitude}m")
        print(f"   DHT11 : {dht_temp}°C, {humidity}%")
        print(f"   GPS   : {pi_lat}, {pi_lon}")
        print(f"   MPU6050 accel(g): {mpu[0]}, {mpu[1]}, {mpu[2]}  "
              f"gyro(deg/s): {mpu[3]}, {mpu[4]}, {mpu[5]}")

        # ──────────────── ALWAYS SEND ────────────────
        send_merged_packet(
            rescue_parts,
            bmp_temp, pressure, altitude,
            dht_temp, humidity,
            pi_lat, pi_lon,
            mpu
        )

        time.sleep(2)   # adjust (important to avoid spam)

# ═══════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════
def main():
    print("=" * 52)
    print("   🛰️  LoRa RELAY NODE  —  Rescue + Sensors + IMU")
    print("=" * 52)

    init_lora()
    receive_loop()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Stopped")
        GPIO.output(LED_R, GPIO.LOW)
        GPIO.output(LED_G, GPIO.LOW)
        GPIO.output(LED_B, GPIO.LOW)
        GPIO.cleanup()
