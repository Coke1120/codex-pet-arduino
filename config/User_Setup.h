// TFT_eSPI setup for Arduino Uno R3 + 1.8-inch ST7735 128x160.
// Copy this file over the TFT_eSPI library's User_Setup.h.

#define USER_SETUP_INFO "Uno R3 ST7735 Codex Pet"

#define ST7735_DRIVER
#define TFT_WIDTH  128
#define TFT_HEIGHT 160

// Most 1.8-inch 128x160 modules use the red-tab initialisation.
// If the image is shifted or colours are wrong, see README troubleshooting.
#define ST7735_REDTAB

// Uno R3 hardware SPI wiring:
// MOSI/SDA = D11, SCK/SCL = D13. These are selected by the SPI peripheral.
#define TFT_CS   10
#define TFT_DC    8
#define TFT_RST   9

// Keep only the small built-in fonts to preserve Uno flash/RAM.
#define LOAD_GLCD
#define LOAD_FONT2

// Conservative clock for short breadboard/perfboard wires through a
// push-pull-capable 5V-to-3.3V translator such as TXS0108E.
#define SPI_FREQUENCY  8000000

// If red and blue are swapped, uncomment this line:
// #define TFT_RGB_ORDER TFT_BGR
