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

TFT_eSPI tft = TFT_eSPI();

enum PetState : uint8_t { IDLE, RUNNING, WAITING, REVIEW };

PetState currentState = IDLE;
char serialLine[24] = {0};
uint8_t serialLength = 0;
uint8_t frame = 0;
unsigned long lastFrameAt = 0;

// Layout is portrait: 128 x 160.
const int16_t SCREEN_W = 128;
const int16_t SCREEN_H = 160;
const int16_t HEADER_H = 24;
const int16_t STATUS_Y = 136;
const int16_t STAGE_Y = HEADER_H;
const int16_t STAGE_H = STATUS_Y - STAGE_Y;

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
    case RUNNING: return 100;
    case WAITING: return 360;
    case REVIEW:  return 240;
    default:      return 420;
  }
}

void drawHeader() {
  tft.fillRect(0, 0, SCREEN_W, HEADER_H, C_NAVY);
  tft.drawFastHLine(0, HEADER_H - 1, SCREEN_W, C_CYAN);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(2);
  tft.setTextColor(C_WHITE, C_NAVY);
  tft.drawString("Codex Pet", SCREEN_W / 2, 11);
}

void drawStatusBar() {
  const uint16_t colour = stateColour(currentState);
  tft.fillRect(0, STATUS_Y, SCREEN_W, SCREEN_H - STATUS_Y, C_PANEL);
  tft.drawFastHLine(0, STATUS_Y, SCREEN_W, colour);
  tft.fillCircle(12, 148, 4, colour);
  tft.setTextDatum(ML_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(C_TEXT, C_PANEL);
  tft.drawString(stateName(currentState), 23, 148);
}

void drawPixelHeart(int16_t x, int16_t y, uint16_t colour) {
  tft.fillRect(x + 2, y, 4, 4, colour);
  tft.fillRect(x + 8, y, 4, 4, colour);
  tft.fillRect(x, y + 2, 14, 5, colour);
  tft.fillRect(x + 2, y + 7, 10, 3, colour);
  tft.fillRect(x + 5, y + 10, 4, 3, colour);
}

// Draw a compact robot-cat from primitives so Uno SRAM is not consumed by
// large image buffers. 'pose' changes legs/tail; 'blink' closes the eyes.
void drawPet(int16_t x, int16_t y, uint8_t pose, bool blink, uint16_t accent) {
  // Shadow.
  tft.fillEllipse(x, y + 35, 30, 6, C_SHADOW);

  // Tail: two simple poses.
  if (pose & 1) {
    tft.drawLine(x + 25, y + 17, x + 34, y + 10, accent);
    tft.drawLine(x + 34, y + 10, x + 38, y + 15, accent);
  } else {
    tft.drawLine(x + 25, y + 19, x + 35, y + 23, accent);
    tft.drawLine(x + 35, y + 23, x + 39, y + 18, accent);
  }

  // Ears and head.
  tft.fillTriangle(x - 23, y - 18, x - 9, y - 12, x - 18, y - 4, accent);
  tft.fillTriangle(x + 23, y - 18, x + 9, y - 12, x + 18, y - 4, accent);
  tft.fillRoundRect(x - 25, y - 12, 50, 34, 8, C_BLUE);
  tft.drawRoundRect(x - 25, y - 12, 50, 34, 8, accent);

  // Face panel and antenna.
  tft.fillRoundRect(x - 19, y - 6, 38, 21, 5, C_NAVY);
  tft.drawFastVLine(x, y - 20, 7, accent);
  tft.fillCircle(x, y - 22, 2, C_PINK);

  // Eyes.
  if (blink) {
    tft.drawFastHLine(x - 13, y + 3, 7, C_CYAN);
    tft.drawFastHLine(x + 6, y + 3, 7, C_CYAN);
  } else {
    tft.fillRect(x - 13, y, 6, 7, C_CYAN);
    tft.fillRect(x + 7, y, 6, 7, C_CYAN);
    tft.drawPixel(x - 11, y + 1, C_WHITE);
    tft.drawPixel(x + 9, y + 1, C_WHITE);
  }
  tft.drawPixel(x - 1, y + 9, C_PINK);
  tft.drawPixel(x, y + 10, C_PINK);
  tft.drawPixel(x + 1, y + 9, C_PINK);

  // Body and chest badge.
  tft.fillRoundRect(x - 20, y + 21, 40, 18, 6, C_BLUE);
  tft.drawRoundRect(x - 20, y + 21, 40, 18, 6, accent);
  tft.fillRect(x - 4, y + 25, 8, 8, accent);
  tft.fillRect(x - 2, y + 27, 4, 4, C_NAVY);

  // Legs alternate for running; tiny shift also gives idle breathing.
  if (pose & 1) {
    tft.fillRoundRect(x - 18, y + 36, 12, 6, 2, accent);
    tft.fillRoundRect(x + 8, y + 34, 12, 6, 2, accent);
  } else {
    tft.fillRoundRect(x - 20, y + 34, 12, 6, 2, accent);
    tft.fillRoundRect(x + 6, y + 36, 12, 6, 2, accent);
  }
}

void drawIdle(uint8_t f) {
  const int16_t bob = (f & 1) ? 1 : 0;
  drawPet(64, 77 + bob, f, (f % 6) == 5, C_CYAN);
  if ((f & 3) == 1) drawPixelHeart(91, 48, C_PINK);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString("ready", 64, 125);
}

void drawRunning(uint8_t f) {
  // Pet dashes side-to-side while speed lines move in the opposite phase.
  const int8_t offset = (f % 4 < 2) ? -5 : 5;
  for (uint8_t i = 0; i < 3; ++i) {
    int16_t lineX = 10 + i * 37 + ((f * 9) % 18);
    tft.drawFastHLine(lineX, 52 + i * 25, 13, C_GREEN);
  }
  drawPet(64 + offset, 76, f, false, C_GREEN);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(C_GREEN, C_BG);
  tft.drawString("coding...", 64, 125);
}

void drawWaiting(uint8_t f) {
  drawPet(64, 79, f, (f & 1), C_YELLOW);
  // Animated ellipsis / thought bubble.
  for (uint8_t i = 0; i < 3; ++i) {
    uint16_t c = (i <= (f % 3)) ? C_YELLOW : C_PANEL;
    tft.fillCircle(48 + i * 16, 42, 3, c);
  }
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(C_YELLOW, C_BG);
  tft.drawString("need input", 64, 125);
}

void drawReview(uint8_t f) {
  drawPet(58, 78, f, false, C_PINK);
  // A tiny document and scanning line.
  tft.fillRect(91, 48, 25, 32, C_WHITE);
  tft.drawRect(91, 48, 25, 32, C_PINK);
  tft.drawFastHLine(96, 56, 14, C_NAVY);
  tft.drawFastHLine(96, 63, 14, C_NAVY);
  tft.drawFastHLine(96, 70, 10, C_NAVY);
  tft.drawFastHLine(93, 52 + ((f % 4) * 7), 21, C_GREEN);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(C_PINK, C_BG);
  tft.drawString("reviewing", 64, 125);
}

void drawFrame() {
  // Redrawing only the stage avoids stale pixels without clearing header/status.
  tft.fillRect(0, STAGE_Y, SCREEN_W, STAGE_H, C_BG);
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
      if (serialLength > 0) {
        serialLine[serialLength] = '\0';
        processCommand(serialLine);
        serialLength = 0;
      }
    } else if (c >= 32 && c <= 126) {
      if (serialLength < sizeof(serialLine) - 1) {
        serialLine[serialLength++] = c;
      } else {
        serialLength = 0;
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
  drawHeader();
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
