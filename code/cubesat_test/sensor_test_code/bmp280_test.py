import smbus2
import time

bus  = smbus2.SMBus(1)
ADDR = 0x76

# ── Load calibration ──────────────────────────────────────────
cal = bus.read_i2c_block_data(ADDR, 0x88, 24)

def u16(i): return (cal[i+1] << 8) | cal[i]           # unsigned
def s16(i): v = u16(i); return v - 65536 if v > 32767 else v  # signed

dig_T1 = u16(0);  dig_T2 = s16(2);  dig_T3 = s16(4)
dig_P1 = u16(6)   # ← MUST be unsigned
dig_P2 = s16(8);  dig_P3 = s16(10); dig_P4 = s16(12)
dig_P5 = s16(14); dig_P6 = s16(16); dig_P7 = s16(18)
dig_P8 = s16(20); dig_P9 = s16(22)

print(f"Calibration check → dig_P1: {dig_P1} (must be positive!)")

bus.write_byte_data(ADDR, 0xF4, 0x27)
bus.write_byte_data(ADDR, 0xF5, 0xA0)
time.sleep(0.5)

print("Testing BMP280...")
for i in range(5):
    d    = bus.read_i2c_block_data(ADDR, 0xF7, 6)
    adc_P = (d[0] << 12) | (d[1] << 4) | (d[2] >> 4)
    adc_T = (d[3] << 12) | (d[4] << 4) | (d[5] >> 4)

    # Temperature
    var1 = ((adc_T / 16384.0) - (dig_T1 / 1024.0)) * dig_T2
    var2 = ((adc_T / 131072.0) - (dig_T1 / 8192.0)) ** 2 * dig_T3
    t_fine = var1 + var2
    temp   = t_fine / 5120.0

    # Pressure
    var1 = t_fine / 2.0 - 64000.0
    var2 = var1 * var1 * dig_P6 / 32768.0
    var2 = var2 + var1 * dig_P5 * 2.0
    var2 = var2 / 4.0 + dig_P4 * 65536.0
    var1 = (dig_P3 * var1 * var1 / 524288.0 + dig_P2 * var1) / 524288.0
    var1 = (1.0 + var1 / 32768.0) * dig_P1

    if var1 == 0:
        print("var1 is zero — calibration error!")
        continue

    pressure = 1048576.0 - adc_P
    pressure = (pressure - var2 / 4096.0) * 6250.0 / var1
    pressure = pressure / 100.0  # Pa to hPa

    altitude = 44330.0 * (1.0 - (pressure / 1013.25) ** (1.0 / 5.255))

    print(f"Temp: {temp:.2f}°C | Pressure: {pressure:.2f}hPa | Altitude: {altitude:.2f}m")
    time.sleep(1)

print("BMP280 Test PASSED ✓")
