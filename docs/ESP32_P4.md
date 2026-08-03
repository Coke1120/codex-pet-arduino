# ESP32-P4 target: GUITION JC4880P443C-I-W

This target adds an ESP-IDF/LVGL firmware alongside the original Arduino Uno
build. It is specifically configured for the enclosed **GUITION
JC4880P443C-I-W** variant with:

- ESP32-P4 main processor
- onboard ESP32-C6 wireless companion
- 4.3-inch 480×800 ST7701S MIPI-DSI IPS display
- GT911 capacitive touch controller
- internal camera

The current Codex Pet firmware contains no application code that opens the
camera, microphone, speaker, or ESP32-C6 networking. Camera inactivity still
needs confirmation on the physical unit because display/touch and camera share
board resources.

## Software stack

- ESP-IDF **5.5.1**
- LVGL 9.5.0 through `espressif/esp_lvgl_port` 2.8.0~1
- pinned community display/touch BSP commit `932af3aaee532af144087b6126aaa48eb9124be4`
  (the upstream repository name says P433C, while its internal board symbols say
  P443C; this exact commit is the version flashed successfully on the target unit)
- committed `dependencies.lock` for deterministic managed components
- 16 MB flash and HEX PSRAM at 80 MHz, matching the verified build configuration
- Native USB Serial/JTAG protocol transport; the host bridge keeps its 115200
  compatibility setting, although USB transport itself is not baud-clocked

The pin/timing assumptions are cross-checked against the hardware-tested
`ultramcu/guition-jc4880p4-bsp` documentation for JC4880P443C-I-W: LCD reset
GPIO5, backlight GPIO23, touch SDA/SCL GPIO7/8, DSI LDO channel 3 at 2.5 V,
480×800 RGB565, two 500 Mbps DSI lanes, and 34 MHz DPI clock. However, the
current firmware still uses the older stock-ST7701 BSP path; compile success is
not proof that its init sequence works on this physical unit. Do not substitute
a generic ESP32-P4 board configuration.

## Generate the selected Codex pet locally

The public build uses a one-pixel placeholder asset. To mirror the pet selected
in Codex Desktop, generate a private RGB565A8 asset translation unit before
building:

```bash
python3 tools/convert_codex_pet_p4.py \
  --spritesheet "$HOME/.codex/pets/<pet-folder>/spritesheet.webp" \
  --output esp32-p4/main/pet_generated.c
```

The generated `pet_generated.c` contains eight tightly cropped 396×612
alpha-preserving frames designed to make the character fill the 480×800 screen
and is intentionally gitignored. Do not commit or publish it unless you own or
have explicit permission to redistribute the artwork. Delete it to exercise the
public fallback build.

## Build

Install ESP-IDF 5.5.1 according to Espressif's setup guide, then open a shell in
which `idf.py` is available:

```bash
cd esp32-p4
idf.py set-target esp32p4
idf.py build
```

The first build downloads the pinned BSP and its managed dependencies.

## Identify the correct port

The exact host port depends on which USB connector is attached. This firmware
routes `stdin`/`stdout` through the ESP32-P4 native USB Serial/JTAG console,
which appears as an Espressif `/dev/cu.usbmodem*` device. The board's CH340
USB-to-UART bridge can enumerate separately as `/dev/cu.usbserial-*`, but it is
not the protocol console selected by this build. Compare the port list before
and after reconnecting the intended connector:

```bash
python3 mac/codex_pet_bridge.py --list
```

Use the reconnect test and ESP32-P4 `chip_id` probe to verify the native P4 port,
then pass it explicitly with `--port`.

## Flash and monitor

Put the P4 into download mode if the board is not already detected by the
flasher, then run:

```bash
cd esp32-p4
idf.py -p /dev/cu.<verified-p4-port> flash monitor
```

Exit the ESP-IDF monitor with `Ctrl+]`.

Expected boot lines include:

```text
Codex Pet ESP32-P4 ready
Board: JC4880P443C-I-W
Commands: idle running waiting review ping status
```

## Protocol verification

Use one persistent serial connection. Opening the port can reset the board.
From the repository root:

```bash
python3 mac/codex_pet_bridge.py \
  --port /dev/cu.<verified-p4-port> \
  --interactive
```

The exact protocol is shared with the Uno firmware:

```text
ping       -> pong
idle       -> OK IDLE
running    -> OK RUNNING
waiting    -> OK WAITING
review     -> OK REVIEW
status     -> STATE <CURRENT_STATE>
```

The status card is touch-enabled. Tapping it cycles through all four states for
a display/touch test without a host bridge.

## Physical acceptance checklist

After flashing, verify all of the following on the real board:

1. The display starts in portrait 480×800 orientation.
2. Colours are correct and the image is not shifted or cropped.
3. The mascot animates continuously without full-screen blinking.
4. Tapping the status card cycles `IDLE → RUNNING → WAITING → REVIEW`.
5. All four Serial commands return the exact acknowledgements above.
6. The backlight remains stable during a continuous run.
7. Confirm no camera indicator or stream activates; the application contains no
   camera initialization, but this remains a physical acceptance check.

If the panel stays dark, stop and check that the exact PCB model is
`JC4880P443C-I-W`; do not try random MIPI timings or GPIO assignments from a
similar P4 display.

## Codex Desktop integration

No separate host installation is required for the P4 target. The existing
`mac/codex_pet_daemon.py`, lifecycle hooks, and Windows installer use the same
newline-delimited protocol. Generic CH340 ports intentionally remain excluded
from automatic discovery because their metadata cannot prove which board is
attached; configure the daemon with the verified explicit P4 port. If both Uno
and P4 are connected, `auto` refuses to guess; run one daemon per board with an
explicit port if both should mirror the same lifecycle state.

## Verified boundary

The firmware has been clean-built and flashed to an ESP32-P4 revision v1.3 unit,
and the written bootloader/partition/application hashes were verified during
flashing. The earlier vector bring-up UI was visually confirmed. The newly
flashed selected-pet RGB565A8 frames, all four animations, touch mapping, and
Serial acknowledgements still require direct physical observation; no protocol
reply was received over the native USB console during the automated post-flash
probe. If the stock ST7701 route becomes unreliable, migrate to the
hardware-tested manual DPI bring-up rather than changing timings at random.
