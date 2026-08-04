# ESP32-P4 target: GUITION JC4880P443C-I-W

This is the maintained ESP-IDF/LVGL firmware target. It is specifically
configured for the enclosed **GUITION
JC4880P443C-I-W** variant with:

- ESP32-P4 main processor
- onboard ESP32-C6 wireless companion
- 4.3-inch 480×800 ST7701S MIPI-DSI IPS display
- GT911 capacitive touch controller
- front MIPI-CSI camera path; the vendor package includes OV02C10 sensor material
- onboard microphone through the ES8311 audio codec
- ES8311/NS4150 speaker-output path with a two-pin speaker connector
- microSD/TF, lithium-battery, RS-485, UART, I2C, and GPIO expansion paths

The ESP32-P4 remains the application, display, and touch host. The firmware uses
the onboard ESP32-C6 as a Wi-Fi and Bluetooth Low Energy co-processor through
ESP-Hosted's four-bit SDIO transport. It does not initialize the camera,
microphone, speaker output, microSD/TF card, USB Host classes, battery telemetry,
RS-485, or the unused expansion connectors. The bare `I-W` board exposes a
speaker connector but does not guarantee that a speaker unit is fitted. Camera
inactivity still needs confirmation on the physical unit because display/touch
and camera share board resources.

The vendor snapshot contains reference APIs for several of these peripherals,
but it is not selected by the active CMake build. Their presence under `vendor/`
must not be interpreted as an installed or enabled Codex Pet feature. The active
application uses display, touch, USB Serial/JTAG, ESP32-C6 Wi-Fi station control,
and user-controlled BLE advertising only; BLE has no provisioning flow or custom
application GATT service.

## Software stack

- ESP-IDF **5.5.1**
- LVGL 9.5.0 through `espressif/esp_lvgl_port` 2.8.0~1
- pinned community display/touch BSP commit `932af3aaee532af144087b6126aaa48eb9124be4`
  (the upstream repository name says P433C, while its internal board symbols say
  P443C; this exact commit is the version flashed successfully on the target unit)
- committed `dependencies.lock` for deterministic managed components
- `esp_wifi_remote` 1.6.3 and ESP-Hosted 2.12.12 for the P4/C6 radio path
- four-bit SDIO between the P4 host and C6 co-processor: P4 CLK GPIO18, CMD
  GPIO19, D0–D3 GPIO14–17, and C6 reset GPIO54
- NimBLE host on the P4 with the controller and HCI transport on the C6; this is
  BLE only, not Classic Bluetooth
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
committed because it also contains videos, prebuilt firmware, host utility
bundles, and unrelated third-party packages.

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
complete action set inside the configured application partition. The generated
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

The P4 and C6 are separate flash targets. Build both images from the same
resolved ESP-Hosted release. Mixing a newly downloaded slave with the committed
host dependency can change the wire protocol and is unsupported.

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

Use the reconnect test and `esptool.py --port <port> chip_id` to distinguish the
ESP32-P4 protocol/flash port from the ESP32-C6 flash port. Confirm the reported
chip before writing either image; do not infer the target from a changing
`usbmodem` suffix.

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
Protocol: v2 lifecycle clock weather today-v1 usage-v1 quota-v1 codexbar-v1 wireless settings-v1
Commands: idle running waiting review ping status capabilities clock weather usage quota
```

## Build and flash the ESP32-C6 slave

Run the P4 build first so ESP-IDF materializes the exact ESP-Hosted version from
`dependencies.lock`. Then build the slave project inside that managed component:

```bash
cd esp32-p4/managed_components/espressif__esp_hosted/slave
idf.py set-target esp32c6
idf.py build
idf.py -p /dev/cu.<verified-c6-port> flash monitor
```

This source tree is ESP-Hosted 2.12.12, the same release linked into the P4 host
at the time of writing. Re-run the P4 build and check `dependencies.lock` before
flashing if dependency resolution changes. The slave defaults select ESP32-C6,
SDIO, Wi-Fi, and BLE HCI. Exit the monitor with `Ctrl+]`, reconnect the P4
protocol port, and reset the board.

The C6 flash connector and download-mode controls are board-specific. Verify the
C6 with `chip_id` before `flash`; an image written to the wrong chip can prevent
the display firmware or wireless co-processor from booting.

After the matching C6 image passes write verification, enable
`Codex Pet → Start the ESP32-C6 wireless backend` in the P4 `menuconfig`, rebuild
the P4, and repeat the P4 boot/display/protocol checks before testing either
radio. The default P4 configuration intentionally keeps this option disabled.

## Protocol verification

Use one persistent serial connection. Opening the port can reset the board.
From the repository root:

```bash
python3 mac/codex_pet_bridge.py \
  --port /dev/cu.<verified-p4-port> \
  --interactive
