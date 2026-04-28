/*
 * ═══════════════════════════════════════════════════════════════
 *   ESP32 GROUND STATION — DUAL MODE RECEIVER
 *   ✔ Accepts RESCUE packets (15 fields)
 *   ✔ Accepts SENSOR packets (type = NONE, GPS = 0,0)
 *   ✔ Sends both to dashboard
 * ═══════════════════════════════════════════════════════════════
 */

#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ─── USER CONFIG ─────────────────────────────────
#define WIFI_SSID       "Vlsi"
#define WIFI_PASSWORD   "vlsi80211"
#define DEVICE_KEY      "1q2w3e4r5t6y7u8i9o0p"
#define GROUND_ID       "GS-001"
#define INGEST_URL      "https://rescue-dash-hub.lovable.app/api/public/ingest-telemetry"
#define LORA_FREQ       433E6

// ─── ESP32 LoRa PINOUT ───────────────────────────
#define LORA_SS    18
#define LORA_RST   14
#define LORA_DIO0  26
#define LORA_SCK    5
#define LORA_MISO  19
#define LORA_MOSI  27

// ─── CRC16 ───────────────────────────────────────
uint16_t crc16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++) {
      if (crc & 1) crc = (crc >> 1) ^ 0xA001;
      else         crc = (crc >> 1);
    }
  }
  return crc;
}

// ─── CSV SPLIT ───────────────────────────────────
int splitCSV(const String& s, String out[], int maxFields) {
  int count = 0, start = 0;
  for (int i = 0; i <= s.length() && count < maxFields; i++) {
    if (i == s.length() || s.charAt(i) == ',') {
      out[count++] = s.substring(start, i);
      start = i + 1;
    }
  }
  return count;
}

// ─── WIFI CONNECT ────────────────────────────────
void connectWiFi() {
  Serial.printf("📶 Connecting to %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 20000) {
    delay(400);
    Serial.print(".");
  }

  if (WiFi.status() == WL_CONNECTED)
    Serial.printf("\n✅ WiFi connected. IP: %s\n", WiFi.localIP().toString().c_str());
  else
    Serial.println("\n⚠️ WiFi failed");
}

// ─── FORWARD TO DASHBOARD ────────────────────────
bool forwardToDashboard(const String& rawCsv, int rssi, float snr) {

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    if (WiFi.status() != WL_CONNECTED) return false;
  }

  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;

  if (!http.begin(client, INGEST_URL)) {
    Serial.println("❌ HTTP begin failed");
    return false;
  }

  http.addHeader("Content-Type", "text/plain");
  http.addHeader("x-device-key", DEVICE_KEY);

  String body = String(GROUND_ID) + "|" + rawCsv +
                "|rssi=" + String(rssi) +
                "|snr="  + String(snr, 2);

  Serial.println("📡 Sending to dashboard...");
  Serial.println(body);

  int code = http.POST(body);
  String resp = http.getString();

  Serial.printf("HTTP %d → %s\n", code, resp.c_str());

  http.end();

  return (code >= 200 && code < 300);
}

// ─── SETUP ───────────────────────────────────────
void setup() {

  Serial.begin(115200);
  delay(500);

  Serial.println("📡 GROUND STATION STARTING...");

  connectWiFi();

  SPI.begin(LORA_SCK, LORA_MISO, LORA_MOSI, LORA_SS);
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);

  if (!LoRa.begin(LORA_FREQ)) {
    Serial.println("❌ LoRa init failed!");
    while (true);
  }

  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();
  LoRa.setSyncWord(0x12);

  Serial.println("✅ LoRa Ready");
}

// ─── LOOP ────────────────────────────────────────
void loop() {

  int packetSize = LoRa.parsePacket();
  if (packetSize == 0) return;

  String raw = "";
  while (LoRa.available()) raw += (char) LoRa.read();
  raw.trim();

  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();

  Serial.println("\n📥 Packet:");
  Serial.println(raw);

  // ─── SPLIT ─────────────────────────
  String f[20];
  int n = splitCSV(raw, f, 20);

  // ❌ Reject if not 15 fields
  if (n != 15) {
    Serial.println("🚫 Rejected: Not 15 fields");
    return;
  }

  bool isSensorOnly = (f[4] == "NONE");

  // ─── CRC CHECK ─────────────────────
  int lastComma = raw.lastIndexOf(',');
  String payload = raw.substring(0, lastComma);

  uint16_t calc = crc16((const uint8_t*)payload.c_str(), payload.length());
  uint16_t got  = (uint16_t) f[14].toInt();

  if (calc != got) {
    Serial.println("❌ Rejected: CRC mismatch");
    return;
  }

  // ─── BASIC DATA ────────────────────
  float lat  = f[2].toFloat();
  float lon  = f[3].toFloat();
  float temp = f[7].toFloat();
  float hum  = f[11].toFloat();

  // ─── VALIDATION ────────────────────
  if (!isSensorOnly) {

    if (lat == 0.0 && lon == 0.0) {
      Serial.println("🚫 Rejected: Invalid GPS");
      return;
    }

    if (!(f[4] == "RESCUE" || f[4] == "MEDICAL" || f[4] == "LOST")) {
      Serial.println("🚫 Rejected: Invalid type");
      return;
    }
  }

  if (temp < -50 || temp > 100) {
    Serial.println("🚫 Rejected: Invalid temperature");
    return;
  }

  if (hum < 0 || hum > 100) {
    Serial.println("🚫 Rejected: Invalid humidity");
    return;
  }

  // ─── ACCEPT PACKET ─────────────────
  Serial.println(isSensorOnly ? "📡 SENSOR PACKET → Sending" 
                              : "🚨 RESCUE PACKET → Sending");

  bool ok = forwardToDashboard(raw, rssi, snr);

  Serial.println(ok ? "✅ Sent\n" : "⚠️ Send failed\n");
}
