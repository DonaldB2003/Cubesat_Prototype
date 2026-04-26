import RPi.GPIO as GPIO
import time
import smbus2
import serial

# ─────────────────────────────────────
# PIN CONFIG
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
GPIO.setup([MISO, DIO0], GPIO.IN)

GPIO.output(NSS, 1)
GPIO.output(SCK, 0)
GPIO.output(LED_R, 0)
GPIO.output(LED_G, 0)
GPIO.output(LED_B, 0)

# ─────────────────────────────────────
# I2C (BMP280)
# ─────────────────────────────────────
bus = smbus2.SMBus(1)
BMP_ADDR = 0x76

# ─────────────────────────────────────
# GPS UART
# ─────────────────────────────────────
try:
    gps = serial.Serial("/dev/serial0", 9600, timeout=1)
except Exception as e:
    print(f"⚠️ GPS init failed: {e}")
    gps = None

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
        time.sleep(0.00001)
    return recv

def write_reg(reg, val):
    GPIO.output(NSS, 0)
    spi_transfer(reg | 0x80)
    spi_transfer(val)
    GPIO.output(NSS, 1)
    time.sleep(0.000005)

def read_reg(reg):
    GPIO.output(NSS, 0)
    spi_transfer(reg & 0x7F)
    val = spi_transfer(0x00)
    GPIO.output(NSS, 1)
    time.sleep(0.000005)
    return val

# ─────────────────────────────────────
# LORA INIT
# ─────────────────────────────────────
def init_lora():
    print("🔄 Resetting LoRa...")
    GPIO.output(RST, 0)
    time.sleep(0.01)
    GPIO.output(RST, 1)
    time.sleep(0.1)

    version = read_reg(0x42)
    print(f"   LoRa version register: 0x{version:02X}")
    if version != 0x12:
        raise Exception(f"LoRa not detected! Got 0x{version:02X}, expected 0x12")

    # Put into Sleep + LoRa mode
    write_reg(0x01, 0x80)
    time.sleep(0.1)

    # Set frequency: 433 MHz
    frf = int(433e6 / (32e6 / 524288))
    write_reg(0x06, (frf >> 16) & 0xFF)
    write_reg(0x07, (frf >> 8) & 0xFF)
    write_reg(0x08, frf & 0xFF)
    print(f"   Freq set: 433 MHz (FRF=0x{frf:06X})")

    # Modem config:
    # 0x1D: BW=125kHz (0111), CR=4/5 (001), ExplicitHeader (0) → 0x72
    # 0x1E: SF=7 (0111), normal TX (0), RxCrcOn (1), SymbTimeout MSB (00) → 0x74
    #        NOTE: bit2 in 0x1E is NOT TxContinuousMode — it's RxPayloadCrcOn. 0x74 is CORRECT.
    # 0x26: LowDataRateOptimize=0, AgcAutoOn=1 → 0x04
    write_reg(0x1D, 0x72)   # BW=125kHz, CR=4/5, Explicit Header
    write_reg(0x1E, 0x74)   # SF=7, RxCrcOn=1
    write_reg(0x26, 0x04)   # AgcAutoOn

    # FIFO base addresses
    write_reg(0x0E, 0x00)   # FifoTxBaseAddr = 0
    write_reg(0x0F, 0x00)   # FifoRxBaseAddr = 0

    # Max payload length
    write_reg(0x23, 0xFF)

    # PA config: +17dBm using PA_BOOST
    write_reg(0x09, 0x8F)

    # Standby mode
    write_reg(0x01, 0x81)
    time.sleep(0.01)

    print("✅ LoRa initialized (433MHz, SF7, BW125, CR4/5, CRC ON)")

