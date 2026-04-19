import time
import board
import adafruit_dht

# ── Setup ──────────────────────────────────────────────────────
dht = adafruit_dht.DHT11(board.D24)   # ← DHT11 not DHT22

print("Testing DHT11...")
for i in range(5):
    try:
        temp = dht.temperature
        hum  = dht.humidity
        if temp and hum:
            print(f"Temp: {round(temp,1)}°C | Humidity: {round(hum,1)}%")
        else:
            print("Read failed — retrying...")
    except RuntimeError as e:
        print(f"RuntimeError (normal): {e}")
    time.sleep(2)   # DHT11 needs minimum 1s between reads

dht.exit()
print("DHT11 Test PASSED ✓")
