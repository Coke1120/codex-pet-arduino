# Codex Pet Arduino Desk Companion

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Arduino Uno](https://img.shields.io/badge/board-Arduino%20Uno-00979D?logo=arduino&logoColor=white)](https://docs.arduino.cc/hardware/uno-rev3/)
[![Display](https://img.shields.io/badge/display-ST7735%20128%C3%97160-5C2D91)](https://github.com/Bodmer/TFT_eSPI)
[![Python](https://img.shields.io/badge/bridge-Python%203-blue?logo=python&logoColor=white)](https://www.python.org/)

A tiny physical coding companion for an **Arduino Uno R3** and a **1.8-inch ST7735 128×160 TFT display**. A macOS Python serial bridge sends activity states over USB, and the display renders a bright pixel-art robot pet with animated `idle`, `running`, `waiting`, and `review` modes.

> Search keywords: Arduino desktop pet, Codex Pet, physical AI coding assistant, ST7735 animation, TFT_eSPI Arduino Uno, serial status display, pixel art robot pet, macOS Arduino bridge.

## Features

- Four animated states: `idle`, `running`, `waiting`, and `review`
- Colourful robot-cat drawn from lightweight graphics primitives
- USB Serial control at **115200 baud**
- Header, current-state indicator, and state-specific animation text
- Manual, one-shot, interactive, and stdin-streaming bridge modes
- Automatic serial-port discovery for common macOS Arduino ports
- Low-memory design without a full-screen framebuffer
- Documented `TFT_eSPI` `User_Setup.h` for the supplied wiring

## Demo states

| Command | Display behaviour | Suggested meaning |
|---|---|---|
| `idle` | Gentle breathing, blinking, and heart | Ready or finished |
| `running` | Fast leg motion and speed lines | Coding or executing |
| `waiting` | Thought bubble and blinking | Waiting for user input |
| `review` | Animated document scan | Reviewing code or tests |

Additional diagnostic commands are `ping` and `status`.

## Hardware

- Arduino Uno R3
- 1.8-inch ST7735 TFT, 128×160 pixels
- USB cable for power and Serial data
- Breadboard wires
- 5V-to-3.3V logic-level shifter when the display module does not provide one

### Wiring

| TFT pin | Arduino Uno R3 | Function |
|---|---:|---|
| VCC | 5V | Module power; confirm that the breakout accepts 5V |
| GND | GND | Common ground |
| CS | D10 | Chip select |
| RST | D9 | Reset |
| DC / A0 | D8 | Data/command |
| SDA / MOSI | D11 | Hardware SPI MOSI |
| SCL / SCK | D13 | Hardware SPI clock |
| BLK / LED | 5V | Backlight; confirm an onboard current-limiting resistor |

> [!CAUTION]
> The Uno R3 uses **5V GPIO logic**, while the ST7735 controller normally uses **3.3V logic**. A breakout that accepts 5V power does not necessarily accept 5V signals. Use level shifting on `CS`, `RST`, `DC`, `MOSI`, and `SCK` unless the module explicitly provides 5V-tolerant inputs.

## Repository layout

```text
arduino/CodexPet/CodexPet.ino  Arduino firmware
config/User_Setup.h            TFT_eSPI display and pin configuration
mac/codex_pet_bridge.py        macOS USB Serial bridge
mac/requirements.txt           Python dependency
```

## Quick start

### 1. Install and configure TFT_eSPI

Install [`TFT_eSPI`](https://github.com/Bodmer/TFT_eSPI) from the Arduino IDE Library Manager.

TFT_eSPI keeps controller and pin settings inside the library rather than the sketch. Back up the library's current `User_Setup.h`, then copy this repository's setup into place:

```bash
cp /path/to/Arduino/libraries/TFT_eSPI/User_Setup.h \
   /path/to/Arduino/libraries/TFT_eSPI/User_Setup.h.backup
cp config/User_Setup.h \
   /path/to/Arduino/libraries/TFT_eSPI/User_Setup.h
```

If the library is shared with other displays, copy the setup to:

```text
TFT_eSPI/User_Setups/Setup_CodexPet_Uno_ST7735.h
```

Then select only that file from `TFT_eSPI/User_Setup_Select.h`:

```cpp
#include <User_Setups/Setup_CodexPet_Uno_ST7735.h>
```

### 2. Upload the firmware

1. Open `arduino/CodexPet/CodexPet.ino` in Arduino IDE.
2. Select **Tools → Board → Arduino Uno**.
3. Select the board's `/dev/cu.usbmodem...` port.
4. Click **Verify**, then **Upload**.
5. Open Serial Monitor at **115200 baud** with newline enabled.
6. Send `idle`, `running`, `waiting`, or `review`.

### 3. Install the Mac bridge

```bash
cd mac
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

List serial ports:

```bash
python3 codex_pet_bridge.py --list
```

Start interactive mode:

```bash
python3 codex_pet_bridge.py --port auto --interactive
```

Send one state:

```bash
python3 codex_pet_bridge.py --port auto --state running
```

Stream newline-delimited states from another program:

```bash
printf 'running\nwaiting\nreview\nidle\n' | \
  python3 codex_pet_bridge.py --port auto --stdin
```

Opening an Uno serial port usually resets the board. The bridge therefore waits for startup and performs a small `ping` handshake before sending states.

## Connecting a coding workflow

The most reliable integration is for the process that knows the real activity phase to write explicit newline-delimited states to a persistent `--stdin` bridge:

```text
running
waiting
review
idle
```

Keeping one bridge process open avoids resetting the Uno for every transition. A wrapper can send `running` before a task, `waiting` when input is required, `review` during review or test phases, and `idle` on completion.

## TFT troubleshooting

- **White or black screen:** check common ground, `CS/DC/RST`, `MOSI/SCK`, and confirm that the controller is ST7735.
- **Shifted or cropped image:** try one of `ST7735_BLACKTAB`, `ST7735_GREENTAB`, or `ST7735_GREENTAB2` instead of `ST7735_REDTAB`. Enable only one.
- **Red and blue swapped:** enable `#define TFT_RGB_ORDER TFT_BGR` in `User_Setup.h`.
- **Flicker or corrupted pixels:** shorten wires, verify level shifting, and reduce `SPI_FREQUENCY` from 8 MHz to 4 MHz.
- **Limited animation performance:** TFT_eSPI is primarily optimised for 32-bit MCUs. The project avoids large buffers so it can use the generic AVR path, but an RP2040 or ESP32 provides smoother animation and more room for sprites.

## Ideas for expansion

- Add `success`, `error`, `sleeping`, or notification states
- Store compact RGB565 sprite frames in `PROGMEM`
- Add an SD card for image assets, with a separate chip-select pin
- Move to RP2040 or ESP32 for `TFT_eSprite` double buffering
- Add a buzzer, buttons, rotary encoder, or ambient-light sensor
- Control the backlight through a suitable transistor or MOSFET
- Extend the protocol with heartbeats, sequence IDs, and timeout fallback
- Build Linux and Windows serial bridge adapters

## Compatibility notes

TFT_eSPI describes itself as a library for 32-bit processors, while its current source also contains a generic AVR path. This project is intentionally conservative for the Uno's 2 KB SRAM and does not allocate a 128×160 framebuffer. For a new build where the microcontroller is flexible, RP2040 or ESP32 is recommended.

## Contributing

Bug reports, display-tab findings, bridge improvements, and new lightweight animations are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

## Security

Do not include serial-device inventories, usernames, home-directory paths, credentials, or private logs in issues. See [SECURITY.md](SECURITY.md) for responsible reporting.

## Support

If this project is useful, you can [sponsor its maintenance on GitHub](https://github.com/sponsors/Coke1120).

## License

Released under the [MIT License](LICENSE).

## Acknowledgements and trademark notice

- Display support is provided by the community-maintained [`TFT_eSPI`](https://github.com/Bodmer/TFT_eSPI) library.
- Arduino is a trademark of Arduino SA.
- OpenAI and Codex are trademarks of OpenAI. This independent community project is not affiliated with or endorsed by OpenAI.
