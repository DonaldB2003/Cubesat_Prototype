import RPi.GPIO as GPIO
import time

# ─── Pin ──────────────────────────────────────────────────────
MOSFET = 17   # GPIO 18 → Pin 12

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(MOSFET, GPIO.OUT, initial=GPIO.LOW)

print("MOSFET Test")
print("=" * 30)
print("⚠️  Make sure nichrome wire is connected!")
print("⚠️  Keep away from flammable material!")
print()

input("Press ENTER to fire MOSFET for 3 seconds...")

print("MOSFET ON — firing...")
GPIO.output(MOSFET, GPIO.HIGH)
time.sleep(3)
GPIO.output(MOSFET, GPIO.LOW)
print("MOSFET OFF — done!")
print()
print("Check if nichrome wire heated up.")

GPIO.cleanup()
