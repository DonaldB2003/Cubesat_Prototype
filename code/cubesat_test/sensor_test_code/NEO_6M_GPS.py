#!/usr/bin/env python3
"""
Raspberry Pi Zero W: GPS (GEP-M10-DI) + SSD1306 OLED + NTP server

Wiring
  GPS  G -> GND (pin 6)
  GPS  V -> 5V  (pin 2)
  GPS  T -> Pi RXD, GPIO15 (pin 10)   (GPS TX goes to Pi RX)
  GPS  R -> Pi TXD, GPIO14 (pin 8)    (GPS RX goes to Pi TX)
  OLED VCC -> 3.3V (pin 1), GND -> pin 9, SDA -> GPIO2 (pin 3), SCL -> GPIO3 (pin 5)

Install
  sudo apt install python3-pip python3-pil fonts-dejavu-core
  pip3 install pyserial pynmea2 luma.oled --break-system-packages

Run (port 123 needs root)
  sudo python3 gps_ntp_pi.py
"""

import calendar
import socket
import struct
import threading
import time

import pynmea2
import serial

# ------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------
GPS_PORT = "/dev/serial0"
GPS_BAUD = 115200          # change to 9600 if you see garbage / no data
NTP_PORT = 123
OLED_ADDR = 0x3C
OLED_ENABLED = True
DEBUG_RAW = False          # True = print every raw NMEA line

# ------------------------------------------------------------------
# SHARED STATE
# ------------------------------------------------------------------
state = {
    "time": "--:--:--",
    "date": "--/--/----",
    "lat": 0.0,
    "lon": 0.0,
    "sats": 0,
    "alt": 0.0,
    "locked": False,
    "gps_epoch": None,     # UTC unix time from last RMC
    "mono_at_fix": None,   # time.monotonic() when that RMC arrived
}
lock = threading.Lock()


# ------------------------------------------------------------------
# GPS READER THREAD
# ------------------------------------------------------------------
def gps_thread():
    try:
        ser = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
    except Exception as e:
        print(f"GPS serial failed: {e}")
        return
    print(f"GPS SERIAL STARTED ({GPS_PORT} @ {GPS_BAUD})")

    while True:
        try:
            line = ser.readline().decode("ascii", errors="ignore").strip()
            if not line.startswith("$"):
                continue
            if DEBUG_RAW:
                print(line)
            msg = pynmea2.parse(line)
        except pynmea2.ParseError:
            continue
        except Exception as e:
            print(f"GPS read error: {e}")
            time.sleep(1)
            continue

        with lock:
            if msg.sentence_type == "RMC" and msg.status == "A":
                dt = msg.datetime  # naive UTC datetime
                state["time"] = dt.strftime("%H:%M:%S")
                state["date"] = dt.strftime("%d/%m/%Y")
                state["lat"] = msg.latitude
                state["lon"] = msg.longitude
                state["gps_epoch"] = calendar.timegm(dt.timetuple())
                state["mono_at_fix"] = time.monotonic()
                if not state["locked"]:
                    print("=========== GPS LOCKED ===========")
                state["locked"] = True
                print(f"UTC {state['time']}  Date {state['date']}  "
                      f"Lat {state['lat']:.6f}  Lon {state['lon']:.6f}")
            elif msg.sentence_type == "RMC":
                state["locked"] = False
            elif msg.sentence_type == "GGA":
                try:
                    state["sats"] = int(msg.num_sats or 0)
                    state["alt"] = float(msg.altitude or 0.0)
                except ValueError:
                    pass


# ------------------------------------------------------------------
# NTP SERVER THREAD
# ------------------------------------------------------------------
NTP_DELTA = 2208988800  # seconds between 1900 and 1970


def to_ntp(t):
    return ((int(t) + NTP_DELTA) << 32) | int((t % 1) * (1 << 32))


def current_gps_time():
    """GPS time, advanced by the monotonic clock since the last fix."""
    with lock:
        if state["gps_epoch"] is None:
            return None
        return state["gps_epoch"] + (time.monotonic() - state["mono_at_fix"])


def ntp_thread():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", NTP_PORT))
    except PermissionError:
        print("NTP: need root for port 123. Run with sudo.")
        return
    except OSError as e:
        print(f"NTP: cannot bind port {NTP_PORT}: {e} "
              "(is chrony/ntpd already running?)")
        return
    print(f"NTP SERVER STARTED, PORT: {NTP_PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        if len(data) < 48:
            continue
        print(f"\nNTP REQUEST RECEIVED from {addr[0]}")

        now = current_gps_time()
        if now is None:
            print("NTP: no GPS time yet, ignoring request")
            continue

        poll = data[2]
        orig = struct.unpack("!Q", data[40:48])[0]   # client's transmit time
        ref = to_ntp(now)
        rx = to_ntp(now)
        tx = to_ntp(current_gps_time())

        reply = struct.pack(
            "!BBbbII4sQQQQ",
            (0 << 6) | (4 << 3) | 4,   # LI=0, VN=4, Mode=4 (server)
            1,                         # stratum 1 (GPS)
            poll,
            -10,                       # precision
            0,                         # root delay
            0,                         # root dispersion
            b"GPS\x00",                # reference ID
            ref, orig, rx, tx,
        )
        sock.sendto(reply, addr)
        print("NTP RESPONSE SENT")


# ------------------------------------------------------------------
# OLED
# ------------------------------------------------------------------
def oled_loop():
    from luma.core.interface.serial import i2c
    from luma.core.render import canvas
    from luma.oled.device import ssd1306
    from PIL import ImageFont

    device = ssd1306(i2c(port=1, address=OLED_ADDR), width=128, height=64)
    small = ImageFont.load_default()
    try:
        big = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
    except Exception:
        big = small

    # boot screen
    with canvas(device) as d:
        d.text((30, 10), "RPi GPS", font=big, fill="white")
        d.text((36, 40), "NTP SERVER", font=small, fill="white")
    time.sleep(3)

    while True:
        with lock:
            t, dt = state["time"], state["date"]
            sats, locked = state["sats"], state["locked"]
        with canvas(device) as d:
            d.text((20, 0), "RPi GPS NTP", font=small, fill="white")
            d.line((0, 10, 127, 10), fill="white")
            d.text((10, 14), t, font=big, fill="white")
            d.text((34, 36), dt, font=small, fill="white")
            d.text((0, 50), f"SAT:{sats}", font=small, fill="white")
            d.text((60, 50), "GPS LOCKED" if locked else "Searching...",
                   font=small, fill="white")
        time.sleep(0.2)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    print("=" * 32)
    print("RPi GPS NTP SERVER STARTING")
    print("=" * 32)

    threading.Thread(target=gps_thread, daemon=True).start()
    threading.Thread(target=ntp_thread, daemon=True).start()

    if OLED_ENABLED:
        try:
            oled_loop()
        except KeyboardInterrupt:
            pass
        except Exception as e:
            print(f"OLED failed ({e}); continuing without display")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
