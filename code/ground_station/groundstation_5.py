#include <SPI.h>
#include <LoRa.h>

// ─── PINOUT ────────────────────────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

// ─── CRC16 (same as Pi) ────────────────────────────
uint16_t crc16(const uint8_t* data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (int j = 0; j < 8; j++) {
      crc = (crc & 1) ? (crc >> 1) ^ 0xA001 : crc >> 1;
    }
  }
  return crc;
}

// ─── SPLIT FUNCTION ────────────────────────────────
int splitString(const String& str, char delim, String* parts, int maxParts) {
  int count = 0, start = 0;
  for (int i = 0; i <= (int)str.length(); i++) {
    if (i == (int)str.length() || str[i] == delim) {
      if (count < maxParts)
        parts[count++] = str.substring(start, i);
      start = i + 1;
    }
  }
  return count;
}

// ─── SETUP ─────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  while (!Serial);

  Serial.println("\n=================================================");
  Serial.println("📡 LoRa GROUND STATION (SMART RECEIVER)");
  Serial.println("=================================================\n");

  SPI.begin(SCLK, MISO, MOSI, NSS);
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("❌ LoRa init FAILED");
    while (1);
  }

  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("✅ Ready — Waiting for packets...\n");
}

// ─── LOOP ──────────────────────────────────────────
void loop() {
  int packetSize = LoRa.parsePacket();
  if (!packetSize) return;

  String received = "";
  while (LoRa.available()) {
    received += (char)LoRa.read();
  }

  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();

  Serial.println("=================================================");
  Serial.println("📥 PACKET RECEIVED");
  Serial.print("Raw   : "); Serial.println(received);
  Serial.print("RSSI  : "); Serial.print(rssi); Serial.println(" dBm");
  Serial.print("SNR   : "); Serial.print(snr); Serial.println(" dB");
  Serial.println("-------------------------------------------------");

  const int MAX_PARTS = 20;
  String parts[MAX_PARTS];
  int count = splitString(received, ',', parts, MAX_PARTS);

  // ════════════════════════════════════════════════
  // 🛰️ RELAY + SENSOR PACKET (15 fields)
  // ════════════════════════════════════════════════
  if (count == 15) {

    long relay_id      = parts[0].toInt();
    long unix_time     = parts[1].toInt();
    float rescue_lat   = parts[2].toFloat();
    float rescue_lon   = parts[3].toFloat();
    String type        = parts[4];
    long rescue_id     = parts[5].toInt();
    long rescue_time   = parts[6].toInt();
    float bmp_temp     = parts[7].toFloat();
    float pressure     = parts[8].toFloat();
    float altitude     = parts[9].toFloat();
    float dht_temp     = parts[10].toFloat();
    float humidity     = parts[11].toFloat();
    float pi_lat       = parts[12].toFloat();
    float pi_lon       = parts[13].toFloat();
    uint16_t rx_crc    = parts[14].toInt();

    // Rebuild payload for CRC
    String payload = "";
    for (int i = 0; i < 14; i++) {
      payload += parts[i];
      if (i < 13) payload += ",";
    }

    uint16_t calc_crc = crc16((uint8_t*)payload.c_str(), payload.length());

    Serial.println("🛰️ RELAY + SENSOR DATA\n");

    Serial.println("🚨 Rescue Info:");
    Serial.print("Type       : "); Serial.println(type);
    Serial.print("Location   : ");
    Serial.print(rescue_lat, 6); Serial.print(", ");
    Serial.println(rescue_lon, 6);

    Serial.println("\n🌡️ BMP280:");
    Serial.print("Temp       : "); Serial.print(bmp_temp); Serial.println(" °C");
    Serial.print("Pressure   : "); Serial.print(pressure); Serial.println(" hPa");
    Serial.print("Altitude   : "); Serial.print(altitude); Serial.println(" m");

    Serial.println("\n💧 DHT22:");
    if (dht_temp == 0 && humidity == 0) {
      Serial.println("No data");
    } else {
      Serial.print("Temp       : "); Serial.print(dht_temp); Serial.println(" °C");
      Serial.print("Humidity   : "); Serial.print(humidity); Serial.println(" %");
    }

    Serial.println("\n📍 Pi GPS:");
    if (pi_lat == 0 && pi_lon == 0) {
      Serial.println("No fix");
    } else {
      Serial.print(pi_lat, 6); Serial.print(", ");
      Serial.println(pi_lon, 6);
    }

    Serial.print("\nCRC        : ");
    Serial.println(calc_crc == rx_crc ? "✅ OK" : "❌ FAIL");
  }

  // ════════════════════════════════════════════════
  // 📡 DIRECT RESCUE PACKET (6 fields)
  // ════════════════════════════════════════════════
  else if (count == 6) {

    Serial.println("📡 DIRECT RESCUE PACKET (bypassed relay)\n");

    Serial.print("ID   : "); Serial.println(parts[0]);
    Serial.print("Time : "); Serial.println(parts[1]);
    Serial.print("Lat  : "); Serial.println(parts[2]);
    Serial.print("Lon  : "); Serial.println(parts[3]);
    Serial.print("Type : "); Serial.println(parts[4]);

    Serial.println("\n⚠️ No sensor data included");
  }

  // ════════════════════════════════════════════════
  // ❌ UNKNOWN PACKET
  // ════════════════════════════════════════════════
  else {
    Serial.println("⚠️ Unknown packet format");
    Serial.print("Fields: "); Serial.println(count);
  }

  Serial.println("=================================================\n");
}
