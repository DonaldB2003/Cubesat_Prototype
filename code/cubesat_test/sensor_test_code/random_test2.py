import serial
import pynmea2

PORT = "/dev/serial0"
BAUD = 9600

ser = serial.Serial(PORT, baudrate=BAUD, timeout=1)
print(f"Reading GPS on {PORT} @ {BAUD} ... (Ctrl+C to stop)")

try:
    while True:
        line = ser.readline().decode("ascii", errors="ignore").strip()
        if not line:
            continue

        print(line)

        if line.startswith(("$GPRMC", "$GNRMC")):
            try:
                msg = pynmea2.parse(line)
            except pynmea2.ParseError:
                continue

            if msg.status == "A":
                print(f"Latitude={msg.latitude} and Longitude={msg.longitude}")
            else:
                print("No GPS fix yet (move the antenna near a window/outdoors)")

except KeyboardInterrupt:
    print("\nStopped")