# ─────────────────────────────────────
# SEND PACKET
# ─────────────────────────────────────
def send_packet(data):
    GPIO.output(LED_G, 1)

    # Go to standby
    write_reg(0x01, 0x81)
    time.sleep(0.001)

    # Reset FIFO pointer to TxBase
    write_reg(0x0E, 0x00)   # FifoTxBaseAddr
    write_reg(0x0D, 0x00)   # FifoAddrPtr

    # Write payload to FIFO
    GPIO.output(NSS, 0)
    spi_transfer(0x80)      # FIFO register (write)
    for b in data:
        spi_transfer(b)
    GPIO.output(NSS, 1)

    # Set payload length
    write_reg(0x22, len(data))

    # Clear all IRQ flags
    write_reg(0x12, 0xFF)

    # Start TX
    write_reg(0x01, 0x83)

    # Wait for TxDone (bit 3 of RegIrqFlags)
    timeout_start = time.time()
    while True:
        irq = read_reg(0x12)
        if irq & 0x08:
            break
        if time.time() - timeout_start > 5:
            print("⚠️ TX TIMEOUT")
            GPIO.output(LED_R, 1)
            time.sleep(0.2)
            GPIO.output(LED_R, 0)
            break

    # Clear IRQ flags
    write_reg(0x12, 0xFF)

    # Return to standby
    write_reg(0x01, 0x81)

    GPIO.output(LED_G, 0)
    print("✅ TX DONE")

# ─────────────────────────────────────
# BMP280 CALIBRATION + READ
# ─────────────────────────────────────
bmp_cal = {}

def read_bmp280_calibration():
    global bmp_cal
    try:
        cal = bus.read_i2c_block_data(BMP_ADDR, 0x88, 24)

        bmp_cal['T1'] = (cal[1] << 8) | cal[0]
        bmp_cal['T2'] = (cal[3] << 8) | cal[2]
        if bmp_cal['T2'] > 32767: bmp_cal['T2'] -= 65536
        bmp_cal['T3'] = (cal[5] << 8) | cal[4]
        if bmp_cal['T3'] > 32767: bmp_cal['T3'] -= 65536

        bmp_cal['P1'] = (cal[7] << 8) | cal[6]
        bmp_cal['P2'] = (cal[9] << 8) | cal[8]
        if bmp_cal['P2'] > 32767: bmp_cal['P2'] -= 65536
        bmp_cal['P3'] = (cal[11] << 8) | cal[10]
        if bmp_cal['P3'] > 32767: bmp_cal['P3'] -= 65536
        bmp_cal['P4'] = (cal[13] << 8) | cal[12]
        if bmp_cal['P4'] > 32767: bmp_cal['P4'] -= 65536
        bmp_cal['P5'] = (cal[15] << 8) | cal[14]
        if bmp_cal['P5'] > 32767: bmp_cal['P5'] -= 65536
        bmp_cal['P6'] = (cal[17] << 8) | cal[16]
        if bmp_cal['P6'] > 32767: bmp_cal['P6'] -= 65536
        bmp_cal['P7'] = (cal[19] << 8) | cal[18]
        if bmp_cal['P7'] > 32767: bmp_cal['P7'] -= 65536
        bmp_cal['P8'] = (cal[21] << 8) | cal[20]
        if bmp_cal['P8'] > 32767: bmp_cal['P8'] -= 65536
        bmp_cal['P9'] = (cal[23] << 8) | cal[22]
        if bmp_cal['P9'] > 32767: bmp_cal['P9'] -= 65536

        # Set BMP280 to forced mode, osrs_t=1, osrs_p=1
        bus.write_byte_data(BMP_ADDR, 0xF4, 0x27)   # osrs_t=001, osrs_p=001, normal mode
        bus.write_byte_data(BMP_ADDR, 0xF5, 0xA0)   # standby=1000ms, filter=off

        print("✅ BMP280 calibration loaded")
        return True
    except Exception as e:
        print(f"❌ BMP280 calibration failed: {e}")
        return False

def read_bmp():
    try:
        d = bus.read_i2c_block_data(BMP_ADDR, 0xF7, 6)

        adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
        adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)

        # Temperature compensation
        T1 = bmp_cal['T1']; T2 = bmp_cal['T2']; T3 = bmp_cal['T3']
        var1 = ((adc_T / 16384.0) - (T1 / 1024.0)) * T2
        var2 = ((adc_T / 131072.0) - (T1 / 8388608.0)) ** 2 * T3
        t_fine = var1 + var2
        temp = t_fine / 5120.0

        # Pressure compensation
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
        pressure = pressure + (var1 + var2 + P7) / 16.0
        pressure = pressure / 100.0  # hPa

        altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** 0.1903)

        return round(temp, 2), round(pressure, 2), round(altitude, 2)

    except Exception as e:
        print(f"❌ BMP read error: {e}")
        GPIO.output(LED_R, 1)
        time.sleep(0.05)
        GPIO.output(LED_R, 0)
        return None, None, None

