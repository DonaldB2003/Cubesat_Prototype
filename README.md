# Cubesat_Prototype
A low-cost CubeSat communication network prototype consisting of a rescue tower, satellite node, and ground station using LoRa communication and ESP32/Arduino microcontrollers.


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
