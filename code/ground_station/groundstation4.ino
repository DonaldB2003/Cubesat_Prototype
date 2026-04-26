#include <SPI.h>
#include <LoRa.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>

// ---------- WiFi ----------
const char* ssid     = "Vlsi";
const char* password = "vlsi80211";

// ---------- Cloud ----------
const char* ingestUrl = "https://project--b25efbe7-457f-4d62-a06d-d530efb2d574.lovable.app/api/public/ingest-telemetry";
const char* deviceKey = "3e7bf048-e74e-4b75-9dae-09625b588874";
const char* deviceId  = "esp32-lora-01";

// ---------- LoRa Pins (ESP32) ----------
#define SS    18
#define RST   14
#define DIO0  26

// ---------- WiFi Connect ----------
void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nWiFi connected!");
  Serial.print("IP: ");
  Serial.println(WiFi.localIP());
}

// ---------- Send to Cloud ----------
void sendToCloud(String payload) {

  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  WiFiClientSecure client;
  client.setInsecure(); // dev only

  HTTPClient https;

  Serial.println("Sending: " + payload);

  if (https.begin(client, ingestUrl)) {

    https.addHeader("Content-Type", "text/plain");
    https.addHeader("x-device-key", deviceKey);

    int httpCode = https.POST(payload);

    Serial.print("HTTP Response: ");
    Serial.println(httpCode);

    Serial.println("Server: " + https.getString());

    https.end();
  } else {
    Serial.println("HTTPS failed");
  }
}

// ---------- Setup ----------
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("🚀 Starting System...");

  // WiFi
  connectWiFi();

  // LoRa Setup
  SPI.begin(5, 19, 27, SS); // SCK, MISO, MOSI, SS
  LoRa.setPins(SS, RST, DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("❌ LoRa init failed!");
    while (true);
  }

  Serial.println("✅ LoRa Initialized");
  Serial.println("📡 Waiting for packets...");
}

// ---------- Loop ----------
void loop() {

  int packetSize = LoRa.parsePacket();

  if (packetSize) {

    String received = "";

    while (LoRa.available()) {
      received += (char)LoRa.read();
    }

    received.trim();

    Serial.println("📡 Received: " + received);

    // Expected:
    // 1,1735000000,20.31,85.85,SOS,12345

    if (received.length() > 5) {

      String finalPayload = String(deviceId) + "|" + received;

      sendToCloud(finalPayload);
    }
  }
}
