import smbus2
import time

bus  = smbus2.SMBus(1)
ADDR = 0x68

def bcd2dec(v): return (v>>4)*10+(v&0x0F)
def dec2bcd(v): return ((v//10)<<4)|(v%10)

def set_time(h, m, s):
    bus.write_byte_data(ADDR, 0x00, dec2bcd(s))
    bus.write_byte_data(ADDR, 0x01, dec2bcd(m))
    bus.write_byte_data(ADDR, 0x02, dec2bcd(h))

def get_time():
    d = bus.read_i2c_block_data(ADDR, 0x00, 3)
    s = bcd2dec(d[0]&0x7F)
    m = bcd2dec(d[1])
    h = bcd2dec(d[2]&0x3F)
    return h, m, s

def get_temp():
    # DS3231 has built in temperature sensor (±3°C accuracy)
    msb = bus.read_byte_data(ADDR, 0x11)
    lsb = bus.read_byte_data(ADDR, 0x12)
    temp = msb + ((lsb >> 6) * 0.25)
    if msb > 127: temp -= 256  # handle negative temp
    return round(temp, 2)

print("=" * 55)
print("        DS3231 CALIBRATION & TEST")
print("=" * 55)

# ── Set current time (CHANGE THIS to actual time) ─────────────
SET_H, SET_M, SET_S = 14, 30, 0
print(f"Setting time to {SET_H:02d}:{SET_M:02d}:{SET_S:02d}")
print("⚠️  Change SET_H, SET_M, SET_S to current time!")
set_time(SET_H, SET_M, SET_S)
time.sleep(1)

# ── Verify time accuracy over 10 seconds ──────────────────────
print("-" * 55)
print("Verifying timekeeping accuracy over 10 seconds...")
h,m,s = get_time()
start_sec = h*3600 + m*60 + s
print(f"Start time: {h:02d}:{m:02d}:{s:02d}")

drifts = []
for i in range(10):
    real_elapsed = i + 1
    time.sleep(1)
    h,m,s   = get_time()
    rtc_sec = h*3600 + m*60 + s
    elapsed = rtc_sec - start_sec
    drift   = elapsed - real_elapsed
    drifts.append(drift)
    rtc_temp = get_temp()
    print(f"  [{real_elapsed:02d}s] RTC:{h:02d}:{m:02d}:{s:02d}"
          f"  Elapsed:{elapsed}s  Drift:{drift:+d}s"
          f"  RTC Temp:{rtc_temp}°C")

print("-" * 55)
avg_drift = sum(drifts)/len(drifts)
print(f"Average drift: {round(avg_drift,2)}s over 10s")
if abs(avg_drift) <= 1:
    print("Accuracy: EXCELLENT ✓ (±1s over 10s)")
elif abs(avg_drift) <= 2:
    print("Accuracy: GOOD ✓ (±2s over 10s)")
else:
    print("Accuracy: POOR ✗ — check CR2032 battery!")
print("=" * 55)
print("DS3231 Calibration DONE ✓")
