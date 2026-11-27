import serial  # Import serial package
import sys     # Import system package
import webbrowser  # Import package for opening link in the browser

# GPS settings
PORT = "/dev/serial0"   # same pins: GPIO14 (TX), GPIO15 (RX)
BAUD = 9600             # try 115200 if you see no data or garbage

lat_in_degrees = 0.0
long_in_degrees = 0.0
map_link = None


def convert_to_degrees(raw_value, hemisphere):
    """Convert NMEA ddmm.mmmm into decimal degrees."""
    degrees = int(raw_value / 100)
    minutes = raw_value - degrees * 100
    position = degrees + minutes / 60.0
    if hemisphere in ("S", "W"):
        position = -position
    return round(position, 6)


def gps_info(nmea_buff):
    """nmea_buff = fields after '$GPGGA,' / '$GNGGA,'"""
    global lat_in_degrees, long_in_degrees

    nmea_time = nmea_buff[0]        # time
    nmea_latitude = nmea_buff[1]    # latitude
    nmea_lat_dir = nmea_buff[2]     # N/S
    nmea_longitude = nmea_buff[3]   # longitude
    nmea_long_dir = nmea_buff[4]    # E/W
    fix_quality = nmea_buff[5]      # 0 = no fix

    print("NMEA Time:", nmea_time, "\n")

    if not nmea_latitude or not nmea_longitude or fix_quality == "0":
        print("No GPS fix yet (move the antenna near a window/outdoors)\n")
        return False

    print("NMEA Latitude:", nmea_latitude, "NMEA Longitude:", nmea_longitude, "\n")

    lat_in_degrees = convert_to_degrees(float(nmea_latitude), nmea_lat_dir)
    long_in_degrees = convert_to_degrees(float(nmea_longitude), nmea_long_dir)
    return True


ser = serial.Serial(PORT, BAUD, timeout=1)
print(f"Reading GPS on {PORT} @ {BAUD} ... (Ctrl+C to stop)\n")

try:
    while True:
        received_data = ser.readline().decode("ascii", errors="ignore").strip()

        if received_data:
            print(received_data)  # raw NMEA, so you can see data is arriving

        for header in ("$GPGGA,", "$GNGGA,"):
            if header in received_data:
                nmea_buff = received_data.split(header, 1)[1].split(",")
                if len(nmea_buff) >= 6 and gps_info(nmea_buff):
                    print("lat in degrees:", lat_in_degrees,
                          " long in degrees:", long_in_degrees, "\n")
                    map_link = ("http://maps.google.com/?q="
                                + str(lat_in_degrees) + "," + str(long_in_degrees))
                    print("Map link:", map_link)
                    print("------------------------------------------------------------\n")
                break

except KeyboardInterrupt:
    print("\nStopped")
    if map_link:
        print("Last position:", map_link)
        try:
            webbrowser.open(map_link)  # only works if the Pi has a desktop/browser
        except Exception:
            pass
    sys.exit(0)
