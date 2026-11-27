import serial # Import serial package

from time import sleep

import webbrowser # Import package for opening link in the browser

import sys # Import system package



def GPS_Info():

global NMEA_buff

global lat_in_degrees

global long_in_degrees

nmea_time = []

nmea_latitude = []

nmea_longitude = []

nmea_time = NMEA_buff[0] # Extract time from GPGGA string

nmea_latitude = NMEA_buff[1] # Extract latitude from GPGGA string

nmea_longitude = NMEA_buff[3] # Extract longitude from GPGGA string



print("NMEA Time: ", nmea_time,'\n')

print ("NMEA Latitude:", nmea_latitude,"NMEA Longitude:", nmea_longitude,'\n')



lat = float(nmea_latitude) # Convert string into float for calculation

longi = float(nmea_longitude) # Convert string into float for calculation



lat_in_degrees = convert_to_degrees(lat) # Get latitude in degree decimal format

long_in_degrees = convert_to_degrees(longi) # Get longitude in degree decimal format



# Convert raw NMEA string into degree decimal format

def convert_to_degrees(raw_value):

decimal_value = raw_value/100.00

degrees = int(decimal_value)

mm_mmmm = (decimal_value - int(decimal_value))/0.6

position = degrees + mm_mmmm

position = "%.4f" %(position)

return position



gpgga_info = "$GPGGA,"

ser = serial.Serial ("/dev/ttyS0") # Open port with baud rate

GPGGA_buffer = 0

NMEA_buff = 0

lat_in_degrees = 0

long_in_degrees = 0



try:

while True:

received_data = (str)(ser.readline()) # Read NMEA string received

GPGGA_data_available = received_data.find(gpgga_info) # Check for NMEA GPGGA string

if (GPGGA_data_available>0):

GPGGA_buffer = received_data.split("$GPGGA,",1)[1] # Store data coming after "$GPGGA," string

NMEA_buff = (GPGGA_buffer.split(',')) # Store comma-separated data in buffer

GPS_Info() # Get time, latitude, longitude



print("lat in degrees:", lat_in_degrees," long in degree: ", long_in_degrees, '\n')

map_link = 'http://maps.google.com/?q=' + lat_in_degrees + ',' + long_in_degrees # Create a link to plot location on Google map

print("<<<<<<<>>>>>\n") # Press ctrl+c to plot on the map and exit

print("------------------------------------------------------------\n")



except KeyboardInterrupt:

webbrowser.open(map_link) # Open the current position information in Google Maps

sys.exit(0)
