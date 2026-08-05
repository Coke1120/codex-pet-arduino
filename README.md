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
- CodexBar is optional and required only for account quota display
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

An authorized MMD/PMX model can instead be posed and rendered offline into the
same private frame transport. See the [MMD / PMX pet pipeline](docs/MMD_PET.md)
for isolated Blender setup, the default mask-off model-like contrapposto,
status-authored motion, and slide-driven four-direction gaze.

An authorized video source can also be edited and matted offline into dynamic
status clips. See the [private video pet pipeline](docs/VIDEO_PET.md) for the
frame manifest, compressed asset build, and evidence gates.

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

Some ESP32-P4 USB Serial/JTAG consoles expose only the generic Espressif
`303A:1001` descriptor in normal operation. Do not accept that descriptor or
VID/PID by itself. After `esptool --chip esp32p4 chip_id` has proved the P4 in
Download Mode, match its MAC to the exact USB serial reported for connector #4,
then enroll that already-attested identity explicitly:

```bash
bash mac/install.sh \
  --port /dev/cu.<verified-p4-port> \
  --p4-usb-serial <chip-id-matched-usb-serial>
```

The pin is conjunctive with the explicit path, is revalidated on every daemon
reconnect, and never changes automatic selection or flash authorization. An
unpinned generic descriptor remains rejected.

### Moving the board to another Mac

The flashed P4 display and touch UI remain on the board, but lifecycle, clock,
weather, and quota are host-fed features. They do not become live on another
Mac merely by reconnecting USB. Repeat the host setup on every Mac:

1. Clone or copy this repository and ensure Python 3 is available. Install and
   sign in to CodexBar only when Codex quota is required; Hong Kong weather does
   not depend on CodexBar.
2. Connect the P4 application console through connector #4 and rediscover its
   `/dev/cu.*` path. Device paths are local to each Mac and may also change when
   the USB topology changes, so do not copy the old Mac's path blindly. For an
   already-attested generic console, reuse the same P4 USB serial pin with the
   newly discovered path.
3. Run the appropriate `mac/install.sh` command above. This installs the
   isolated runtime and per-user LaunchAgent on that Mac; it intentionally does
   not modify or trust Codex hooks automatically.
4. Merge the installed lifecycle hook into that Mac's Codex configuration:

   ```bash
   python3 tools/install_codex_hooks.py \
     --hooks "$HOME/.codex/hooks.json" \
     --python "$HOME/Library/Application Support/CodexPet/runtime/bin/python" \
     --hook-script "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_hook.py"
   ```

   The merger is deliberately additive and preserves unrelated hooks. If this
   Mac already has older Codex Pet commands that point into a repository path,
   inspect `~/.codex/hooks.json` and remove only those obsolete Codex Pet groups;
   a different existing command is not silently replaced.

5. Restart Codex, open `/hooks`, inspect the exact Application Support command,
   and trust it only after it matches the installed runtime. Hook trust remains
   user-controlled on each Mac.

Verify the new host independently:

```bash
launchctl print "gui/$(id -u)/com.coke1120.codex-pet"
tail -n 50 "$HOME/Library/Application Support/CodexPet/daemon.out.log"
tail -n 50 "$HOME/Library/Application Support/CodexPet/daemon.err.log"
```

`idle` is the correct state when no Codex turn is active. A submitted prompt
should produce `running`; tests or review work can produce `review`; a real
permission request produces `waiting`; and turn completion returns to `idle`.
If the display remains `idle` throughout an active turn, first verify that the
installed hooks were merged, reviewed, trusted, and are writing recent session
records under `~/Library/Application Support/CodexPet/sessions/`.

Weather values are real Hong Kong current conditions and forecasts fetched from
Open-Meteo for `22.3193, 114.1694` in the `Asia/Hong_Kong` timezone every
15 minutes. They are not demo constants or measurements from an onboard sensor,
and require no CodexBar account. A failed refresh intentionally preserves the
last good per-Mac cache, so check its `updated_epoch` and `daemon.err.log` before
calling a displayed value current. After a cold board boot, the UI shows
`Waiting for weather sync` until a host sends a snapshot; it marks data aging
after 45 minutes and unavailable after three hours.

### Copy-paste setup prompt for Codex on a new Mac

Replace the three input values before pasting this prompt into a Codex task on
the new Mac. Keep the board-specific USB serial private to your local setup; do
not commit it to this repository.

