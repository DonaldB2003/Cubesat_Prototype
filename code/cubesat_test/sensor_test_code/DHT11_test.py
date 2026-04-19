import Adafruit_DHT
import time

PIN    = 24
SENSOR = Adafruit_DHT.DHT22

# ── Known offsets (compare with thermometer/hygrometer) ───────
TEMP_OFFSET = 0.0   # e.g. if reads 28°C but actual is 27°C → set -1.0
HUM_OFFSET  = 0.0   # e.g. if reads 65% but actual is 60%  → set -5.0

print("=" * 55)
print("        DHT22 CALIBRATION & TEST")
print("=" * 55)
print("Collecting 10 readings (2s apart)...")
print("-" * 55)

temps, hums = [], []
fail_count  = 0

for i in range(10):
    hum, temp = Adafruit_DHT.read_retry(SENSOR, PIN)
    if hum is None or temp is None:
        print(f"  [{i+1:02d}] READ FAILED")
        fail_count += 1
        continue
    temp_cal = round(temp + TEMP_OFFSET, 1)
    hum_cal  = round(hum  + HUM_OFFSET,  1)
    temps.append(temp_cal)
    hums.append(hum_cal)
    print(f"  [{i+1:02d}] Temp:{temp_cal}°C  Humidity:{hum_cal}%"
          f"  (raw T:{round(temp,1)} H:{round(hum,1)})")
    time.sleep(2)

print("-" * 55)
if temps:
    avg_t = round(sum(temps)/len(temps), 1)
    avg_h = round(sum(hums)/len(hums),   1)
    print(f"Average → Temp:{avg_t}°C  Humidity:{avg_h}%")
    print(f"Temp  range: {min(temps)}°C to {max(temps)}°C")
    print(f"Hum   range: {min(hums)}%  to {max(hums)}%")
    print(f"Failed reads: {fail_count}/10")
print("-" * 55)
print("⚠️  Compare with a known thermometer/hygrometer.")
print("    If temp is off, set TEMP_OFFSET = (actual - reading)")
print("    If hum  is off, set HUM_OFFSET  = (actual - reading)")
print("=" * 55)
print("DHT22 Calibration DONE ✓")
