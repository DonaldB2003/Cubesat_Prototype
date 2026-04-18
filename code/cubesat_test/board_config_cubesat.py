"""
Custom board config for CubeSat RA-02 LoRa
Raspberry Pi Zero W — corrected pins
"""

import time
import RPi.GPIO as GPIO
import spidev

class _BOARD:
    # ─── LoRa Pins (BCM numbering) ─────────────────────────────
    NSS  = 8    # CE0 - SPI Chip Select
    RST  = 17   # Reset
    DIO0 = 4    # RX Done interrupt

    spi = spidev.SpiDev()

    @staticmethod
    def setup():
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        GPIO.setup(_BOARD.RST,  GPIO.OUT)
        GPIO.setup(_BOARD.NSS,  GPIO.OUT)
        GPIO.setup(_BOARD.DIO0, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        # Reset pulse to RA-02
        GPIO.output(_BOARD.RST, GPIO.LOW)
        time.sleep(0.01)
        GPIO.output(_BOARD.RST, GPIO.HIGH)
        time.sleep(0.01)

        # SPI bus 0, device 0 (CE0 = GPIO8)
        _BOARD.spi.open(0, 0)
        _BOARD.spi.max_speed_hz = 5000000
        _BOARD.spi.mode = 0b00

        print("[BOARD] SPI + GPIO ready.")

    @staticmethod
    def teardown():
        _BOARD.spi.close()
        GPIO.cleanup()
        print("[BOARD] Cleanup done.")

    @staticmethod
    def SpiDev():
        return _BOARD.spi

    @staticmethod
    def add_event_detect(dio_number, callback):
        GPIO.add_event_detect(
            dio_number,
            GPIO.RISING,
            callback=callback,
            bouncetime=50
        )

    @staticmethod
    def add_events(cb_dio0, cb_dio1, cb_dio2, cb_dio3, cb_dio4, cb_dio5):
        # Only DIO0 is wired — skip DIO1–5 safely
        _BOARD.add_event_detect(_BOARD.DIO0, callback=cb_dio0)

    @staticmethod
    def led_on(value=1): pass

    @staticmethod
    def led_off(): pass

BOARD = _BOARD()
