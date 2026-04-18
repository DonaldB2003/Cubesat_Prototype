#include <SPI.h>
#include <LoRa.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ─── OLED ─────────────────────────────
#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// ─── Pins ─────────────────────────────
#define BUTTON 5
#define GREEN_LED 3
#define RED_LED 4

#define LORA_SS 10
#define LORA_RST 9
#define LORA_DIO0 2

// ─── Emergency Types ──────────────────
const char* types[3] = {"RESCUE", "MEDICAL", "LOST"};
int mode = 0;

// ─── Button ───────────────────────────
bool pressed = false;
unsigned long pressTime = 0;

// ─── State ────────────────────────────
bool active = false;

// ─── Packet Data ──────────────────────
uint16_t msgID = 0;

// ─── SEND PACKET ─────────────────────
void sendPacket() {
  msgID++;
  unsigned long timeStamp = millis();

  char msg[90];

  // Simple checksum
  unsigned long crc = msgID + timeStamp;

  snprintf(msg, sizeof(msg),
    "%u,%lu,22.57,88.36,%s,%lu",
    msgID,
    timeStamp,
    types[mode],
    crc
  );

  LoRa.beginPacket();
  LoRa.print(msg);
  LoRa.endPacket();

  Serial.println(msg);
}

// ─── DISPLAY ──────────────────────────
void showDisplay(const char* line1, const char* line2) {
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println(line1);
  display.println(line2);
  display.display();
}

// ─── SETUP ────────────────────────────
void setup() {
  Serial.begin(9600);

  pinMode(BUTTON, INPUT_PULLUP);
  pinMode(GREEN_LED, OUTPUT);
  pinMode(RED_LED, OUTPUT);

  // 🔴 RED LED ALWAYS ON
  digitalWrite(RED_LED, HIGH);

  // 🟢 GREEN OFF initially
  digitalWrite(GREEN_LED, LOW);

  // OLED init
  display.begin(SSD1306_SWITCHCAPVCC, 0x3C);
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);

  showDisplay("Select:", types[mode]);

  // LoRa init
  LoRa.setPins(LORA_SS, LORA_RST, LORA_DIO0);
  LoRa.begin(433E6);
}

// ─── LOOP ─────────────────────────────
void loop() {

  int state = digitalRead(BUTTON);

  // Button press
  if (state == LOW && !pressed) {
    pressed = true;
    pressTime = millis();
  }

  // Button release
  if (state == HIGH && pressed) {
    pressed = false;

    unsigned long duration = millis() - pressTime;

    if (duration < 700) {
      // 🔁 SHORT PRESS → Change message
      mode++;
      if (mode > 2) mode = 0;

      showDisplay("Select:", types[mode]);
    } 
    else {
      // 🔥 LONG PRESS → Toggle sending
      active = !active;

      if (active) {
        showDisplay("Sending:", types[mode]);
      } else {
        showDisplay("Stopped:", types[mode]);
        digitalWrite(GREEN_LED, LOW);
      }
    }
  }
  // ─── ACTIVE MODE ──────────────────
  if (active) {

    // GREEN LED blink
    digitalWrite(GREEN_LED, HIGH);

    sendPacket();

    delay(300);

    digitalWrite(GREEN_LED, LOW);

    delay(700);
  }
}
