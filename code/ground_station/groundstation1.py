#include <SPI.h>
#include <LoRa.h>

// ─── PIN CONFIG ─────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

// ─── SETTINGS ───────────────────────
#define BAND 433E6

// ─── SETUP ──────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("=================================");
  Serial.println("   ESP32 LoRa Ground Station");
  Serial.println("=================================");

  // SPI setup
  SPI.begin(SCLK, MISO, MOSI, NSS);

  // LoRa setup
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(BAND)) {
    Serial.println("❌ LoRa init failed!");
    while (1);
  }

  // Match your Pi settings
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("✅ LoRa Ready - Listening...");
}

// ─── LOOP ───────────────────────────
void loop() {

  int packetSize = LoRa.parsePacket();

  if (packetSize) {

    String received = "";

    while (LoRa.available()) {
      received += (char)LoRa.read();
    }

    Serial.println("\n📥 RAW: " + received);

    // ─── PARSE RELAY PACKET ─────────
    // Expected format:
    // 2,MSG_ID,TIME,LAT,LON,TYPE,CRC

    int firstComma = received.indexOf(',');

    if (firstComma == -1) {
      Serial.println("⚠️ Invalid packet");
      return;
    }

    String relayID = received.substring(0, firstComma);
    String payload = received.substring(firstComma + 1);

    Serial.println("🔁 Relay Node ID: " + relayID);

    // Split payload
    String parts[6];
    int index = 0;

    for (int i = 0; i < payload.length(); i++) {
      if (payload.charAt(i) == ',') {
        parts[index++] = payload.substring(0, i);
        payload = payload.substring(i + 1);
        i = -1;
      }
      if (index >= 5) break;
    }
    parts[5] = payload;

    // ─── DISPLAY CLEAN DATA ─────────
    Serial.println("=================================");

    if (index >= 5) {
      Serial.println("ID       : " + parts[0]);
      Serial.println("Time(ms) : " + parts[1]);
      Serial.println("Lat      : " + parts[2]);
      Serial.println("Lon      : " + parts[3]);
      Serial.println("Type     : " + parts[4]);

      // CRC check
      long msgID = parts[0].toInt();
      long timeStamp = parts[1].toInt();
      long rx_crc = parts[5].toInt();

      long calc_crc = msgID + timeStamp;

      if (calc_crc == rx_crc) {
        Serial.println("CRC      : ✅ OK");
      } else {
        Serial.println("CRC      : ❌ FAIL");
      }
    } else {
      Serial.println("⚠️ Parsing failed");
    }

    // Signal quality
    Serial.print("RSSI     : ");
    Serial.print(LoRa.packetRssi());
    Serial.println(" dBm");

    Serial.print("SNR      : ");
    Serial.print(LoRa.packetSnr());
    Serial.println(" dB");

    Serial.println("=================================\n");
  }
}
