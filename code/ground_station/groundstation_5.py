#include <SPI.h>
#include <LoRa.h>

// ─── PINOUT ────────────────────────────────────────
#define DIO0 26
#define RST  14
#define NSS  18
#define MOSI 27
#define MISO 19
#define SCLK 5

// ─── CRC16 — must match Pi ─────────────────────────
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

// ─── SPLIT HELPER ──────────────────────────────────
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

  Serial.println("=====================================================");
  Serial.println("  📡 ESP32 LoRa GROUND STATION — Relay + Sensor RX");
  Serial.println("=====================================================\n");

  SPI.begin(SCLK, MISO, MOSI, NSS);
  LoRa.setPins(NSS, RST, DIO0);

  if (!LoRa.begin(433E6)) {
    Serial.println("❌ LoRa init FAILED — check wiring");
    while (1);
  }

  // ── Must match Pi relay node settings ──────────
  LoRa.setSpreadingFactor(7);
  LoRa.setSignalBandwidth(125E3);
  LoRa.setCodingRate4(5);
  LoRa.enableCrc();

  Serial.println("✅ Ground station ready");
  Serial.println("   Freq : 433 MHz");
  Serial.println("   SF   : 7  |  BW: 125kHz  |  CR: 4/5  |  CRC: ON");
  Serial.println("\n⏳ Waiting for relay packets...\n");
}

