/*
  Codex Pet - Arduino Uno R3 + 1.8-inch ST7735 (128x160)

  Serial commands (115200 baud, one command per line):
    idle | running | waiting | review | ping | status

  TFT_eSPI is configured in the library's User_Setup.h. See the supplied
  config/User_Setup.h and README.md before compiling.
*/

#include <TFT_eSPI.h>
#include <SPI.h>
#include <string.h>
#if __has_include("pet_generated.h")
#include "pet_generated.h"
#else
#include "pet_demo_rle.h"
#endif

TFT_eSPI tft = TFT_eSPI();

enum PetState : uint8_t { IDLE, RUNNING, WAITING, REVIEW };

PetState currentState = IDLE;
char serialLine[24] = {0};
uint8_t serialLength = 0;
bool discardingSerialLine = false;
uint8_t frame = 0;
unsigned long lastFrameAt = 0;

// Layout is portrait: large pet area plus a compact status bar.
const int16_t SCREEN_W = 128;
const int16_t SCREEN_H = 160;
const int16_t STATUS_H = 16;
const int16_t STATUS_Y = SCREEN_H - STATUS_H;
const int16_t PET_X = (SCREEN_W - PET_W) / 2;
const int16_t PET_Y = (STATUS_Y - PET_H) / 2;

// RGB565 colours chosen for a bright pixel-art look.
const uint16_t C_BG       = 0x10A5; // deep blue-black
const uint16_t C_PANEL    = 0x194B;
const uint16_t C_CYAN     = 0x4FFF;
const uint16_t C_BLUE     = 0x249F;
const uint16_t C_NAVY     = 0x0929;
const uint16_t C_WHITE    = 0xFFFF;
const uint16_t C_TEXT     = 0xD73F;
const uint16_t C_PINK     = 0xF9B8;
const uint16_t C_YELLOW   = 0xFFE0;
const uint16_t C_GREEN    = 0x4FEA;
const uint16_t C_ORANGE   = 0xFD20;
const uint16_t C_RED      = 0xF986;
const uint16_t C_SHADOW   = 0x0841;

const char *stateName(PetState state) {
  switch (state) {
    case RUNNING: return "RUNNING";
    case WAITING: return "WAITING";
    case REVIEW:  return "REVIEW";
    default:      return "IDLE";
  }
}

uint16_t stateColour(PetState state) {
  switch (state) {
    case RUNNING: return C_GREEN;
    case WAITING: return C_YELLOW;
    case REVIEW:  return C_PINK;
    default:      return C_CYAN;
  }
}

uint16_t frameInterval(PetState state) {
  switch (state) {
    case RUNNING: return 280;
    case WAITING: return 520;
    case REVIEW:  return 420;
    default:      return 650;
  }
}

void drawStatusBar() {
  const uint16_t colour = stateColour(currentState);
  tft.fillRect(0, STATUS_Y, SCREEN_W, STATUS_H, C_PANEL);
  tft.drawFastHLine(0, STATUS_Y, SCREEN_W, colour);
  tft.fillCircle(8, STATUS_Y + 8, 3, colour);
  tft.setTextDatum(ML_DATUM);
  tft.setTextFont(1);
  tft.setTextSize(1);
  tft.setTextColor(C_WHITE, C_PANEL);
  tft.drawString(stateName(currentState), 16, STATUS_Y + 8);
}

void drawPetSprite(uint8_t frameIndex, int16_t x, int16_t y) {
  const uint8_t *frameData = (const uint8_t *)pgm_read_ptr(&PET_FRAMES[frameIndex]);
  const uint16_t runCount = pgm_read_word(&PET_FRAME_LENGTHS[frameIndex]);
  // Frames are RLE-compressed: high 5 bits = run length minus one,
  // low 3 bits = 8-colour palette index.
  tft.startWrite();
  tft.setAddrWindow(x, y, PET_W, PET_H);
  for (uint16_t i = 0; i < runCount; ++i) {
    const uint8_t packed = pgm_read_byte(frameData + i);
    const uint8_t count = (packed >> 3) + 1;
    const uint8_t colourIndex = packed & 0x07;
    const uint16_t colour = colourIndex
        ? pgm_read_word(&PET_PALETTE[colourIndex])
        : C_BG;
    tft.pushColor(colour, count);
  }
  tft.endWrite();
}

void drawIdle(uint8_t f) {
  drawPetSprite(f & 1, PET_X, PET_Y);
}

void drawRunning(uint8_t f) {
  drawPetSprite(2 + (f & 1), PET_X, PET_Y);
}

void drawWaiting(uint8_t f) {
  drawPetSprite(4 + (f & 1), PET_X, PET_Y);
}

void drawReview(uint8_t f) {
  drawPetSprite(6 + (f & 1), PET_X, PET_Y);
}

void drawFrame() {
  // Each frame overwrites only the pet rectangle, avoiding full-stage flashes.
  switch (currentState) {
    case RUNNING: drawRunning(frame); break;
    case WAITING: drawWaiting(frame); break;
    case REVIEW:  drawReview(frame);  break;
    default:      drawIdle(frame);    break;
  }
  ++frame;
}

void setState(PetState next) {
  if (currentState != next) {
    currentState = next;
    frame = 0;
    drawStatusBar();
    drawFrame();
  }
  Serial.print(F("OK "));
  Serial.println(stateName(currentState));
}

void processCommand(char *command) {
  // Trim leading/trailing spaces and normalise to lowercase in-place.
  while (*command == ' ' || *command == '\t') ++command;
  char *end = command + strlen(command);
  while (end > command && (end[-1] == ' ' || end[-1] == '\t')) --end;
  *end = '\0';
  for (char *p = command; *p; ++p) {
    if (*p >= 'A' && *p <= 'Z') *p += ('a' - 'A');
  }

  if (!strcmp(command, "idle"))         setState(IDLE);
  else if (!strcmp(command, "running")) setState(RUNNING);
  else if (!strcmp(command, "waiting")) setState(WAITING);
  else if (!strcmp(command, "review"))  setState(REVIEW);
  else if (!strcmp(command, "ping"))    Serial.println(F("pong"));
  else if (!strcmp(command, "status")) {
    Serial.print(F("STATE "));
    Serial.println(stateName(currentState));
  } else if (*command) {
    Serial.print(F("ERR unknown command: "));
    Serial.println(command);
  }
}

void readSerialCommands() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (discardingSerialLine) {
        discardingSerialLine = false;
        serialLength = 0;
      } else if (serialLength > 0) {
        serialLine[serialLength] = '\0';
        processCommand(serialLine);
        serialLength = 0;
      }
    } else if (!discardingSerialLine && c >= 32 && c <= 126) {
      if (serialLength < sizeof(serialLine) - 1) {
        serialLine[serialLength++] = c;
      } else {
        serialLength = 0;
        discardingSerialLine = true;
        Serial.println(F("ERR command too long"));
      }
    }
  }
}

void setup() {
  Serial.begin(115200);
  tft.init();
  tft.setRotation(0); // Portrait 128 x 160.
  tft.fillScreen(C_BG);
  drawStatusBar();
  drawFrame();
  Serial.println(F("Codex Pet ready"));
  Serial.println(F("Commands: idle running waiting review ping status"));
}

void loop() {
  readSerialCommands();
  const unsigned long now = millis();
  if (now - lastFrameAt >= frameInterval(currentState)) {
    lastFrameAt = now;
    drawFrame();
  }
}
