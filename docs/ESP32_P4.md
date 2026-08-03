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

## Vendor BSP snapshot

The redistributable BSP source subset from the supplied JC4880P443C-I-W vendor
archive is preserved under
[`vendor/jc4880p443c_i_w_bsp/`](../vendor/jc4880p443c_i_w_bsp/). Its provenance,
archive checksum, per-file archive hashes, component versions, and licenses are
recorded beside the sources. It includes the package's model-specific
`guition-jc4880p443` board configuration and implementation as well as its
required/common ESP-IDF components. The full 309 MB resource archive is not
committed because it also contains videos, prebuilt firmware, Windows utilities,
and unrelated third-party packages.

This snapshot is not selected by CMake; its model-specific source depends on the
surrounding Xiaozhi application abstractions. The active firmware remains on the
commit-pinned `csvke/esp32_p4_jc4880p433c_bsp` component that passed the current
build and board/display bring-up. Migrating to the vendor snapshot is a separate
hardware change and requires the complete physical acceptance checklist below.

The pin/timing assumptions are cross-checked against the hardware-tested
`ultramcu/guition-jc4880p4-bsp` documentation for JC4880P443C-I-W: LCD reset
GPIO5, backlight GPIO23, touch SDA/SCL GPIO7/8, DSI LDO channel 3 at 2.5 V,
480×800 RGB565, two 500 Mbps DSI lanes, and 34 MHz DPI clock. However, the
current firmware still uses the older stock-ST7701 BSP path; compile success is
not proof that its init sequence works on this physical unit. Do not substitute
a generic ESP32-P4 board configuration.

## Generate the selected Codex pet locally

The public build uses a small red test tile instead of redistributable character
art. To mirror the pet selected in Codex Desktop, generate a private RGB565A8
asset translation unit before building:

```bash
python3 tools/convert_codex_pet_p4.py \
  --spritesheet "$HOME/.codex/pets/<pet-folder>/spritesheet.webp" \
  --output esp32-p4/main/pet_generated.c
```

The generated `pet_generated.c` contains all 73 used cells from the Codex Pet v2
8×11 contract: nine standard animation rows plus 16 clockwise look directions.
Frames remain at a 152×204 alpha-preserving source size and LVGL renders them at
an exact integer 3× scale (456×612). Avoiding 73 pre-scaled bitmaps keeps the
complete action set inside the 8,128 KiB application partition. The generated
translation unit is intentionally gitignored; do not commit or publish it unless
you own or have explicit permission to redistribute the artwork. Delete it to
exercise the public fallback build.

The v2 rows are `idle`, `running-right`, `running-left`, `waving`, `jumping`,
`failed`, `waiting`, active-task `running`, and `review`, followed by 16 look
directions from 000° (up) clockwise through 337.5°. The firmware action manifest
adds semantic aliases such as `blink`, `look_up`, `present`, `think`, `happy`,
`sleepy`, `turn_around`, and weather reactions without duplicating image data.

## Build

Install ESP-IDF 5.5.1 according to Espressif's setup guide, then open a shell in
which `idf.py` is available:

```bash
cd esp32-p4
idf.py set-target esp32p4
idf.py build
```

