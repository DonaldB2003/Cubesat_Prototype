#!/usr/bin/env python3
"""
Raspberry Pi Zero W: GPS (GEP-M10-DI) + NTP server (no OLED)

Wiring
  GPS  G -> GND (pin 6)
  GPS  V -> 5V  (pin 2)
  GPS  T -> Pi RXD, GPIO15 (pin 10)   (GPS TX goes to Pi RX)
  GPS  R -> Pi TXD, GPIO14 (pin 8)    (GPS RX goes to Pi TX)

Install
  pip3 install pyserial --break-system-packages

Run (port 123 needs root)
  sudo python3 gps_ntp_pi.py

If it prints nothing:
  - try GPS_BAUD = 9600
  - run:  sudo systemctl stop serial-getty@ttyS0   and check raspi-config
    (serial login shell = No, serial hardware = Yes), then reboot
"""

import calendar
import socket
import struct
import sys
import threading
import time

import serial

# ------------------------------------------------------------------
# SETTINGS
# ------------------------------------------------------------------
GPS_PORT = "/dev/serial0"
GPS_BAUD = 115200        # try 9600 if you see garbage or nothing
NTP_PORT = 123
PRINT_RAW = True         # print every raw NMEA line (like the ESP32 version)

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
    "gps_epoch": None,
    "mono_at_fix": None,
    "bytes_rx": 0,
}
lock = threading.Lock()


# ------------------------------------------------------------------
# NMEA HELPERS (no external library)
# ------------------------------------------------------------------
def checksum_ok(line):
    if "*" not in line or not line.startswith("$"):
        return False
    body, _, cs = line[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cs[:2], 16)
    except ValueError:
        return False


def nmea_to_decimal(val, direction):
    try:
        v = float(val)
        deg = int(v / 100)
        dec = deg + (v - deg * 100) / 60.0
        return -dec if direction in ("S", "W") else dec
    except ValueError:
        return 0.0


def handle_sentence(line):
    f = line[1:].split("*")[0].split(",")
    kind = f[0][2:]  # strips talker ID: GPRMC/GNRMC -> RMC

    if kind == "RMC" and len(f) >= 10:
        # f[1]=hhmmss.ss f[2]=status f[3]=lat f[4]=N/S f[5]=lon f[6]=E/W f[9]=ddmmyy
        if f[2] == "A" and f[1] and f[9]:
            hh, mm, ss = int(f[1][0:2]), int(f[1][2:4]), int(f[1][4:6])
            dd, mo, yy = int(f[9][0:2]), int(f[9][2:4]), 2000 + int(f[9][4:6])
            epoch = calendar.timegm((yy, mo, dd, hh, mm, ss, 0, 0, 0))
            with lock:
                state["time"] = f"{hh:02d}:{mm:02d}:{ss:02d}"
                state["date"] = f"{dd:02d}/{mo:02d}/{yy:04d}"
                state["lat"] = nmea_to_decimal(f[3], f[4])
                state["lon"] = nmea_to_decimal(f[5], f[6])
                state["gps_epoch"] = epoch
                state["mono_at_fix"] = time.monotonic()
                if not state["locked"]:
                    print("\n=========== GPS LOCKED ===========")
                state["locked"] = True
            print(f"UTC Time: {state['time']}   Date: {state['date']}")
            print(f"Latitude: {state['lat']:.6f}   Longitude: {state['lon']:.6f}")
        else:
            with lock:
                state["locked"] = False

    elif kind == "GGA" and len(f) >= 10:
        try:
            with lock:
                state["sats"] = int(f[7] or 0)
                state["alt"] = float(f[9] or 0.0)
            print(f"Satellites: {state['sats']}   Altitude: {state['alt']} m")
        except ValueError:
            pass


# ------------------------------------------------------------------
# GPS READER THREAD
# ------------------------------------------------------------------
def gps_thread():
    try:
        ser = serial.Serial(GPS_PORT, GPS_BAUD, timeout=1)
    except Exception as e:
        print(f"GPS serial FAILED: {e}")
        print("Check: raspi-config -> Serial: login shell NO, hardware YES, then reboot.")
        return
    print(f"GPS SERIAL STARTED ({GPS_PORT} @ {GPS_BAUD})")

    while True:
        try:
            raw = ser.readline()
        except Exception as e:
            print(f"GPS read error: {e}")
            time.sleep(1)
            continue

        if not raw:
            continue

        with lock:
            state["bytes_rx"] += len(raw)

        line = raw.decode("ascii", errors="ignore").strip()
        if PRINT_RAW and line:
            print(line)

        if line.startswith("$") and checksum_ok(line):
            try:
                handle_sentence(line)
            except Exception as e:
                print(f"Parse error: {e}")


# ------------------------------------------------------------------
# STATUS THREAD (so you always see something on screen)
# ------------------------------------------------------------------
def status_thread():
    last_bytes = 0
    while True:
        time.sleep(5)
        with lock:
            b = state["bytes_rx"]
            locked = state["locked"]
            sats = state["sats"]
        if b == last_bytes:
            print("\n[STATUS] NO DATA from GPS. Check wiring (T->pin 10, R->pin 8), "
                  "baud rate (try 9600), and serial settings in raspi-config.\n")
        elif not locked:
            print(f"\n[STATUS] Receiving data, but NO FIX yet "
                  f"(satellites: {sats}). Put the antenna near a window or outdoors.\n")
        last_bytes = b


# ------------------------------------------------------------------
# NTP SERVER THREAD
# ------------------------------------------------------------------
NTP_DELTA = 2208988800


def to_ntp(t):
    return ((int(t) + NTP_DELTA) << 32) | int((t % 1) * (1 << 32))


def current_gps_time():
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
        print(f"NTP: cannot bind port {NTP_PORT}: {e} (is chrony/ntpd running?)")
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

        orig = struct.unpack("!Q", data[40:48])[0]
        reply = struct.pack(
            "!BBbbII4sQQQQ",
            (0 << 6) | (4 << 3) | 4,   # LI=0, VN=4, Mode=4 (server)
            1,                         # stratum 1
            data[2],                   # poll
            -10,                       # precision
            0, 0,                      # root delay, root dispersion
            b"GPS\x00",
            to_ntp(now), orig, to_ntp(now), to_ntp(current_gps_time()),
        )
        sock.sendto(reply, addr)
        print("NTP RESPONSE SENT")


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def main():
    print("=" * 32)
    print("RPi GPS NTP SERVER STARTING")
    print("=" * 32)
    sys.stdout.reconfigure(line_buffering=True)

    for fn in (gps_thread, status_thread, ntp_thread):
        threading.Thread(target=fn, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