```

The lifecycle protocol uses these newline-delimited commands:

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
  -> CAPABILITIES 2 lifecycle clock weather today-v1 usage usage-v1 quota quota-v1 codexbar-v1 wireless settings-v1
clock <unix_epoch> <utc_offset_seconds>
  -> OK CLOCK
weather <current_c> <low_c> <high_c> <rain_pct> <condition> <updated_epoch>
  -> OK WEATHER
usage <latest_session_tokens> <today_tokens> <today_cached_input_tokens> <today_input_tokens> <updated_epoch>
  -> OK USAGE
quota <five_hour_remaining_pct> <five_hour_reset_epoch> <weekly_remaining_pct> <weekly_reset_epoch> <credits_tenths> <updated_epoch>
  -> OK QUOTA
```

Temperatures accept one decimal place. Conditions are `clear`,
`partly_cloudy`, `cloudy`, `fog`, `rain`, `snow`, `thunder`, or `unknown`.
An incomplete capability response is treated as a retryable connection failure
so a transient P4 response delay cannot silently disable v2 extensions. `quota`
uses `-1` with a zero reset epoch for an unavailable window or credit balance.
CodexBar remains responsible for authentication; no account identity is sent to
the P4. `usage` remains as a compatibility command for non-negative local token
counters and is not account quota data.