The first build downloads the pinned BSP and its managed dependencies. Review
[`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) before redistributing a
firmware binary: the pinned community BSP snapshot does not include an explicit
license file, so this repository publishes source/build instructions rather than
prebuilt binaries containing that component.

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
Protocol: v2 lifecycle clock weather today-v1
Commands: idle running waiting review ping status capabilities clock weather
```

## Protocol verification

Use one persistent serial connection. Opening the port can reset the board.
From the repository root:

```bash
python3 mac/codex_pet_bridge.py \
  --port /dev/cu.<verified-p4-port> \
  --interactive
```

The lifecycle protocol remains shared with the Uno firmware:

```text
ping       -> pong
idle       -> OK IDLE
running    -> OK RUNNING
waiting    -> OK WAITING
review     -> OK REVIEW
status     -> STATE <CURRENT_STATE>
```

The P4 advertises optional extensions before the daemon uses them:

```text
capabilities
  -> CAPABILITIES 2 lifecycle clock weather today-v1
clock <unix_epoch> <utc_offset_seconds>
  -> OK CLOCK
weather <current_c> <low_c> <high_c> <rain_pct> <condition> <updated_epoch>
  -> OK WEATHER
```

Temperatures accept one decimal place. Conditions are `clear`,
`partly_cloudy`, `cloudy`, `fog`, `rain`, `snow`, `thunder`, or `unknown`.
Unsupported or legacy boards explicitly reject the capability probe, and the
daemon then sends lifecycle commands only. A probe timeout is treated as a
retryable connection failure so a transient P4 response delay cannot silently
disable Today Pet extensions.

The daemon obtains Hong Kong data from the no-key
[Open-Meteo forecast API](https://open-meteo.com/en/docs), refreshes it every 15
minutes off the Serial thread, and stores a small weather-only cache beside the
session directory. Clock sync runs once per minute. The device keeps the last
weather value, fades it after 45 minutes, and marks it unavailable after three
hours rather than blanking the panel. Use `--no-weather` to disable network
weather retrieval. Weather data is attributed to Open-Meteo in the Today Panel.
Fetch failures retain the last cached value and produce a deduplicated daemon
warning; a successful refresh clears that warning state.

## Touch interaction

- Drag down from the top 82 pixels to reveal the Today Panel; the card follows
  the finger and snaps open or closed on release.
- While the panel opens, the Pet moves below it and shows only its upper body.
  When lifecycle priority allows, the v2 000° look frame makes it look upward.
- Push the panel upward to return home.
- Tap the Pet for a random blink, wave, jump, look, turn, or excited reaction.
  A 2.5-second cooldown prevents repeated interruptions, and the Pet returns to
  the newest `idle`, `running`, `waiting`, or `review` state afterward.
- Tap the bottom status card to cycle all four lifecycle states for a hardware
  test. Weather does not interrupt active work; a thunder condition is treated
  as a critical reaction.

## Physical acceptance checklist

After flashing, verify all of the following on the real board:

1. The display starts in portrait 480×800 orientation.
2. Colours are correct and the image is not shifted or cropped.
3. The mascot animates continuously without full-screen blinking.
4. Tapping the Pet produces varied one-shot reactions and respects the cooldown.
5. Tapping the status card cycles `IDLE → RUNNING → WAITING → REVIEW`.
6. A top-edge drag follows the finger, opens the Today Panel, moves the Pet to
   an upper-body composition, and an upward push restores the home view.
7. `capabilities`, all four lifecycle commands, `clock`, and `weather` return the
   exact acknowledgements above; a legacy board remains lifecycle-only.
8. Time continues advancing between minute syncs; a failed weather request does
   not block lifecycle or clock updates.
9. The backlight and scaled animation remain stable during a continuous run.
10. Confirm no camera indicator or stream activates; the application contains no
   camera initialization, but this remains a physical acceptance check.

If the panel stays dark, stop and check that the exact PCB model is
`JC4880P443C-I-W`; do not try random MIPI timings or GPIO assignments from a
similar P4 display.

## Codex Desktop integration

No separate host installation is required for the P4 target. The existing
`mac/codex_pet_daemon.py`, lifecycle hooks, and Windows installer use the same
newline-delimited lifecycle protocol and negotiate P4-only extensions. Generic CH340 ports intentionally remain excluded
from automatic discovery because their metadata cannot prove which board is
attached; configure the daemon with the verified explicit P4 port. If both Uno
and P4 are connected, `auto` refuses to guess; run one daemon per board with an
explicit port if both should mirror the same lifecycle state.

## Verified boundary

The board/display route was previously clean-built and flashed to an ESP32-P4
revision v1.3 unit, and its written image hashes were verified. This Today Pet
revision has also been clean-linked locally with a private 73-frame v2 asset:
the application image is `0x720560` bytes and leaves `0xcfaa0` bytes (10%) in the
`0x7f0000` app partition. The new integer-scaled animation, Today Panel gestures,
clock/weather exchange, and Serial acknowledgements still require direct
physical observation. If the stock ST7701 route becomes unreliable, migrate to
the hardware-tested manual DPI bring-up rather than changing timings at random.
