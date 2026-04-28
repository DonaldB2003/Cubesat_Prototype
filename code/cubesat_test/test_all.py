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
#  I2C — BMP280
# ═══════════════════════════════════════════════════
bus      = smbus2.SMBus(1)
BMP_ADDR = 0x76

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
#  DHT22 — PURE GPIO BIT-BANG (no board, no library)
# ═══════════════════════════════════════════════════
def read_dht():
    """
    Pure GPIO DHT22 reader.
    Returns (temperature_C, humidity_%) or (None, None) on failure.
    """
    try:
        data = []

        # ── Send start signal ──────────────────────
        GPIO.setup(DHT_PIN, GPIO.OUT)
        GPIO.output(DHT_PIN, GPIO.LOW)
        time.sleep(0.02)                    # hold low 20ms
        GPIO.output(DHT_PIN, GPIO.HIGH)
        time.sleep(0.00004)                 # hold high 40us

        # ── Switch to input and wait for sensor response ──
        GPIO.setup(DHT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Wait for sensor to pull LOW (response start)
        timeout = time.time() + 0.1
        while GPIO.input(DHT_PIN) == GPIO.HIGH:
            if time.time() > timeout:
                return None, None

        # Wait for sensor to pull HIGH (response pulse)
        timeout = time.time() + 0.1
        while GPIO.input(DHT_PIN) == GPIO.LOW:
            if time.time() > timeout:
                return None, None

        # Wait for sensor to pull LOW again (data start)
        timeout = time.time() + 0.1
        while GPIO.input(DHT_PIN) == GPIO.HIGH:
            if time.time() > timeout:
                return None, None

        # ── Read 40 bits ──────────────────────────
        for _ in range(40):
            # Each bit starts with a ~50us LOW pulse
            timeout = time.time() + 0.001
            while GPIO.input(DHT_PIN) == GPIO.LOW:
                if time.time() > timeout:
                    return None, None

            # Measure HIGH duration:
            # ~26-28us = 0 bit
            # ~70us    = 1 bit
            high_start = time.time()
            timeout = time.time() + 0.001
            while GPIO.input(DHT_PIN) == GPIO.HIGH:
                if time.time() > timeout:
                    return None, None
            high_duration = time.time() - high_start

            data.append(1 if high_duration > 0.00005 else 0)

        # ── Assemble 5 bytes from 40 bits ─────────
        bytes_data = []
        for i in range(5):
            byte = 0
            for bit in data[i*8 : i*8+8]:
                byte = (byte << 1) | bit
            bytes_data.append(byte)

        # ── Verify checksum ───────────────────────
        checksum = (bytes_data[0] + bytes_data[1] +
                    bytes_data[2] + bytes_data[3]) & 0xFF

        if checksum != bytes_data[4]:
            print(f"⚠️ DHT11 checksum fail: calc={checksum}, got={bytes_data[4]}")
            return None, None

        # ── Decode humidity ───────────────────────
        #humidity = ((bytes_data[0] << 8) | bytes_data[1]) / 10.0

        # ── Decode temperature (signed) ───────────
        #raw_temp = ((bytes_data[2] & 0x7F) << 8) | bytes_data[3]
        #temp = raw_temp / 10.0

        humidity = bytes_data[0]      # integer %
        temp = bytes_data[2]          # integer °C
        
        if bytes_data[2] & 0x80:            # negative temp flag
            temp = -temp

        # ── Sanity check ──────────────────────────
        if not (0 <= temp <= 50) or not (20 <= humidity <= 90):
            print(f"⚠️ DHT11 out of range: T={temp} H={humidity}")
            return None, None

        return round(temp, 2), round(humidity, 2)

    except Exception as e:
        print(f"❌ DHT11 error: {e}")
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
#  FORMAT (15 fields):
#  relay_id, unix_time,
#  rescue_lat, rescue_lon, emergency_type,
#  rescue_msg_id, rescue_millis,
#  bmp_temp, pressure, altitude,
#  dht_temp, humidity,
#  pi_lat, pi_lon,
#  crc16
# ═══════════════════════════════════════════════════
relay_id = 0

def send_merged_packet(rescue_parts, bmp_temp, pressure, altitude,
                        dht_temp, humidity, pi_lat, pi_lon):
    global relay_id
    relay_id += 1

    rescue_msg_id  = rescue_parts[0]
    rescue_millis  = rescue_parts[1]
    rescue_lat     = rescue_parts[2]
    rescue_lon     = rescue_parts[3]
    emergency_type = rescue_parts[4]

    unix_time = int(time.time())

    payload = (
        f"{relay_id},{unix_time},"
        f"{rescue_lat},{rescue_lon},{emergency_type},"
        f"{rescue_msg_id},{rescue_millis},"
        f"{bmp_temp},{pressure},{altitude},"
        f"{dht_temp},{humidity},"
        f"{pi_lat},{pi_lon}"
    )

    crc = crc16(payload.encode())
    full_msg = f"{payload},{crc}"

    print(f"\n📤 Sending merged packet [{relay_id}]:")
    print(f"   {full_msg}\n")

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

# ═══════════════════════════════════════════════════
#  MAIN RECEIVE + RELAY LOOP
# ═══════════════════════════════════════════════════
def receive_loop():
    print("\n📡 Relay node active — listening for rescue tower...\n")

    while True:
        irq = read_reg(REG_IRQ_FLAGS)

        if irq & 0x40:  # RxDone

            # CRC error check
            if irq & 0x20:
                print("⚠️ CRC error in received packet — discarding")
                write_reg(REG_IRQ_FLAGS, 0xFF)
                write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
                time.sleep(0.05)
                continue

            length    = read_reg(REG_RX_NB_BYTES)
            fifo_addr = read_reg(REG_FIFO_RX_CURR)
            write_reg(REG_FIFO_ADDR_PTR, fifo_addr)

            payload  = read_fifo(length)
            raw_msg  = bytes(payload).decode('utf-8', errors='ignore').strip()

            rssi = read_reg(REG_PKT_RSSI) - 137
            snr  = read_reg(REG_PKT_SNR)
            if snr > 127: snr -= 256
            snr  = snr / 4.0

            print(f"📦 Received from rescue tower:")
            print(f"   Raw   : {raw_msg}")
            print(f"   RSSI  : {rssi} dBm  |  SNR: {snr} dB")

            parts = raw_msg.split(',')

            # Validate 6-field rescue tower format
            if len(parts) != 6:
                print(f"⚠️ Unexpected field count: {len(parts)} — discarding")
                write_reg(REG_IRQ_FLAGS, 0xFF)
                write_reg(REG_OP_MODE, MODE_LONG_RANGE | MODE_RX_CONT)
                time.sleep(0.05)
                continue

            # Validate tower CRC
            try:
                tower_msg_id   = int(parts[0])
                tower_millis   = int(parts[1])
                tower_crc_rx   = int(parts[5])
                tower_crc_calc = (tower_msg_id + tower_millis) & 0xFFFFFFFF
                crc_ok = (tower_crc_calc == tower_crc_rx)
                print(f"   Tower CRC: {'✅ OK' if crc_ok else '❌ FAIL (relaying anyway)'}")
            except:
                print("   ⚠️ Could not verify tower CRC")

            # Read Pi sensors
            bmp_temp, pressure, altitude = read_bmp()
            dht_temp, humidity           = read_dht()
            pi_lat,   pi_lon             = read_gps()

            if bmp_temp  is None: bmp_temp  = 0.0
            if pressure  is None: pressure  = 0.0
            if altitude  is None: altitude  = 0.0
            if dht_temp  is None: dht_temp  = 0.0
            if humidity  is None: humidity  = 0.0

            print(f"   BMP280: {bmp_temp}°C, {pressure}hPa, {altitude}m")
            print(f"   DHT22 : {dht_temp}°C, {humidity}%")
            print(f"   GPS   : {pi_lat}, {pi_lon}")

            send_merged_packet(
                parts,
                bmp_temp, pressure, altitude,
                dht_temp, humidity,
                pi_lat, pi_lon
            )

            write_reg(REG_IRQ_FLAGS, 0xFF)

        time.sleep(0.05)

# ═══════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════
def main():
    print("=" * 52)
    print("   🛰️  LoRa RELAY NODE  —  Rescue + Sensors")
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
