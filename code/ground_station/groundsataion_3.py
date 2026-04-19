#include <SPI.h>
#include <LoRa.h>

// ─── CUSTOM PINOUT ─────────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("📡 ESP32 LoRa RECEIVER (from Pi Relay)");

  // Initialize SPI with custom pins
  SPI.begin(SCLK, MISO, MOSI, NSS);

  // Setup LoRa module
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("❌ LoRa init failed");
    while (1);
  }

  // MUST match Raspberry Pi settings
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("✅ Receiver ready\n");
}

void loop() {
  int packetSize = LoRa.parsePacket();

  if (packetSize) {
    String received = "";

    while (LoRa.available()) {
      received += (char)LoRa.read();
    }

    Serial.println("📥 RAW: " + received);

    // ─── PARSE SAME FORMAT AS PI ───────────
    // msg_id,timestamp,lat,lon,type,crc
    int partsCount = 0;
    String parts[6];

    int start = 0;
    for (int i = 0; i < received.length(); i++) {
      if (received[i] == ',') {
        parts[partsCount++] = received.substring(start, i);
        start = i + 1;
      }
    }
    parts[partsCount++] = received.substring(start);

    if (partsCount == 6) {
      long msg_id    = parts[0].toInt();
      long timestamp = parts[1].toInt();
      float lat      = parts[2].toFloat();
      float lon      = parts[3].toFloat();
      String type    = parts[4];
      long rx_crc    = parts[5].toInt();

      long calc_crc = msg_id + timestamp;

      Serial.println("=================================");
      Serial.print("ID       : "); Serial.println(msg_id);
      Serial.print("Time(ms) : "); Serial.println(timestamp);
      Serial.print("Location : "); 
      Serial.print(lat); Serial.print(", "); Serial.println(lon);
      Serial.print("Type     : "); Serial.println(type);

      if (calc_crc == rx_crc) {
        Serial.println("CRC      : ✅ OK");
      } else {
        Serial.println("CRC      : ❌ FAIL");
      }

      Serial.print("RSSI     : ");
      Serial.print(LoRa.packetRssi());
      Serial.println(" dBm");

      Serial.print("SNR      : ");
      Serial.print(LoRa.packetSnr());
      Serial.println(" dB");

      Serial.println("=================================\n");
    } else {
      Serial.println("⚠️ Invalid format\n");
    }
  }
}
