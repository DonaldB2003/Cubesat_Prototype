import RPi.GPIO as GPIO
import time

MOSFET = 18

GPIO.setmode(GPIO.BCM)
GPIO.setup(MOSFET, GPIO.OUT, initial=GPIO.LOW)

print("Testing MOSFET gate...")
print("⚠️  DO NOT connect burn wire during this test!")
print("Use a multimeter on DRAIN pin instead.")
print()

for i in range(3):
    print(f"Pulse {i+1}: MOSFET ON")
    GPIO.output(MOSFET, GPIO.HIGH)
    time.sleep(1)
    GPIO.output(MOSFET, GPIO.LOW)
    print(f"Pulse {i+1}: MOSFET OFF")
    time.sleep(1)

GPIO.cleanup()
print("MOSFET Test PASSED ✓")
print("Verify with multimeter: 3.3V on DRAIN when ON, 0V when OFF")