The daemon obtains Hong Kong data from the no-key
[Open-Meteo forecast API](https://open-meteo.com/en/docs), refreshes it every 15
minutes off the Serial thread, and stores a small weather-only cache beside the
session directory. Clock sync runs once per minute. The device keeps the last
weather value, fades it after 45 minutes, and marks it unavailable after three
hours rather than blanking the panel. Use `--no-weather` to disable network
weather retrieval. Weather data is attributed to Open-Meteo in the Today Panel.
Fetch failures retain the last cached value and produce a deduplicated daemon
warning; a successful refresh clears that warning state.

For a board that advertises `quota`, the daemon invokes CodexBar's official
Codex OAuth JSON CLI at most once per minute and sends only numeric quota fields.
It preserves the last good numeric cache when CodexBar is temporarily
unavailable. `--no-usage` disables both quota sync and legacy local usage sync.

## Touch navigation

- From Home, drag down from the top 82 pixels to reveal Today, swipe left to
  open Settings, or swipe up to open Codex Quota. The surface follows the finger
  and snaps open or closed on release.
- While the panel opens, the Pet moves below it and shows only its upper body.
  When lifecycle priority allows, the v2 000° look frame makes it look upward.
- Swipe up from Today, right from Settings, or down from Codex Quota to return
  Home. Settings and Quota also provide a Back control.
- When compiled in, Settings starts the non-blocking C6 backend and exposes Wi-Fi enable, scan,
  network selection, password entry for secured networks, forget, and a BLE
  Enable/Disable control. BLE starts disabled. Enable initializes the P4 NimBLE
  host and C6 controller before advertising as `Codex Pet`; Disable stops
  advertising, stops and deinitializes the host, then disables and deinitializes
  the C6 controller while retaining memory for a later Enable. Password text is
  cleared after submission and is never included in the UI status snapshot or
  logs. ESP-IDF stores the selected station configuration in flash until Forget
  clears it. If host startup does not synchronize within the bounded startup
  window, Settings exposes Disable so partially initialized BLE layers can be
  torn down; a failed shutdown exposes Retry. BLE lifecycle work runs separately
  from the Wi-Fi command manager so a delayed stop does not stall Wi-Fi controls.
  The blocking ESP-IDF stop runs in one tracked helper task. Settings waits at
  most five seconds; after a timeout, Retry rejoins that same operation instead
  of starting a second NimBLE stop. An immediate internal stop error is latched
  to protect NimBLE's static listener; restart the device before trying BLE
  again in that exceptional case.
- The wireless backend is disabled in the default P4 build. Enable
  `Codex Pet → Start the ESP32-C6 wireless backend` only after the matching C6
  image has been flashed and verified. A disabled backend intentionally leaves
  Wi-Fi and BLE controls unavailable.
- Codex Quota shows CodexBar's five-hour and weekly remaining percentages,
  reset times, optional credits, and update freshness. It marks data aging
  after five minutes and stale after 30 minutes. Older firmware can still use
  the legacy local-token `usage` command.
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
7. A left swipe opens Settings; a right swipe or Back returns Home without
   changing the current lifecycle animation.
8. Enable Wi-Fi, scan, connect to an open or WPA/WPA2 network, and confirm the
   Settings status and RSSI update. Use Forget and verify the saved network is
   cleared. Do not publish the SSID or password in test logs.
9. Enable BLE, use a second device to discover `Codex Pet`, then Disable it and
   confirm it disappears. Enable it again and confirm it reappears. Repeat the
   cycle while Wi-Fi is connected and verify Wi-Fi remains connected. This is
   BLE discovery only; Classic Bluetooth is not supported.
10. An upward swipe opens Codex Quota and shows the same remaining percentages,
    reset times, and credits reported by CodexBar. A downward swipe or Back
    returns Home. Leave the daemon stopped long enough to observe aging at five
    minutes and stale at 30 minutes.
11. The Today panel shows a clock icon next to its time and a condition icon;
    Home shows the same condition icon beside the weather label.
12. `capabilities`, all four lifecycle commands, `clock`, `weather`, `quota`,
    and legacy `usage` return the exact acknowledgements above.
13. Time continues advancing between minute syncs; a failed weather or CodexBar
    refresh does not block lifecycle or clock updates.
14. The backlight and scaled animation remain stable while Wi-Fi scans, BLE
    advertises continuously, and BLE is repeatedly disabled and enabled.
15. Confirm no camera indicator or stream activates; the application contains no
   camera initialization, but this remains a physical acceptance check.

If the panel stays dark, stop and check that the exact PCB model is
`JC4880P443C-I-W`; do not try random MIPI timings or GPIO assignments from a
similar P4 display.

## Codex Desktop integration

Install the macOS runtime with `bash mac/install.sh`. The daemon and lifecycle
hooks use the newline-delimited protocol above and negotiate v2 extensions. The
daemon supplies CodexBar quota fields over USB; Wi-Fi is not required for
lifecycle or quota sync. Generic CH340 ports intentionally remain excluded
from automatic discovery because their metadata cannot prove which board is
attached; configure the daemon with the verified explicit P4 port when automatic
selection is ambiguous. The maintained host environment is macOS.

## Verified boundary

The board/display route was previously clean-built and flashed to an ESP32-P4
revision v1.3 unit, and its written image hashes were verified. The full v2
animation asset has also been linked locally. The Settings and Codex Quota
surfaces, P4/C6 SDIO link, Wi-Fi connection, repeated BLE controller teardown and
restart, BLE advertising, CodexBar quota rendering, weather/clock icons, updated
Serial exchange, and concurrent display/touch stability still require the
physical checks above. If the stock ST7701 route
becomes unreliable, migrate to the hardware-tested manual DPI bring-up rather
than changing timings at random.
