# 🛰️Cubesat_Prototype
A low-cost CubeSat communication network prototype consisting of a rescue tower, satellite node, and ground station using LoRa communication and ESP32/Arduino microcontrollers.


# ℹAbstract
This project presents a compact satellite-based rescue communication system integrating a rescue tower, CubeSat, and ground station with a real-time dashboard. A distress signal transmitted from a DIY rescue tower antenna is received by the CubeSat, which acts as a relay and forwards the signal to the ground station. The ground station processes the data and displays it on a dashboard for monitoring and response. The system demonstrates the practical implementation of CubeSat communication, embedded systems, and long-range wireless transmission using LoRa technology.

# Introduction📒
The increasing need for reliable communication in remote and disaster-affected regions has led to the development of satellite-assisted emergency systems. This project focuses on designing and implementing a complete rescue communication chain consisting of a rescue tower, a CubeSat-based relay system, and a ground station integrated with a real-time dashboard.

The rescue tower is designed using a DIY antenna system and is responsible for transmitting distress signals. It is controlled by an ESP32 microcontroller, which interfaces with a LoRa RA-02 module to enable long-range, low-power communication.

The CubeSat module acts as a relay satellite and is controlled using a Raspberry Pi Zero W. It includes a communication subsystem based on the LoRa RA-02 module to receive and retransmit signals. The satellite is equipped with an automated antenna deployment system that uses a burn wire circuit mechanism to release the antenna after deployment. Additionally, it incorporates various sensors for monitoring environmental and system parameters, along with a dedicated power management system to efficiently regulate and distribute power among onboard components.

The ground station is responsible for receiving the relayed signal from the CubeSat and processing it for visualization. It is built using an Arduino Nano for signal handling and decoding, along with an ESP32 module for wireless communication and internet connectivity. The processed data is then transmitted to a dashboard interface, where the rescue message is displayed in real time.

Communication between all components is established using LoRa RA-02 modules, ensuring reliable long-range transmission with minimal power consumption. The integration of embedded systems, satellite communication principles, and IoT-based dashboard visualization makes this project a scalable and cost-effective solution for emergency communication applications.

# What are CubeSats?
CubeSats are a class of nanosatellites that use a standard size and form factor. The standard CubeSat size uses a “one unit” or “1U” measuring 10x10x10 cms and is extendable to larger sizes; 1.5, 2, 3, 6, and even 12U. Originally developed in 1999 by California Polytechnic State University at San Luis Obispo (Cal Poly) and Stanford University to provide a platform for education and space exploration. The development of CubeSats has advanced into its own industry with government, industry and academia collaborating for ever increasing capabilities. CubeSats now provide a cost effective platform for science investigations, new technology demonstrations and advanced mission concepts using constellations, swarms disaggregated systems. 
<img width="1925" height="809" alt="image" src="https://github.com/user-attachments/assets/c1b229c7-d5f7-4fd8-88fa-bec8c888d0fe" />

## Why CubeSats ?
- size 4x4x4 inches
- Mass=1.33kg
- allows for cost-effective development and deployment
- CubeSats have lower costs compared to large satellites.
- Shorter development times (CubeSats can be built within two years.)
- Flexible services(CubeSats can be used for different missions and purposes).

## History📖
The CubeSat concept originated in the late 1990s as a collaborative effort between Stanford University's Space Systems Development Laboratory (SSDL) and California Polytechnic State University (Cal Poly). Professors Bob Twiggs (Stanford) and Jordi Puig-Suari (Cal Poly) proposed the idea of a standardized, small satellite format to enable affordable space access for universities and other entities.

# Components and Structure of CubeSat
<img width="1011" height="688" alt="image" src="https://github.com/user-attachments/assets/c40eb6d1-0254-4549-b1b1-67029c11f4e4" />

## layer 1-Antenna

## layer 2-communication radio
![Comm Radio jpg](https://github.com/user-attachments/assets/2445d713-458b-430c-b34e-dcdbed2b15d3)


## layer 3-On Board Computer
![On Board Computer jpg](https://github.com/user-attachments/assets/884597f9-a8e2-4e25-a914-c30b1ea9f25b)


## layer 4-Attitude control rods and sensors
![Sensors jpg](https://github.com/user-attachments/assets/18ae4a67-b1fd-4ca9-b252-206e4094bce7)

## layer 5-power management system and antenna deploy ment system
<img width="1035" height="715" alt="image" src="https://github.com/user-attachments/assets/6fafc4e4-1374-4dd9-bae1-6034a87575e3" />


## layer 6-magnet and battery
![battery jpg](https://github.com/user-attachments/assets/24afe857-c1c7-4c78-bb11-d20adc6877af)


## Block Diagram For communication
<img width="1187" height="560" alt="image" src="https://github.com/user-attachments/assets/f1cdeadf-aaf6-464f-b8ff-36e7969fd3dc" />


## Rescue Management System
<img width="2138" height="1202" alt="image" src="https://github.com/user-attachments/assets/1031372b-e7c2-4a83-b71b-8fddf23633d2" />


# Weight of the CubeSat
<img width="960" height="1280" alt="sat1" src="https://github.com/user-attachments/assets/c3968eed-e283-4b0a-828b-9d9b30b77880" />

# Groundstation


## 📌 Pin Configuration

### LoRa RA-02
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| RST | GPIO 17 |
| CS (NSS) | GPIO 8 (CE0) |
| DIO0 | GPIO 4 |
| MOSI | GPIO 10 (SPI0 MOSI) |
| MISO | GPIO 9 (SPI0 MISO) |
| SCK | GPIO 11 (SPI0 SCLK) |
| VCC | 3.3V |
| GND | GND |

### BMP280
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| SDA | GPIO 2 (I2C SDA) |
| SCL | GPIO 3 (I2C SCL) |
| VCC | 3.3V |
| GND | GND |
| I2C Address | 0x76 |

### MPU-6050
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| SDA | GPIO 2 (I2C SDA) |
| SCL | GPIO 3 (I2C SCL) |
| VCC | 3.3V |
| GND | GND |
| AD0 | Pull HIGH → Address 0x69 ⚠️ |

> ⚠️ AD0 must be pulled HIGH to avoid I2C address conflict with DS3231 (both default to 0x68).  
> Update `MPU6050_ADDR = 0x69` in the code.

### DS3231 RTC
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| SDA | GPIO 2 (I2C SDA) |
| SCL | GPIO 3 (I2C SCL) |
| VCC | 3.3V |
| GND | GND |
| I2C Address | 0x68 |

### NEO-6M GPS
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| TX → RPi RX | GPIO 15 (UART RX) |
| RX → RPi TX | GPIO 14 (UART TX) |
| VCC | 3.3V |
| GND | GND |

### DHT22
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| DATA | GPIO 24 |
| VCC | 3.3V |
| GND | GND |

### MOSFET (Antenna Deploy)
| Pin/Signal | Raspberry Pi Zero W GPIO |
|---|---|
| GATE | GPIO 18 |

### Status LEDs
| LED | GPIO | Function |
|---|---|---|
| 🔴 Red | GPIO 23 | Power ON (solid) |
| 🟢 Green | GPIO 25 | Code Running (1Hz blink) |
| 🔵 Blue | GPIO 16 | Data Transmitting (blink on TX) |

> ⚠️ All LEDs require a **330Ω resistor** in series.