# ─────────────────────────────────────
# DHT22
# ─────────────────────────────────────
def read_dht():
    try:
        import Adafruit_DHT
        h, t = Adafruit_DHT.read_retry(Adafruit_DHT.DHT22, DHT_PIN)
        if h is not None and t is not None:
            return round(t, 2), round(h, 2)
    except Exception as e:
        print(f"⚠️ DHT read error: {e}")
    return None, None

# ─────────────────────────────────────
# GPS — NMEA NMEA-correct parsing
# ─────────────────────────────────────
def nmea_to_decimal(val_str, direction):
    """Convert NMEA DDDMM.MMMM + direction to decimal degrees."""
    try:
        val = float(val_str)
        degrees = int(val / 100)
        minutes = val - degrees * 100
        decimal = degrees + minutes / 60.0
        if direction in ('S', 'W'):
            decimal = -decimal
        return round(decimal, 6)
    except:
        return 0.0

def read_gps():
    if gps is None:
        return 0.0, 0.0
    try:
        for _ in range(10):  # Try up to 10 lines per call
            line = gps.readline().decode(errors="ignore").strip()
            if line.startswith("$GPGGA") or line.startswith("$GNGGA"):
                parts = line.split(',')
                if len(parts) >= 6 and parts[2] and parts[4]:
                    lat = nmea_to_decimal(parts[2], parts[3])
                    lon = nmea_to_decimal(parts[4], parts[5])
                    if lat != 0.0 or lon != 0.0:
                        GPIO.output(LED_B, 1)
                        return lat, lon
        GPIO.output(LED_B, 0)
    except Exception as e:
        print(f"⚠️ GPS error: {e}")
    return 0.0, 0.0

# ─────────────────────────────────────
# SIMPLE CRC16
# ─────────────────────────────────────
def crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF

# ─────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────
msg_id = 0

def loop():
    global msg_id

    while True:
        msg_id += 1

        temp_bmp, press, alt = read_bmp()
        temp_dht, hum        = read_dht()
        lat, lon             = read_gps()

        if temp_bmp is None:
            print("❌ BMP280 read failed — skipping packet")
            GPIO.output(LED_R, 1)
            time.sleep(1)
            GPIO.output(LED_R, 0)
            time.sleep(4)
            continue

        # Use 0.0 for missing DHT
        if temp_dht is None: temp_dht = 0.0
        if hum       is None: hum      = 0.0

        timestamp = int(time.time())

        # Build CSV payload without CRC first
        payload_no_crc = f"{msg_id},{timestamp},{lat},{lon},{temp_bmp},{press},{alt},{temp_dht},{hum}"

        # Compute CRC16 over the payload
        crc = crc16(payload_no_crc.encode())

        msg = f"{payload_no_crc},{crc}"

        print(f"\n📤 TX [{msg_id}]: {msg}")
        print(f"   BMP → Temp:{temp_bmp}°C  Press:{press}hPa  Alt:{alt}m")
        print(f"   DHT → Temp:{temp_dht}°C  Hum:{hum}%")
        print(f"   GPS → {lat}, {lon}")
        print(f"   CRC16: 0x{crc:04X}")

        send_packet(msg.encode())

        time.sleep(5)

# ─────────────────────────────────────
# START
# ─────────────────────────────────────
print("=" * 50)
print("🚀 CubeSat LoRa Transmitter Node")
print("=" * 50)

# Init BMP280 calibration
read_bmp280_calibration()

# Init LoRa
init_lora()

print("\n🛰️  Node started. Transmitting every 5 seconds.\n")

try:
    loop()
except KeyboardInterrupt:
    print("\n🛑 Stopped by user")
    GPIO.output(LED_R, 0)
    GPIO.output(LED_G, 0)
    GPIO.output(LED_B, 0)
    GPIO.cleanup()