// ─── LOOP ──────────────────────────────────────────
void loop() {
  int packetSize = LoRa.parsePacket();
  if (packetSize == 0) return;

  String received = "";
  while (LoRa.available())
    received += (char)LoRa.read();

  int rssi = LoRa.packetRssi();
  float snr = LoRa.packetSnr();

  Serial.println("=====================================================");
  Serial.println("📥 PACKET RECEIVED");
  Serial.print  ("   Raw    : "); Serial.println(received);
  Serial.print  ("   Length : "); Serial.print(packetSize); Serial.println(" bytes");
  Serial.print  ("   RSSI   : "); Serial.print(rssi); Serial.println(" dBm");
  Serial.print  ("   SNR    : "); Serial.print(snr);  Serial.println(" dB");
  Serial.println("-----------------------------------------------------");

  const int MAX_PARTS = 16;
  String parts[MAX_PARTS];
  int count = splitString(received, ',', parts, MAX_PARTS);

  // ════════════════════════════════════════════════
  //  RELAY + SENSOR PACKET — 15 fields
  //
  //  [0]  relay_id
  //  [1]  unix_time       (Pi real clock)
  //  [2]  rescue_lat      (from rescue tower)
  //  [3]  rescue_lon      (from rescue tower)
  //  [4]  emergency_type  (RESCUE / MEDICAL / LOST)
  //  [5]  rescue_msg_id   (tower packet counter)
  //  [6]  rescue_millis   (tower millis — NOT unix)
  //  [7]  bmp_temp        (Pi BMP280)
  //  [8]  pressure        (Pi BMP280)
  //  [9]  altitude        (Pi BMP280)
  //  [10] dht_temp        (Pi DHT22)
  //  [11] humidity        (Pi DHT22)
  //  [12] pi_lat          (Pi GPS)
  //  [13] pi_lon          (Pi GPS)
  //  [14] crc16
  // ════════════════════════════════════════════════
  if (count == 15) {

    long     relay_id      = parts[0].toInt();
    long     unix_time     = parts[1].toInt();
    float    rescue_lat    = parts[2].toFloat();
    float    rescue_lon    = parts[3].toFloat();
    String   emerg_type    = parts[4];
    long     rescue_msg_id = parts[5].toInt();
    long     rescue_millis = parts[6].toInt();
    float    bmp_temp      = parts[7].toFloat();
    float    pressure      = parts[8].toFloat();
    float    altitude      = parts[9].toFloat();
    float    dht_temp      = parts[10].toFloat();
    float    humidity      = parts[11].toFloat();
    float    pi_lat        = parts[12].toFloat();
    float    pi_lon        = parts[13].toFloat();
    uint16_t rx_crc        = (uint16_t)parts[14].toInt();

    // Reconstruct payload without last CRC field
    String payload = "";
    for (int i = 0; i < 14; i++) {
      payload += parts[i];
      if (i < 13) payload += ",";
    }

    uint16_t calc_crc = crc16((const uint8_t*)payload.c_str(), payload.length());
    bool     crc_ok   = (calc_crc == rx_crc);

    Serial.println("🛰️  RELAY + SENSOR PACKET");
    Serial.println();

    Serial.print  ("   Relay ID     : "); Serial.println(relay_id);
    Serial.print  ("   Unix Time    : "); Serial.println(unix_time);
    Serial.println();

    Serial.println("   🚨 RESCUE TOWER");
    Serial.print  ("   Type         : "); Serial.println(emerg_type);
    Serial.print  ("   Tower Msg ID : "); Serial.println(rescue_msg_id);
    Serial.print  ("   Tower Uptime : ");
    Serial.print  (rescue_millis / 1000); Serial.println(" sec");
    Serial.print  ("   Location     : ");
    Serial.print  (rescue_lat, 6); Serial.print(", ");
    Serial.println(rescue_lon, 6);
    Serial.println();

    Serial.println("   🌡️  BMP280 (Pi)");
    Serial.print  ("   Temp         : "); Serial.print(bmp_temp, 2); Serial.println(" °C");
    Serial.print  ("   Pressure     : "); Serial.print(pressure, 2); Serial.println(" hPa");
    Serial.print  ("   Altitude     : "); Serial.print(altitude, 2); Serial.println(" m");
    Serial.println();

    Serial.println("   💧 DHT22 (Pi)");
    if (dht_temp == 0.0 && humidity == 0.0) {
      Serial.println("   Temp         : N/A");
      Serial.println("   Humidity     : N/A");
    } else {
      Serial.print  ("   Temp         : "); Serial.print(dht_temp, 2); Serial.println(" °C");
      Serial.print  ("   Humidity     : "); Serial.print(humidity, 2); Serial.println(" %");
    }
    Serial.println();

    Serial.println("   📍 GPS (Pi Relay Position)");
    if (pi_lat == 0.0 && pi_lon == 0.0) {
      Serial.println("   Position     : No GPS fix");
    } else {
      Serial.print  ("   Latitude     : "); Serial.println(pi_lat, 6);
      Serial.print  ("   Longitude    : "); Serial.println(pi_lon, 6);
    }
    Serial.println();

    Serial.print("   CRC16        : ");
    if (crc_ok) {
      Serial.print("✅ OK  (0x"); Serial.print(calc_crc, HEX); Serial.println(")");
    } else {
      Serial.print("❌ FAIL — got 0x"); Serial.print(rx_crc, HEX);
      Serial.print(", expected 0x");    Serial.println(calc_crc, HEX);
    }

  }

  // ════════════════════════════════════════════════
  //  LEGACY DIRECT SENSOR PACKET — 10 fields
  //  (Pi transmitting directly, no relay)
  // ════════════════════════════════════════════════
  else if (count == 10) {

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

    String payload = "";
    for (int i = 0; i < 9; i++) {
      payload += parts[i];
      if (i < 8) payload += ",";
    }
    uint16_t calc_crc = crc16((const uint8_t*)payload.c_str(), payload.length());
    bool     crc_ok   = (calc_crc == rx_crc);

    Serial.println("📦 DIRECT SENSOR PACKET");
    Serial.println();
    Serial.print  ("   Msg ID   : "); Serial.println(msg_id);
    Serial.print  ("   UnixTime : "); Serial.println(timestamp);
    Serial.println();
    Serial.println("   📍 GPS");
    if (lat == 0.0 && lon == 0.0) {
      Serial.println("   Position : No GPS fix");
    } else {
      Serial.print  ("   Lat      : "); Serial.println(lat, 6);
      Serial.print  ("   Lon      : "); Serial.println(lon, 6);
    }
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
    Serial.print  ("   CRC16    : ");
    if (crc_ok) {
      Serial.print("✅ OK  (0x"); Serial.print(calc_crc, HEX); Serial.println(")");
    } else {
      Serial.print("❌ FAIL — got 0x"); Serial.print(rx_crc, HEX);
      Serial.print(", expected 0x");    Serial.println(calc_crc, HEX);
    }

  }

  // ════════════════════════════════════════════════
  //  UNKNOWN FORMAT
  // ════════════════════════════════════════════════
  else {
    Serial.println("⚠️  Unknown packet format");
    Serial.print  ("   Fields  : "); Serial.println(count);
    Serial.println("   Expected 15 (relay) or 10 (direct sensor)");
  }

  Serial.println("=====================================================\n");
}