```text
Set up my already-flashed GUITION JC4880P443C-I-W Codex Pet on this Mac and
verify the macOS host synchronization end to end.

Inputs:
- Repository: <ABSOLUTE_PATH_TO_CODEX_PET_DEV_BOARD>
- Previously attested P4 USB serial: <12_HEX_SERIAL_OR_UNKNOWN>
- CodexBar quota setup and live OAuth refresh authorized: <YES_OR_NO>

Work autonomously through every safe, reversible step. Preserve existing
worktree changes and unrelated Codex hooks. Do not commit or push unless I ask.

Non-negotiable safety boundaries:
- The P4 firmware is already installed. Do not build, erase, flash, or change
  firmware, and do not put either chip into Download Mode.
- Do not access or flash the ESP32-C6.
- Use connector #4 as the P4 application USB Serial/JTAG console. Never guess a
  CH340, C6, or generic Espressif device from VID/PID alone.
- Ordinary selection requires exact ESP32-P4 or JC4880P443C metadata. A generic
  303A:1001 console is allowed only when its one unique complete USB serial
  exactly matches the previously attested P4 serial and an explicit /dev/cu.*
  path. If that proof is unavailable or ambiguous, stop before installation and
  report the missing evidence.
- Keep exactly one exclusive Serial owner. Stop an existing daemon, bridge, or
  monitor before a direct protocol test; do not open a second monitor while the
  LaunchAgent owns the port.
- Never expose CodexBar raw JSON, email, account identity, or OAuth material.
  Never put prompts, transcripts, tool output, or working directories into hook
  records, daemon logs, caches, or Serial payloads.

Execution and verification:
1. Work from the repository input. Read README.md, docs/CODEX_DESKTOP.md, and
   .agents/skills/codex-pet-host-sync/SKILL.md plus its runbook. Record git
   status and source revision without discarding local changes.
2. Prepare the repository macOS Python venv if needed using the hash-locked
   mac/requirements.txt, then inspect serial ports with pyserial verbose output.
   Rediscover the new Mac's /dev/cu.* path; never copy a path from another Mac.
3. Establish the P4 identity using the strict rules above, check lsof for an
   existing owner, then use one temporary pyserial process with one exclusive
   Serial handle. Create the probe under /tmp but invoke it with
   <ABSOLUTE_PATH_TO_CODEX_PET_DEV_BOARD>/mac/.venv/bin/python. Prepend the
   repository's mac directory to sys.path and import select_p4_port from
   codex_pet_device plus list_ports from serial.tools. Open the verified port at
   115200 with timeout=0.25, write_timeout=1.0, and exclusive=True, then
   immediately re-enumerate ports and require
   select_p4_port(list_ports.comports(), verified_port, pinned_serial_or_none)
   to return that same explicit port before any write. On mismatch, close with
   zero writes. After successful revalidation, wait 2.1 seconds for the reset,
   clear input, then send the newline-terminated raw ASCII commands ping, status,
   and capabilities in that same session. Use a bounded response loop of at most
   two seconds per command and require exact pong, STATE <CURRENT_STATE>, and
   CAPABILITIES 2 ... replies before installing launchd, then remove the
   temporary probe. Do not use codex_pet_bridge.py interactive mode for these
   raw commands; it accepts lifecycle states only. Keep provider retrieval,
   Serial ACKs, and physical rendering as separate evidence.
4. Install the transactional Application Support runtime and LaunchAgent with
   bash mac/install.sh --port <VERIFIED_PORT>. If and only if the connector is
   the already-attested generic console, also pass
   --p4-usb-serial <ATTESTED_SERIAL>. Never add an allow-generic bypass.
5. Before changing hooks, inspect ~/.codex/hooks.json and create a timestamped
   backup when it exists. Then merge hooks without replacing unrelated entries:
   python3 tools/install_codex_hooks.py \
     --hooks "$HOME/.codex/hooks.json" \
     --python "$HOME/Library/Application Support/CodexPet/runtime/bin/python" \
     --hook-script "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_hook.py"
   The merger is additive. After verifying the new group, remove only exact
   obsolete Codex Pet repository-path groups, never unrelated hooks.
6. Verify source/runtime SHA-256 equality, one running
   com.coke1120.codex-pet LaunchAgent, one exclusive owner of the intended port,
   the pinned port/serial tuple when used, negotiated clock/quota/usage/weather
   capabilities, private 0700 session directories, private 0600 records/caches,
   and no new serial or identity error after a successful connection. Classify
   optional provider warnings separately.
7. Verify live Hong Kong Open-Meteo retrieval independently from Serial delivery.
   Before starting or restarting the daemon, record whether
   "$HOME/Library/Application Support/CodexPet/weather-cache.json" exists, its
   mtime, and the byte size of daemon.err.log beside the runtime. Require the
   cache to be created or its mtime to advance during this run, require no new
   weather warning in the appended stderr segment, and require the numeric age
   to satisfy 0 <= current_epoch - updated_epoch <= 1800. The sanitized cache
   may contain only current, low, high, rain_pct, condition, and updated_epoch;
   report those values. A future timestamp or merely recent retained cache is
   not a successful current fetch.
8. Discover the supported CodexBar executable without reading account data:
   check CODEXBAR_CLI when set, command -v codexbar, /opt/homebrew/bin/codexbar,
   /usr/local/bin/codexbar,
   /Applications/CodexBar.app/Contents/Helpers/CodexBarCLI, and
   $HOME/Applications/CodexBar.app/Contents/Helpers/CodexBarCLI, then run the
   discovered executable with --version. Only when the input says YES, install
   CodexBar from its official project if none is found, pause for me to complete
   any interactive sign-in, then perform the live OAuth refresh. Keep raw output
   private and report only the six sanitized numeric quota fields. When the
   input says NO, leave quota unverified/unavailable and continue with lifecycle,
   clock, and weather.
9. After all automatic setup is complete, give me one explicit checkpoint to
   restart Codex, open /hooks, inspect the exact Application Support command,
   and trust it. Do not claim lifecycle completion until I resume this task.
10. After resume, prove real transitions: no active turn -> idle, submitted
    prompt -> running, test/review work -> review, a real permission request ->
    waiting when supported, and turn completion -> idle. If host logs change but
    the panel does not, report the Serial/UI layer separately instead of
    reflashing.
11. Ask me to confirm the visible time, weather, icons, quota, and lifecycle on
    the panel. Finish with a PASS/FAIL/UNPROVEN table for firmware protocol,
    provider retrieval, Serial delivery, hooks, LaunchAgent, and physical UI,
    including exact remaining blockers and no unsupported success claims.
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
  --p4-usb-serial <chip-id-matched-usb-serial> \
  --interactive
```

Omit `--p4-usb-serial` when current USB metadata already names `ESP32-P4` or
`JC4880P443C`. Never derive or auto-enroll a pin from the first attached
Espressif device.

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
