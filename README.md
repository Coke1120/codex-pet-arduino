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
state, reacts to touch, and exposes Today, Settings, and local Codex Usage as
gesture-driven information layers. The private Codex Pet v2 source atlas stays
local and is converted into a gitignored firmware asset before building.

This repository maintains one product configuration:

| Part | Supported configuration |
|---|---|
| Hardware | GUITION JC4880P443C-I-W with ESP32-P4, ESP32-C6, 480×800 ST7701S display, and GT911 touch |
| Host | macOS with Python 3 and launchd |
| Firmware | ESP-IDF 5.5.1 and LVGL 9 |

Ubuntu runners are firmware-build infrastructure only; desktop host support
remains macOS-only. Generic Python or ESP-IDF code that happens to run elsewhere
is an implementation detail, not a compatibility commitment.

## Features

- Four Codex lifecycle states: `idle`, `running`, `waiting`, and `review`
- Complete 73-frame Codex Pet v2 action and look-direction contract
- Priority-aware wave, jump, failure, waiting, running, review, and touch reactions
- Thin time/weather bar and pull-down Today panel
- Hong Kong weather, high/low temperature, rain probability, and stale-data handling
- Swipe-left Settings page for Wi-Fi and BLE controls
- Swipe-up Codex Usage page for privacy-limited local token aggregates
- Wi-Fi station scan/connect/forget through the onboard ESP32-C6
- BLE advertising as `Codex Pet` (BLE only; Classic Bluetooth is not supported)
- USB Serial lifecycle, clock, weather, and usage synchronization
- Persistent macOS LaunchAgent with official Codex lifecycle hooks
- Local-only generated pet artwork excluded from Git

## Interaction model

| Gesture | Result |
|---|---|
| Drag down from the top edge | Open Today; the pet moves below the card and looks up |
| Swipe left | Open Settings |
| Swipe up | Open Codex Usage |
| Tap the pet | Play a cooldown-limited random reaction, then return to the current lifecycle state |
| Tap the status card | Cycle lifecycle states for hardware testing |

Today closes with an upward swipe. Settings closes with a right swipe or Back.
Usage closes with a downward swipe or Back.

## Architecture

```text
Codex hooks ──▶ mac/codex_pet_hook.py ─┐
                                        ├─▶ codex_pet_daemon.py ──USB Serial──▶ ESP32-P4
Local session token_count events ───────┘                                      │
                                                                               ├─▶ LVGL UI + v2 pet actions
Open-Meteo weather ─────────────────────────────────────────────────────────────┤
                                                                               └─SDIO──▶ ESP32-C6 Wi-Fi/BLE
```

The Mac sends compact data only. The device advances its own clock between
minute syncs, keeps the last weather/usage values when refreshes fail, and marks
old data as stale instead of blanking the UI.

## Repository layout

```text
esp32-p4/                         ESP-IDF firmware and locked managed components
mac/codex_pet_bridge.py           Manual macOS USB Serial bridge
mac/codex_pet_hook.py             Codex lifecycle hook event mapper
mac/codex_pet_daemon.py           Persistent lifecycle/data synchronization daemon
mac/codex_pet_usage.py            Local token-count aggregate reader
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

Open an ESP-IDF 5.5.1 shell:

```bash
cd esp32-p4
idf.py set-target esp32p4
idf.py build
idf.py -p /dev/cu.<verified-p4-port> flash monitor
```

Exit the monitor with `Ctrl+]`. Expected boot output includes:

```text
Codex Pet ESP32-P4 ready
Board: JC4880P443C-I-W
Protocol: v2 lifecycle clock weather today-v1 usage-v1 wireless settings-v1
```

## 3. Build and flash the ESP32-C6 wireless slave

Run the P4 build first so ESP-IDF resolves the exact ESP-Hosted version locked
by the project. Then build the matching C6 image:

```bash
cd esp32-p4/managed_components/espressif__esp_hosted/slave
idf.py set-target esp32c6
idf.py build
idf.py -p /dev/cu.<verified-c6-port> flash monitor
```

Verify the chip identity and port before flashing. Mixing host and slave images
from different ESP-Hosted releases is unsupported.

## 4. Install the macOS host runtime

From the repository root:

```bash
bash mac/install.sh
```

The installer maintains an isolated runtime under
`~/Library/Application Support/CodexPet/runtime` and loads the
`com.coke1120.codex-pet` per-user LaunchAgent. Configure the supplied lifecycle
hooks separately, merging them without replacing unrelated hooks, as described
in the desktop guide. Rerun the installer after updating the repository.

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
.venv/bin/python -m pip install -r requirements.txt
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

Build the P4 firmware in an ESP-IDF 5.5.1 shell:

```bash
cd esp32-p4
idf.py set-target esp32p4
idf.py build
```

GitHub Actions uses macOS for supported host checks and Ubuntu only as firmware
build infrastructure. CI compile success does not replace the physical display,
touch, P4/C6 radio, Serial, and camera-inactivity checks in
[`docs/ESP32_P4.md`](docs/ESP32_P4.md).

## Privacy and redistribution

- The lifecycle hook stores only a hashed session key, mapped state, event name,
  and timestamp. It does not store prompts or transcript content.
- Codex Usage reads only local `token_count` events and sends aggregate integers.
  It is not an account quota or billing report.
- Wi-Fi passwords are cleared from the UI after submission and are not included
  in UI status snapshots or logs.
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

The board/display path has been built, flashed, and hash-verified on an
ESP32-P4 revision v1.3 unit. The full v2 asset has also linked successfully.
Settings, Codex Usage, P4/C6 SDIO, Wi-Fi, BLE advertising, updated Serial
exchange, and continuous display/touch stability still require the complete
physical checklist in [`docs/ESP32_P4.md`](docs/ESP32_P4.md).

## Contributing and security

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request. Report
security vulnerabilities privately according to [`SECURITY.md`](SECURITY.md).

## License

Project-authored code and documentation are available under the [MIT License](LICENSE).
Third-party components and generated artwork retain their own terms.
