#!/usr/bin/env python3
"""
Raspberry Pi Zero W: GPS + NTP server (no OLED), automatic baud detection

Wiring:  GPS T -> GPIO15 (pin 10)   GPS R -> GPIO14 (pin 8)
         GPS V -> 5V (pin 2)        GPS G -> GND (pin 6)

Run:     sudo python3 gps_ntp_pi.py
"""

import calendar
import socket
import struct
import sys
import threading
import time

import serial

PORTS = ["/dev/serial0", "/dev/ttyAMA0", "/dev/ttyS0"]
BAUDS = [9600, 115200, 38400, 57600, 4800, 230400]
NTP_PORT = 123

state = {
    "time": "--:--:--", "date": "--/--/----",
    "lat": 0.0, "lon": 0.0, "sats": 0, "alt": 0.0,
    "locked": False, "gps_epoch": None, "mono_at_fix": None,
}
lock = threading.Lock()


# ---------------- NMEA helpers ----------------
def checksum_ok(line):
    if not line.startswith("$") or "*" not in line:
        return False
    body, _, cs = line[1:].partition("*")
    calc = 0
    for ch in body:
        calc ^= ord(ch)
    try:
        return calc == int(cs[:2], 16)
    except ValueError:
        return False


def to_decimal(val, hemi):
    try:
        v = float(val)
        d = int(v / 100)
        dec = d + (v - d * 100) / 60.0
        return -dec if hemi in ("S", "W") else dec
    except ValueError:
        return 0.0


def handle(line):
    f = line[1:].split("*")[0].split(",")
    kind = f[0][2:]
    if kind == "RMC" and len(f) >= 10:
        if f[2] == "A" and f[1] and f[9]:
            hh, mm, ss = int(f[1][0:2]), int(f[1][2:4]), int(f[1][4:6])
            dd, mo, yy = int(f[9][0:2]), int(f[9][2:4]), 2000 + int(f[9][4:6])
            with lock:
                state["time"] = f"{hh:02d}:{mm:02d}:{ss:02d}"
                state["date"] = f"{dd:02d}/{mo:02d}/{yy:04d}"
                state["lat"] = to_decimal(f[3], f[4])
                state["lon"] = to_decimal(f[5], f[6])
                state["gps_epoch"] = calendar.timegm((yy, mo, dd, hh, mm, ss, 0, 0, 0))
                state["mono_at_fix"] = time.monotonic()
                first = not state["locked"]
                state["locked"] = True
            if first:
                print("\n=========== GPS LOCKED ===========")
            print(f"UTC Time : {state['time']}   Date: {state['date']}")
            print(f"Latitude : {state['lat']:.6f}   Longitude: {state['lon']:.6f}")
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


# ---------------- Auto-detect port + baud ----------------
def find_gps():
    while True:
        for port in PORTS:
            for baud in BAUDS:
                try:
                    ser = serial.Serial(port, baud, timeout=0.5)
                except Exception:
                    break  # this port cannot be opened, try next port
                print(f"Trying {port} @ {baud} ...")
                ser.reset_input_buffer()
                end = time.time() + 2.5
                got_bytes = False
                while time.time() < end:
                    raw = ser.readline()
                    if raw:
                        got_bytes = True
                    line = raw.decode("ascii", errors="ignore").strip()
                    if checksum_ok(line):
                        print(f"GPS FOUND on {port} @ {baud}\n")
                        return ser
                if got_bytes:
                    print("  data arrived but it is not valid NMEA (wrong baud)")
                ser.close()
        print("\nNo GPS data on any port/baud. Check wiring, power and "
              "raspi-config serial settings. Retrying...\n")
        time.sleep(2)


def gps_thread():
    ser = find_gps()
    while True:
        try:
            line = ser.readline().decode("ascii", errors="ignore").strip()
        except Exception as e:
            print(f"GPS read error: {e}")
            time.sleep(1)
            continue
        if not line:
            continue
        print(line)  # raw NMEA, like the ESP32 version
        if checksum_ok(line):
            try:
                handle(line)
            except Exception as e:
                print(f"Parse error: {e}")


# ---------------- NTP server ----------------
NTP_DELTA = 2208988800


def to_ntp(t):
    return ((int(t) + NTP_DELTA) << 32) | int((t % 1) * (1 << 32))


def gps_now():
    with lock:
        if state["gps_epoch"] is None:
            return None
        return state["gps_epoch"] + (time.monotonic() - state["mono_at_fix"])


def ntp_thread():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", NTP_PORT))
    except PermissionError:
        print("NTP: need root for port 123. Run with: sudo python3 gps_ntp_pi.py")
        return
    except OSError as e:
        print(f"NTP: cannot bind port {NTP_PORT}: {e} (chrony/ntpd running?)")
        return
    print(f"NTP SERVER STARTED, PORT: {NTP_PORT}")
    while True:
        data, addr = sock.recvfrom(1024)
        if len(data) < 48:
            continue
        print(f"\nNTP REQUEST RECEIVED from {addr[0]}")
        now = gps_now()
        if now is None:
            print("NTP: no GPS fix yet, ignoring")
            continue
        orig = struct.unpack("!Q", data[40:48])[0]
        reply = struct.pack(
            "!BBbbII4sQQQQ",
            (0 << 6) | (4 << 3) | 4, 1, data[2], -10, 0, 0, b"GPS\x00",
            to_ntp(now), orig, to_ntp(now), to_ntp(gps_now()),
        )
        sock.sendto(reply, addr)
        print("NTP RESPONSE SENT")


# ---------------- Main ----------------
def main():
    sys.stdout.reconfigure(line_buffering=True)
    print("=" * 32)
    print("RPi GPS NTP SERVER STARTING")
    print("=" * 32)
    threading.Thread(target=gps_thread, daemon=True).start()
    threading.Thread(target=ntp_thread, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped")


if __name__ == "__main__":
    main()
