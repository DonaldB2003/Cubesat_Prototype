import smbus2
import math
import time

bus  = smbus2.SMBus(1)
ADDR = 0x69

bus.write_byte_data(ADDR, 0x6B, 0x00)  # wake up
time.sleep(0.1)

def rw(reg):
    h = bus.read_byte_data(ADDR, reg)
    l = bus.read_byte_data(ADDR, reg+1)
    v = (h<<8)+l
    return v-65536 if v>=0x8000 else v

print("=" * 55)
print("       MPU-6050 CALIBRATION & TEST")
print("=" * 55)
print("⚠️  Keep sensor FLAT and STILL during calibration!")
print("Collecting 100 readings...")
print("-" * 55)

# ── Collect 100 readings for offset calculation ───────────────
ax_list,ay_list,az_list = [],[],[]
gx_list,gy_list,gz_list = [],[],[]

for i in range(100):
    ax_list.append(rw(0x3B)/16384.0)
    ay_list.append(rw(0x3D)/16384.0)
    az_list.append(rw(0x3F)/16384.0)
    gx_list.append(rw(0x43)/131.0)
    gy_list.append(rw(0x45)/131.0)
    gz_list.append(rw(0x47)/131.0)
    time.sleep(0.01)

# ── Calculate offsets ─────────────────────────────────────────
# At rest: ax=0, ay=0, az=1.0g (gravity), gx=gy=gz=0
ax_off = round(sum(ax_list)/100, 4)
ay_off = round(sum(ay_list)/100, 4)
az_off = round(sum(az_list)/100 - 1.0, 4)  # subtract 1g gravity
gx_off = round(sum(gx_list)/100, 4)
gy_off = round(sum(gy_list)/100, 4)
gz_off = round(sum(gz_list)/100, 4)

print(f"Accel offsets → X:{ax_off}g  Y:{ay_off}g  Z:{az_off}g")
print(f"Gyro  offsets → X:{gx_off}°/s  Y:{gy_off}°/s  Z:{gz_off}°/s")
print("-" * 55)

# ── Live calibrated readings ──────────────────────────────────
print("Live calibrated readings (10 samples):")
for i in range(10):
    ax = round(rw(0x3B)/16384.0 - ax_off, 3)
    ay = round(rw(0x3D)/16384.0 - ay_off, 3)
    az = round(rw(0x3F)/16384.0 - az_off, 3)
    gx = round(rw(0x43)/131.0   - gx_off, 2)
    gy = round(rw(0x45)/131.0   - gy_off, 2)
    gz = round(rw(0x47)/131.0   - gz_off, 2)
    mag = round(math.sqrt(ax**2+ay**2+(az+1.0)**2), 3)
    print(f"  Accel X:{ax:7.3f}g Y:{ay:7.3f}g Z:{az+1.0:7.3f}g MAG:{mag}g")
    print(f"  Gyro  X:{gx:7.2f}  Y:{gy:7.2f}  Z:{gz:7.2f} °/s")
    print(f"  {'-'*45}")
    time.sleep(0.5)

print("=" * 55)
print("MPU-6050 Calibration DONE ✓")
print(f"Add these to your main code:")
print(f"  AX_OFF={ax_off}  AY_OFF={ay_off}  AZ_OFF={az_off}")
print(f"  GX_OFF={gx_off}  GY_OFF={gy_off}  GZ_OFF={gz_off}")
print("=" * 55)
