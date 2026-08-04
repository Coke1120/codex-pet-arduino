# GUITION JC4880P443C-I-W bring-up

This guide records evidence established on a GUITION JC4880P443C-I-W with an ESP32-P4 revision v1.3 and 16 MB flash. Re-identify every connected board rather than treating these values as assumptions.

## Contents

- [Safety boundaries](#safety-boundaries)
- [Physical USB mapping](#physical-usb-mapping)
- [Establish source and toolchain identity](#establish-source-and-toolchain-identity)
- [Stop serial owners](#stop-serial-owners)
- [Enumerate and identify USB](#enumerate-and-identify-usb)
- [Confirm Download Mode, chip, and flash](#confirm-download-mode-chip-and-flash)
- [Verify the three flash regions](#verify-the-three-flash-regions)
- [Conservative P4 flash](#conservative-p4-flash)
- [Capture normal boot](#capture-normal-boot)
- [Test the protocol in one persistent session](#test-the-protocol-in-one-persistent-session)
- [Record the physical screen independently](#record-the-physical-screen-independently)
- [Keep firmware variants and handoffs unambiguous](#keep-firmware-variants-and-handoffs-unambiguous)
- [Verify glyph and icon rendering](#verify-glyph-and-icon-rendering)
- [Regression isolation learned on this repository](#regression-isolation-learned-on-this-repository)
- [Completion gate](#completion-gate)

## Safety boundaries

- Read the repository `AGENTS.md` and preserve uncommitted work.
- Do not reset, overwrite, or clean unrelated changes.
- Do not edit `todo.md` or `ToDo.md` as part of bring-up.
- Keep the ESP32-C6 out of scope unless the task explicitly includes it.
- Stop the host daemon, LaunchAgent, serial monitor, and any other port owner before probing, flashing, verification, or protocol testing.
- Never guess BOOT and RESET from left/right placement. Use confirmed silkscreen or a board photo.
- Re-scan after every reset, cable move, or esptool operation. A `/dev/cu.usbmodem*` suffix is not a stable connector identity.

## Physical USB mapping

On the vendor connector diagram used during bring-up:

| Diagram connector | Physical role | Observed USB identity | Use |
|---|---|---|---|
| #4, upper USB-C | ESP32-P4 USB Serial/JTAG | VID:PID `303A:1001` during normal application operation | Boot console and persistent application protocol |
| #5, lower USB-C | ESP32-P4 native USB-OTG | VID:PID `303A:0012` in ROM Download Mode | Conservative ROM download and flash operations |

Connector #4 can also expose the ROM loader in Download Mode, where esptool identifies USB-Serial/JTAG. Connector #5 is the clearest USB-OTG download path. The same macOS port suffix may appear on either connector at different times, so identify the active device instead of relying on the suffix.

A CH340-style `/dev/cu.usbserial*` device is not the maintained P4 console. With:

```text
CONFIG_ESP_CONSOLE_USB_SERIAL_JTAG=y
CONFIG_ESP_CONSOLE_SECONDARY_NONE=y
CONFIG_ESP_CONSOLE_UART_NUM=-1
```

silence on CH340 is expected and is not application-crash evidence.

## Establish source and toolchain identity

Run from the repository root:

```bash
git status --short --branch
git fetch origin main
git rev-parse HEAD
git rev-parse origin/main
```

Load the repository-supported ESP-IDF release and use its Python for all esptool operations:

```bash
source "$HOME/.espressif/frameworks/esp-idf-v5.5.1/export.sh"
PY="$(command -v python)"
"$PY" -m esptool version
```

## Stop serial owners

```bash
pkill -f 'codex_pet_daemon.py' 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.coke1120.codex-pet" 2>/dev/null || true
ps aux | grep '[c]odex_pet_daemon.py' || true
```

Keep the daemon stopped until boot, flash verification, and direct protocol checks are complete.

## Enumerate and identify USB

```bash
ls -l /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null || true
system_profiler SPUSBDataType
ioreg -r -c IOSerialBSDClient -l -w0
```

For every candidate:

```bash
lsof "$PORT"
```

No matching descriptor means no USB enumeration evidence. It is not a flash mismatch or firmware panic by itself; check cable data capability, connector, power, and boot mode first.

## Confirm Download Mode, chip, and flash

Only after Download Mode is explicit and the port has no owner:

```bash
"$PY" -m esptool \
  --chip esp32p4 \
  --port "$PORT" \
  --before no_reset \
  --after no_reset \
  chip_id
```

Run `flash_id` the same way. Record the exact port, VID:PID, esptool USB mode, chip model/revision, flash manufacturer/device ID, and detected size. If the installed esptool rejects `no_reset`, inspect its help before changing the command. Re-scan after each invocation because the device can disappear or re-enumerate even when reset suppression was requested.

## Verify the three flash regions

Verification is meaningful only against the exact binaries being claimed. First record their hashes:

```bash
shasum -a 256 \
  "$ARTIFACTS/bootloader/bootloader.bin" \
  "$ARTIFACTS/partition_table/partition-table.bin" \
  "$ARTIFACTS/codex_pet_jc4880p443c.bin"
```

Verify each region in a separate esptool invocation so the result is unambiguous:

```bash
"$PY" -m esptool --chip esp32p4 --port "$PORT" --baud 115200 \
  --before no_reset --after no_reset --no-stub verify_flash \
  0x2000 "$ARTIFACTS/bootloader/bootloader.bin"

# Re-scan and reassign PORT if necessary.
"$PY" -m esptool --chip esp32p4 --port "$PORT" --baud 115200 \
  --before no_reset --after no_reset --no-stub verify_flash \
  0x8000 "$ARTIFACTS/partition_table/partition-table.bin"

# Re-scan and reassign PORT if necessary.
"$PY" -m esptool --chip esp32p4 --port "$PORT" --baud 115200 \
  --before no_reset --after no_reset --no-stub verify_flash \
  0x10000 "$ARTIFACTS/codex_pet_jc4880p443c.bin"
```

Report bootloader, partition table, and application separately. A missing port means that verification did not execute; it is not a digest mismatch.

## Conservative P4 flash

Use the exact P4 build artifacts and confirmed P4 Download Mode:

```bash
"$PY" -m esptool \
  --chip esp32p4 \
  --port "$PORT" \
  --baud 115200 \
  --before default_reset \
  --after hard_reset \
  --no-stub \
  write_flash \
  --no-compress \
  --flash_mode dio \
  --flash_size 16MB \
  --flash_freq 80m \
  0x2000 "$ARTIFACTS/bootloader/bootloader.bin" \
  0x8000 "$ARTIFACTS/partition_table/partition-table.bin" \
  0x10000 "$ARTIFACTS/codex_pet_jc4880p443c.bin"
```

This command is P4-only. It does not authorize flashing the C6.

## Capture normal boot

Connect #4 before resetting into normal boot and keep one monitor open through the full cycle. Do not repeatedly run `chip_id` while trying to capture an application boot.

Expected successful sequence includes:

1. PSRAM initialization and test success.
2. `BSP_DISPLAY: Init display`.
3. DSI/ST7701 creation and initialization.
4. LVGL task startup.
5. GT911 touch identification and initialization.
6. Application readiness lines.

Expected readiness:

```text
Codex Pet ESP32-P4 ready
Board: JC4880P443C-I-W
Protocol: v2 lifecycle clock weather today-v1 usage-v1 quota-v1 codexbar-v1 wireless settings-v1
Commands: idle running waiting review ping status capabilities clock weather usage quota
```

The following were observed as non-fatal when readiness, protocol, touch, and the physical display all succeeded:

- ST7701 `LCD ID FF FF FF`
- `esp_lcd_panel_swap_xy ... not supported`
- the GT911 I2C pull-up warning

Do not suppress those messages merely to make logs cleaner. A panic after `BSP_DISPLAY: Init display`, a disappearing native port, or a reboot cycle must be captured verbatim and localized to the last completed stage.

## Test the protocol in one persistent session

Do not repeatedly close and reopen the serial port. Send:

```text
ping
status
capabilities
```

Expected reply forms are:

```text
pong
STATE <CURRENT_STATE>
CAPABILITIES 2 lifecycle clock weather today-v1 usage usage-v1 quota quota-v1 codexbar-v1 wireless settings-v1
```

`STATE IDLE` proves only the firmware's current lifecycle state. It does not prove the macOS daemon or Codex hooks are running. To validate host synchronization, start the configured daemon after direct protocol tests, trigger or observe a real Codex lifecycle event, and query status while that event is active.

## Record the physical screen independently

Ask the observer to choose one exact state:

- completely unlit
- backlight on but black
- white screen
- brief flash or reboot flicker
- public fallback red square
- expected custom pet/UI

Backlight does not prove panel initialization. Boot readiness proves display/UI construction returned but does not prove visible pixels. The public fallback is a central red square; seeing it proves the panel scanout path works but also proves no private generated pet asset was linked.

## Keep firmware variants and handoffs unambiguous

Keep each deliverable in its own directory:

| Variant | P4 wireless option | Intended evidence |
|---|---:|---|
| Safe display recovery | Off | P4 display, protocol, and host-sync baseline |
| Wireless candidate | On | P4-to-C6 startup plus unchanged display behavior |
| Matching C6 image | Separate target | Wireless coprocessor compatibility only when C6 flashing is explicitly in scope |

For every directory, include the source revision, target, relevant configuration,
flash offsets, and SHA-256 hashes calculated after the final copy. Never verify
one variant's flash against another variant's binaries. Keep private generated
pet source and unlicensed assets out of public bundles.

A copied bundle, clean build, or wireless-enabled image remains a candidate. It
becomes verified only after its exact binaries pass independent read-back,
normal boot, protocol, and observer-confirmed display checks on the target board.

## Verify glyph and icon rendering

Inspect the configured LVGL font before adding a Unicode weather or clock glyph.
A source-code emoji literal does not prove that the built font contains it. When
coverage is absent, prefer an LVGL primitive or a rights-safe converted image
asset instead of silently relying on the fallback glyph.

Build success proves only that the API and assets link. Inject every supported
weather condition and physically confirm the home-page weather icon, Today-page
weather icon, clock icon, and adjacent labels. Record unsupported/fallback glyphs,
clipping, color, and alignment separately from the underlying weather/time values.

## Regression isolation learned on this repository

Useful historical anchors:

- `603c26d`: previously known-good display firmware.
- `4d57319`: last pre-wireless display baseline used during isolation.
- `09ebb13`: introduced unconditional ESP-Hosted/C6 wireless startup.
- `894d9df`: main revision on which the blank-display regression was reproduced.

On the affected board, both historical display baselines rendered the central red fallback tile. The affected main build booted to black until the wireless backend was excluded from startup. Lowering task priority and suppressing only the ESP-Hosted constructor did not restore pixels. The root-cause boundary was unconditional wireless startup, not GPIO, DSI timing, BSP, or PSRAM.

The minimal recovery is to keep C6 wireless opt-in at build time, disable ESP-Hosted whole-archive constructor retention, and explicitly initialize ESP-Hosted when the option is enabled. Keep camera, Wi-Fi, BLE, and C6 changes out of a display-only diagnostic build.

When testing a wireless-enabled P4 build, preserve the `Wireless stage:` console
lines around `esp_hosted_init`, `connect_to_slave`, and `initialize_wifi`. Record
the last start/result pair together with the physical screen state; compile
success or a backend-ready label is not display evidence.

## Completion gate

Before declaring success, provide:

1. Actual USB device, VID:PID, connector, and port.
2. `chip_id` and `flash_id` results.
3. Independent bootloader, partition-table, and application verify results.
4. Normal boot result and exact readiness or panic evidence.
5. Exact `ping`, `status`, and `capabilities` replies.
6. Observer-confirmed screen state.
7. Root cause and minimal fix.
8. Changed files, artifact identity, and clean exact-target build/test results.
9. Post-flash independent verification and physical result.
10. Glyph/icon coverage and any hardware-only evidence still missing.

Do not push or publish private generated pet assets. Do not push firmware changes until the user requests it.
