#include <SPI.h>
#include <LoRa.h>

// ─── CUSTOM PINOUT ─────────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

// ─── CRC16 (must match Pi) ─────────────────
uint16_t crc16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      if (crc & 1)
        crc = (crc >> 1) ^ 0xA001;
      else
        crc >>= 1;
    }
  }
  return crc;
}

// ─── SPLIT STRING HELPER ───────────────────
int splitString(String str, char delim, String* parts, int maxParts) {
  int count = 0;
  int start = 0;
  for (int i = 0; i <= str.length(); i++) {
    if (i == str.length() || str[i] == delim) {
      if (count < maxParts) {
        parts[count++] = str.substring(start, i);
        start = i + 1;
      }
    }
  }
  return count;
}

// ─────────────────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("========================================");
  Serial.println(" 📡 ESP32 LoRa RECEIVER — CubeSat GS");
  Serial.println("========================================\n");

  SPI.begin(SCLK, MISO, MOSI, NSS);
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("❌ LoRa init FAILED — check wiring");
    while (1);
  }

  // ── These MUST match the Pi transmitter ──
  LoRa.setSpreadingFactor(7);       // SF7
  LoRa.setSignalBandwidth(125E3);   // BW 125 kHz
  LoRa.setCodingRate4(5);           // CR 4/5
  LoRa.enableCrc();                 // CRC ON

  Serial.println("✅ Receiver ready");
  Serial.println("   Freq : 433 MHz");
  Serial.println("   SF   : 7");
  Serial.println("   BW   : 125 kHz");
  Serial.println("   CR   : 4/5");
  Serial.println("   CRC  : ON");
  Serial.println("\n⏳ Waiting for packets...\n");
}

// ─────────────────────────────────────
void loop() {
  int packetSize = LoRa.parsePacket();

  if (packetSize == 0) return;

  // ─── Read raw packet ───────────────
  String received = "";
  while (LoRa.available()) {
    received += (char)LoRa.read();
  }

  Serial.println("=================================================");
  Serial.println("📥 PACKET RECEIVED");
  Serial.print  ("   Raw     : "); Serial.println(received);
  Serial.print  ("   Length  : "); Serial.print(packetSize); Serial.println(" bytes");
  Serial.print  ("   RSSI    : "); Serial.print(LoRa.packetRssi()); Serial.println(" dBm");
  Serial.print  ("   SNR     : "); Serial.print(LoRa.packetSnr());  Serial.println(" dB");
  Serial.println("-------------------------------------------------");

  // ─── Split into parts ──────────────
  const int MAX_PARTS = 12;
  String parts[MAX_PARTS];
  int partsCount = splitString(received, ',', parts, MAX_PARTS);

  // ─── FULL SENSOR PACKET: 10 fields ─
  if (partsCount == 10) {

    long     msg_id    = parts[0].toInt();
    long     timestamp = parts[1].toInt();
    float    lat       = parts[2].toFloat();
    float    lon       = parts[3].toFloat();
    float    bmp_temp  = parts[4].toFloat();
    float    pressure  = parts[5].toFloat();
    float    altitude  = parts[6].toFloat();
    float    dht_temp  = parts[7].toFloat();
    float    humidity  = parts[8].toFloat();
    uint16_t rx_crc    = (uint16_t)parts[9].toInt();

    // Reconstruct payload string to verify CRC
    String payload_no_crc = parts[0] + "," + parts[1] + "," +
                            parts[2] + "," + parts[3] + "," +
                            parts[4] + "," + parts[5] + "," +
                            parts[6] + "," + parts[7] + "," +
                            parts[8];

    uint16_t calc_crc = crc16((const uint8_t*)payload_no_crc.c_str(), payload_no_crc.length());
    bool crc_ok = (calc_crc == rx_crc);

    Serial.println("🛰️  FULL SENSOR DATA");
    Serial.println();
    Serial.print  ("   Msg ID   : "); Serial.println(msg_id);
    Serial.print  ("   UnixTime : "); Serial.println(timestamp);
    Serial.println();

    Serial.println("   📍 GPS");
    Serial.print  ("   Latitude : "); Serial.println(lat, 6);
    Serial.print  ("   Longitude: "); Serial.println(lon, 6);
    Serial.println();

    Serial.println("   🌡️  BMP280");
    Serial.print  ("   Temp     : "); Serial.print(bmp_temp, 2); Serial.println(" °C");
    Serial.print  ("   Pressure : "); Serial.print(pressure, 2); Serial.println(" hPa");
    Serial.print  ("   Altitude : "); Serial.print(altitude, 2); Serial.println(" m");
    Serial.println();

    Serial.println("   💧 DHT22");
    if (dht_temp == 0.0 && humidity == 0.0) {
      Serial.println("   Temp     : N/A");
      Serial.println("   Humidity : N/A");
    } else {
      Serial.print  ("   Temp     : "); Serial.print(dht_temp, 2); Serial.println(" °C");
      Serial.print  ("   Humidity : "); Serial.print(humidity, 2); Serial.println(" %");
    }
    Serial.println();

    Serial.print("   CRC16    : ");
    if (crc_ok) {
      Serial.print("✅ OK  (0x");
      Serial.print(calc_crc, HEX);
      Serial.println(")");
    } else {
      Serial.print("❌ FAIL — got 0x");
      Serial.print(rx_crc, HEX);
      Serial.print(", expected 0x");
      Serial.print(calc_crc, HEX);
      Serial.println();
    }

  }

  // ─── RELAY / LEGACY PACKET: 6 fields ─
  else if (partsCount == 6) {

    long   msg_id    = parts[0].toInt();
    long   timestamp = parts[1].toInt();
    float  lat       = parts[2].toFloat();
    float  lon       = parts[3].toFloat();
    String type      = parts[4];
    long   rx_crc    = parts[5].toInt();

    long calc_crc = msg_id + timestamp;

    Serial.println("📡 RELAY PACKET (legacy)");
    Serial.print  ("   Msg ID   : "); Serial.println(msg_id);
    Serial.print  ("   UnixTime : "); Serial.println(timestamp);
    Serial.print  ("   Latitude : "); Serial.println(lat, 6);
    Serial.print  ("   Longitude: "); Serial.println(lon, 6);
    Serial.print  ("   Type     : "); Serial.println(type);
    Serial.print  ("   CRC      : ");
    Serial.println(calc_crc == rx_crc ? "✅ OK" : "❌ FAIL");

  }

  // ─── UNKNOWN FORMAT ────────────────
  else {
    Serial.println("⚠️  Unknown packet format");
    Serial.print  ("   Fields parsed: "); Serial.println(partsCount);
    Serial.println("   Expected 10 (full) or 6 (relay)");
  }

  Serial.println("=================================================\n");
}
