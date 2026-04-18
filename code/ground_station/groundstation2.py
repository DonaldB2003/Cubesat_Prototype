#include <SPI.h>
#include <LoRa.h>

// ─── PIN CONFIG ─────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

#define BAND 433E6

// ─── STATE ──────────────────────────
long lastMsgID = -1;

// ─── SETUP ──────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("=================================");
  Serial.println("   ESP32 Ground Station (RX+ACK)");
  Serial.println("=================================");

  SPI.begin(SCLK, MISO, MOSI, NSS);
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(BAND)) {
    Serial.println("❌ LoRa init failed!");
    while (1);
  }

  // Match Pi settings
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("✅ Listening...");
}

// ─── SEND ACK ───────────────────────
void sendACK(long msgID) {

  String ack = "ACK," + String(msgID);

  LoRa.beginPacket();
  LoRa.print(ack);
  LoRa.endPacket();

  Serial.println("📤 Sent ACK: " + ack);
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

    // ─── EXTRACT RELAY ID ───────────
    int firstComma = received.indexOf(',');

    if (firstComma == -1) {
      Serial.println("⚠️ Invalid packet");
      return;
    }

    String relayID = received.substring(0, firstComma);
    String payload = received.substring(firstComma + 1);

    Serial.println("🔁 Relay Node: " + relayID);

    // ─── SPLIT PAYLOAD ─────────────
    String parts[6];
    int idx = 0;
    String temp = "";

    for (int i = 0; i < payload.length(); i++) {
      if (payload[i] == ',') {
        parts[idx++] = temp;
        temp = "";
      } else {
        temp += payload[i];
      }

      if (idx >= 5) break;
    }
    parts[5] = temp;

    // ─── VALIDATE ──────────────────
    if (idx < 5) {
      Serial.println("⚠️ Parse error");
      return;
    }

    long msgID = parts[0].toInt();
    long timeStamp = parts[1].toInt();
    float lat = parts[2].toFloat();
    float lon = parts[3].toFloat();
    String type = parts[4];
    long rx_crc = parts[5].toInt();

    // ─── CRC CHECK (supports both old + XOR) ───
    long crc_add = msgID + timeStamp;
    long crc_xor = msgID ^ timeStamp;

    bool crc_ok = (rx_crc == crc_add) || (rx_crc == crc_xor);

    // ─── DISPLAY ───────────────────
    Serial.println("=================================");
    Serial.println("ID       : " + String(msgID));
    Serial.println("Time(ms) : " + String(timeStamp));
    Serial.println("Lat      : " + String(lat, 6));
    Serial.println("Lon      : " + String(lon, 6));
    Serial.println("Type     : " + type);

    if (crc_ok)
      Serial.println("CRC      : ✅ OK");
    else
      Serial.println("CRC      : ❌ FAIL");

    // ─── PACKET LOSS CHECK ─────────
    if (lastMsgID != -1 && msgID != lastMsgID + 1) {
      Serial.println("⚠️ Packet loss detected!");
    }

    lastMsgID = msgID;

    // ─── SIGNAL QUALITY ────────────
    Serial.print("RSSI     : ");
    Serial.print(LoRa.packetRssi());
    Serial.println(" dBm");

    Serial.print("SNR      : ");
    Serial.print(LoRa.packetSnr());
    Serial.println(" dB");

    Serial.println("=================================\n");

    // ─── SEND ACK ──────────────────
    if (crc_ok) {
      delay(50);   // small delay before TX
      sendACK(msgID);
    }
  }
}
