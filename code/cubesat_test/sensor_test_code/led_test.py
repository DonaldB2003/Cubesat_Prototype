import RPi.GPIO as GPIO
import time

LED_RED, LED_GREEN, LED_BLUE = 23, 25, 16

GPIO.setmode(GPIO.BCM)
GPIO.setup(LED_RED,   GPIO.OUT)
GPIO.setup(LED_GREEN, GPIO.OUT)
GPIO.setup(LED_BLUE,  GPIO.OUT)

print("Testing LEDs...")

print("RED ON"); GPIO.output(LED_RED, GPIO.HIGH); time.sleep(2)
print("RED OFF"); GPIO.output(LED_RED, GPIO.LOW); time.sleep(0.5)

print("GREEN ON"); GPIO.output(LED_GREEN, GPIO.HIGH); time.sleep(2)
print("GREEN OFF"); GPIO.output(LED_GREEN, GPIO.LOW); time.sleep(0.5)

print("BLUE ON"); GPIO.output(LED_BLUE, GPIO.HIGH); time.sleep(2)
print("BLUE OFF"); GPIO.output(LED_BLUE, GPIO.LOW); time.sleep(0.5)

print("ALL ON"); 
GPIO.output(LED_RED, GPIO.HIGH)
GPIO.output(LED_GREEN, GPIO.HIGH)
GPIO.output(LED_BLUE, GPIO.HIGH)
time.sleep(2)

print("ALL OFF")
GPIO.output(LED_RED,   GPIO.LOW)
GPIO.output(LED_GREEN, GPIO.LOW)
GPIO.output(LED_BLUE,  GPIO.LOW)

GPIO.cleanup()
print("LED Test PASSED ✓")
