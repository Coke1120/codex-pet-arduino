# Codex Pet MCU Desk Companion

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Hardware](https://img.shields.io/badge/hardware-JC4880P443C--I--W-E7352C)](docs/ESP32_P4.md)
[![Host](https://img.shields.io/badge/host-macOS-000000?logo=apple&logoColor=white)](docs/CODEX_DESKTOP.md)
[![CI](https://github.com/Coke1120/codex-pet-dev-board/actions/workflows/ci.yml/badge.svg)](https://github.com/Coke1120/codex-pet-dev-board/actions/workflows/ci.yml)

Codex Pet turns the **GUITION JC4880P443C-I-W** into a 480×800 touch desk
companion for Codex on macOS. The ESP32-P4 drives the display, touch UI, and
USB Serial protocol. Its onboard ESP32-C6 provides Wi-Fi and Bluetooth Low
Energy over ESP-Hosted SDIO.

The pet remains the primary interface. It reflects the current Codex lifecycle
state, reacts to touch, and exposes Today, Settings, and Codex quota as
gesture-driven information layers. The private Codex Pet v2 source atlas stays
local and is converted into a gitignored firmware asset before building.

This repository maintains one product configuration:

| Part | Supported configuration |
|---|---|
| Hardware | GUITION JC4880P443C-I-W with ESP32-P4, ESP32-C6, 480×800 ST7701S display, and GT911 touch |
| Host | macOS with Python 3 and launchd |
| Firmware | ESP-IDF 5.5.1 (sole maintained MCU framework) with LVGL 9, the board BSP, and ESP-Hosted as ESP-IDF components |

Ubuntu runners are firmware-build infrastructure only; desktop host support
remains macOS-only. Generic Python or ESP-IDF code that happens to run elsewhere
is an implementation detail, not a compatibility commitment.
Arduino is unsupported and inactive; there is no maintained Arduino build,
flash, library, or compatibility path in this repository.

## Enabled features

- Four Codex lifecycle states: `idle`, `running`, `waiting`, and `review`
- Complete 73-frame Codex Pet v2 action and look-direction contract
- Priority-aware wave, jump, failure, waiting, running, review, and touch reactions
- Thin time/weather bar and pull-down Today panel with clock and weather icons
- Hong Kong weather, high/low temperature, rain probability, and stale-data handling
- Swipe-left Settings page for Wi-Fi and BLE controls
- Swipe-up Codex quota page synchronized through CodexBar
- Optional Wi-Fi station scan/connect/forget through the onboard ESP32-C6
- Optional non-connectable `Codex Pet` BLE advertising (BLE only; no Classic Bluetooth or application GATT service)
- USB Serial lifecycle, clock, weather, quota, and legacy usage synchronization
- Persistent macOS LaunchAgent with official Codex lifecycle hooks
- Local-only generated pet artwork excluded from Git

## Board capabilities not enabled by this repository

The JC4880P443C-I-W hardware and its vendor package expose more peripherals than
the Codex Pet application initializes. The vendored BSP snapshot is retained for
provenance and reference; it is not selected by the active CMake build. In this
table, **available** means the board or BSP provides the path, not that Codex Pet
installs, initializes, tests, or uses it.

| Board capability | Supplied hardware or BSP path | Codex Pet status |
|---|---|---|
| Front camera | MIPI-CSI camera path; the vendor package includes OV02C10 sensor material | Disabled: no camera driver or pipeline, capture, storage, stream, or network upload |
| Microphone | Onboard microphone through the ES8311 ADC and I2S input | Disabled: no codec initialization, audio capture, or recording |
| Speaker output | ES8311 DAC, NS4150 amplifier, and MX1.25 two-pin speaker connector | Disabled: no audio playback; the bare `I-W` board does not guarantee that a speaker unit is fitted |
| microSD / TF card | Card slot and BSP mount APIs | Disabled: the application does not mount, read, or write a card |
| High-speed USB / USB Host | Secondary USB path and BSP host APIs | Disabled: no HID, storage, audio, video, or network class; the maintained host link is USB Serial/JTAG |
| Lithium battery path | Battery connector and charger/power circuit | Hardware-only: no battery percentage, charge-state, sleep, or power-management UI |
| RS-485 and expansion I/O | RS-485, UART, I2C, and GPIO connectors | Unassigned: no Codex Pet protocol, driver setup, or UI controls |

Wi-Fi and BLE support is deliberately narrow and build-time opt-in. Wi-Fi provides
station enable, scan, connect, and forget controls, but Mac synchronization still
uses USB Serial. BLE starts disabled; enabling it initializes the P4 NimBLE host
and C6 controller and advertises `Codex Pet`, while disabling it tears both
layers down without releasing the memory needed for a later restart. The
potentially blocking NimBLE stop is supervised by a dedicated task, so Settings
returns an error after five seconds instead of blocking Wi-Fi; Retry joins the
same in-flight stop rather than starting a second teardown. There is
no BLE provisioning flow or custom application GATT service. Camera and
microphone inactivity are privacy boundaries: the current application never
reads either sensor.

## Interaction model

| Gesture | Result |
|---|---|
| Drag down from the top edge | Open Today; the pet moves below the card and looks up |
| Swipe left | Open Settings |
| Swipe up | Open Codex Quota |
| Tap the pet | Play a cooldown-limited random reaction, then return to the current lifecycle state |
| Tap the status card | Cycle lifecycle states for hardware testing |

Today closes with an upward swipe. Settings closes with a right swipe or Back.
Quota closes with a downward swipe or Back.

## Architecture

```text
Codex hooks ──▶ mac/codex_pet_hook.py ─┐
CodexBar quota ─────────────────────────┼─▶ codex_pet_daemon.py ──USB Serial──▶ ESP32-P4
Legacy local token aggregates ──────────┘                                      │
                                                                               ├─▶ LVGL UI + v2 pet actions
Open-Meteo weather ─────────────────────────────────────────────────────────────┤
                                                                               └─SDIO──▶ ESP32-C6 Wi-Fi/BLE
```

The Mac sends compact data only. The device advances its own clock between
minute syncs, keeps the last weather/quota values when refreshes fail, and marks
old data as stale instead of blanking the UI.

## Repository layout

```text
esp32-p4/                         ESP-IDF firmware and locked managed components
mac/codex_pet_bridge.py           Manual macOS USB Serial bridge
mac/codex_pet_hook.py             Codex lifecycle hook event mapper
mac/codex_pet_daemon.py           Persistent lifecycle/data synchronization daemon
mac/codex_pet_usage.py            CodexBar quota adapter and legacy aggregate reader
mac/install.sh                    macOS runtime and LaunchAgent installer
tools/convert_codex_pet_p4.py     Codex Pet v2 atlas converter
tools/install_codex_hooks.py      Non-destructive Codex hook merger
examples/codex-hooks.json         Codex lifecycle hook configuration example
tests/                            Host, protocol, converter, and interaction tests
docs/ESP32_P4.md                  Build, flash, protocol, and hardware acceptance guide
docs/CODEX_DESKTOP.md             macOS Codex synchronization guide
vendor/jc4880p443c_i_w_bsp/       Licensed vendor BSP provenance snapshot
```

## Requirements

- macOS
- GUITION JC4880P443C-I-W and suitable USB cables
- ESP-IDF 5.5.1
- CodexBar with a working Codex login for account quota display
- Python 3
- `ffmpeg` when converting a selected Codex Pet v2 atlas

The P4 and C6 are separate flash targets. Confirm the detected chip before
writing either image. See [the hardware guide](docs/ESP32_P4.md) for port
identification and the physical acceptance checklist.

## 1. Generate the selected Codex Pet v2 asset

The public build uses a small test tile so the repository can build without
redistributing character art. To mirror a compatible pet selected in Codex
Desktop, generate the private RGB565A8 asset locally:

```bash
python3 tools/convert_codex_pet_p4.py \
  --spritesheet "$HOME/.codex/pets/<pet-folder>/spritesheet.webp" \
  --output esp32-p4/main/pet_generated.c
```

The converter uses all 73 referenced cells in the v2 8×11 atlas: nine animation
rows and 16 clockwise look directions. `pet_generated.c` is gitignored. Do not
commit or publish it unless you own or have explicit permission to redistribute
the source artwork. Delete the generated file to restore the public test asset.

## 2. Build and flash the ESP32-P4

Open an ESP-IDF 5.5.1 shell and create a clean, isolated display-safe build.
Never flash a repo-local `esp32-p4/build/` directory or effective
`esp32-p4/sdkconfig`; either can contain stale settings from another variant.

```bash
cd esp32-p4
P4_SAFE_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/codex-pet-p4-safe.XXXXXX")"
idf.py -B "$P4_SAFE_ROOT/build" \
  -D "SDKCONFIG=$P4_SAFE_ROOT/sdkconfig" \
  -D "SDKCONFIG_DEFAULTS=$PWD/sdkconfig.defaults" \
  set-target esp32p4
grep -q '^CONFIG_ESP_MAIN_TASK_STACK_SIZE=7680$' "$P4_SAFE_ROOT/sdkconfig"
grep -q '^# CONFIG_CODEX_PET_C6_WIRELESS is not set$' "$P4_SAFE_ROOT/sdkconfig"
idf.py -B "$P4_SAFE_ROOT/build" build
test -n "$(find "$P4_SAFE_ROOT/build" -name '*.su' -print -quit)"
find "$P4_SAFE_ROOT/build" -name '*.su' -print
```

The build is rejected if any Codex Pet component stack frame exceeds 768 bytes;
the emitted `.su` files are required stack-usage evidence, not optional debug
output. Keep the isolated effective `sdkconfig`, binaries, ELF/map files, and
`.su` reports together as one variant. Before and after flashing, independently
read back/verify the exact bootloader, partition table, and application binaries
described in [the hardware guide](docs/ESP32_P4.md).

Only after those gates pass, flash from that same isolated build:

```bash
idf.py -B "$P4_SAFE_ROOT/build" \
  -p /dev/cu.<verified-p4-port> flash monitor
```

Exit the monitor with `Ctrl+]`. Expected boot output includes:

```text
Codex Pet ESP32-P4 ready
Display/serial: ready
Board: JC4880P443C-I-W
Protocol: v2 lifecycle clock weather today-v1 usage-v1 quota-v1 codexbar-v1 wireless settings-v1
Wireless: disabled at build time
```

## 3. Build and flash the ESP32-C6 wireless slave

Wireless P4 and matching C6 images are a separate candidate from the
display-safe baseline. Build them in their own isolated directories only after
the safe P4 has passed its display, Serial, stack, and read-back gates. Do not
flash the C6 during display recovery or unless C6 work is explicitly in scope.
The hardware guide contains the exact variant commands and acceptance gates.

Run the isolated P4 build first so ESP-IDF resolves the exact ESP-Hosted version
locked by the project. Then build the matching C6 image:

```bash
cd esp32-p4/managed_components/espressif__esp_hosted/slave
C6_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/codex-pet-c6.XXXXXX")"
idf.py -B "$C6_ROOT/build" -D "SDKCONFIG=$C6_ROOT/sdkconfig" set-target esp32c6
grep -q '^CONFIG_IDF_TARGET_ESP32C6=y$' "$C6_ROOT/sdkconfig"
idf.py -B "$C6_ROOT/build" build
idf.py -B "$C6_ROOT/build" -p /dev/cu.<verified-c6-port> flash monitor
```

Verify the chip identity and port before flashing. Mixing host and slave images
from different ESP-Hosted releases is unsupported. Only after the matching C6
image is verified should `Codex Pet → Start the ESP32-C6 wireless backend` be
enabled in P4 `menuconfig` and the P4 rebuilt and physically tested. The default
P4 build keeps this option off so an unverified C6 cannot regress display bring-up.

## 4. Install the macOS host runtime

From the repository root:

```bash
bash mac/install.sh
```

The installer maintains an isolated runtime under
`~/Library/Application Support/CodexPet/runtime` and loads the
`com.coke1120.codex-pet` per-user LaunchAgent. Configure the supplied lifecycle
hooks separately, merging them without replacing unrelated hooks, as described
in the desktop guide. Rerun the installer after updating the repository. Each
update is prepared in a sibling staged venv/runtime; the live runtime, plist,
and previously loaded jobs are restored together if unload, replacement,
cleanup, or bootstrap fails. Unsafe broad, symlink, and non-directory runtime
targets are rejected before filesystem mutation.

When automatic port selection is ambiguous, install with the verified P4 port:

```bash
bash mac/install.sh --port /dev/cu.<verified-p4-port>
```

See [Direct Codex Desktop and CLI synchronization](docs/CODEX_DESKTOP.md) for
hook review, verification, logs, usage-data boundaries, and removal.

## Manual bridge

The manual bridge is useful for protocol and animation checks:

```bash
cd mac
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
.venv/bin/python codex_pet_bridge.py --list
.venv/bin/python codex_pet_bridge.py \
  --port /dev/cu.<verified-p4-port> \
  --interactive
```

The supported lifecycle commands and responses are:

```text
ping       -> pong
idle       -> OK IDLE
running    -> OK RUNNING
waiting    -> OK WAITING
review     -> OK REVIEW
status     -> STATE <CURRENT_STATE>
```

Keep one bridge or daemon process attached to the port. Two processes cannot
safely own the same Serial device.

## Development verification

Run the host tests and syntax checks on macOS:

```bash
python3 -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/codex-pet-pycache \
  python3 -m py_compile mac/*.py tools/*.py tests/*.py
```

Build the P4 firmware in an ESP-IDF 5.5.1 shell using the isolated display-safe
or wireless commands above. Development verification has the same effective-
sdkconfig, 7,680-byte main-stack, fatal 768-byte frame, and `.su` evidence gates
as a release candidate.

GitHub Actions uses macOS for supported host checks and Ubuntu only as firmware
build infrastructure. CI compile success does not replace the physical display,
touch, P4/C6 radio, Serial, and camera-inactivity checks in
[`docs/ESP32_P4.md`](docs/ESP32_P4.md).

## Privacy and redistribution

- The lifecycle hook stores only a hashed session key, mapped state, event name,
  and timestamp. It does not store prompts or transcript content.
- CodexBar performs Codex authentication and quota retrieval. The daemon sends
  only remaining percentages, reset epochs, credit balance, and update epoch to
  the P4; it never sends the CodexBar account identity.
- The legacy reader accepts only local `token_count` events for compatibility
  with older P4 firmware; those aggregates are not account quota data.
- Wi-Fi passwords are cleared from the UI after submission and are not included
  in UI status snapshots or logs. Station credentials use ESP-IDF RAM-only
  storage, are lost on reboot, and require the user to reconnect; they are not
  persisted to flash by this application.
- The camera and microphone are not initialized; the application contains no
  image capture, audio recording, media storage, or media-upload path.
- Custom pet artwork remains local and must not be published without explicit
  redistribution rights.
- Review [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) before distributing
  firmware binaries.

## Vendor BSP provenance

The repository preserves the redistributable, model-specific source subset from
the supplied JC4880P443C-I-W package under
[`vendor/jc4880p443c_i_w_bsp/`](vendor/jc4880p443c_i_w_bsp/), with archive hashes
and license records. This snapshot is provenance material; the active build uses
the commit-pinned community BSP recorded in `esp32-p4/dependencies.lock`.

The original resource archive also contains utilities for other operating
systems and unrelated packages. Those archived contents do not expand this
project's macOS-only host support policy.

## Current verification boundary

The board/display path has previously been built, flashed, and hash-verified on an
ESP32-P4 revision v1.3 unit. The full v2 asset has also linked successfully.
The current hardening changes add isolated variant builds, a 7,680-byte main
task stack floor, a fatal 768-byte frame gate, `.su` evidence, stricter Serial
identity/exclusive ownership, RAM-only Wi-Fi credentials, and non-connectable
BLE advertising. These current changes are software-evidenced only here; their
exact artifacts still require read-back, boot-resource, protocol, and physical
acceptance. P4/C6 SDIO, Wi-Fi reconnection after reboot, repeated BLE
enable/disable and advertising, updated Serial exchange, and continuous
display/touch stability require the complete physical checklist in
[`docs/ESP32_P4.md`](docs/ESP32_P4.md).

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request. Report
security vulnerabilities privately according to [`SECURITY.md`](SECURITY.md).

## License

Project-authored code and documentation are available under the [MIT License](LICENSE).
Third-party components and generated artwork retain their own terms.
