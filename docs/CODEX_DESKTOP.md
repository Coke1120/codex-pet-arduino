# Direct Codex Desktop and CLI synchronization

The Python hook and Serial daemon connect Codex on macOS to the
JC4880P443C-I-W over USB Serial. The ESP32-P4 negotiates lifecycle, clock, Hong
Kong weather, and CodexBar quota synchronization before the daemon starts
optional data workers.

The basic `codex_pet_bridge.py` is intentionally manual: it sends only the state supplied through `--state`, `--interactive`, or `--stdin`. It does not inspect Codex Desktop automatically.

For direct reflection, this repository uses the official Codex lifecycle hooks documented at <https://developers.openai.com/codex/hooks>:

```text
Codex lifecycle event ──▶ codex_pet_hook.py ──▶ lifecycle state ─┐
CodexBar OAuth CLI ──▶ codex_pet_usage.py ──▶ numeric quota ─────┼─▶ daemon ──▶ USB Serial ──▶ Pet
legacy ~/.codex/sessions ──▶ local token aggregates ─────────────┘
```

## State mapping

| Codex event | Pet state |
|---|---|
| Session start | `idle` |
| User prompt, ordinary tool use, subagent activity | `running` |
| Review/test/lint/typecheck tool command or compaction | `review` |
| Permission request | `waiting` |
| Turn stop or session end | `idle` |

When multiple Codex conversations are active, priority is `waiting` → `review` → `running` → `idle`. Session records expire after 15 minutes by default so a crashed Codex process cannot leave the pet permanently busy.

`RUNNING` or `REVIEW` is expected while Codex is processing the current turn;
the same session writes `idle` when its `Stop` hook fires. A manual status-card
tap is only a hardware test and will be replaced by the daemon's next five-second
heartbeat. If a process exits without `Stop`, its last busy state can remain
visible until the 15-minute active TTL expires.

The hook stores only a hashed session key, mapped state, allow-listed event name,
and timestamp under:

```text
~/Library/Application Support/CodexPet/sessions/
```

It does **not** store prompts, assistant messages, tool output, transcript paths,
working-directory paths, Wi-Fi credentials, or account identity. The session
directory is mode `0700` and records are mode `0600`; malformed or foreign JSON
is not accepted as lifecycle state.

## Codex quota data

For a P4 that advertises `quota`, the daemon runs CodexBar's supported machine
interface:

```text
codexbar --provider codex --source oauth --format json --json-only
```

CodexBar owns authentication and provider access. The adapter converts its
five-hour and weekly used percentages to remaining percentages, then sends only
six numeric fields: both remaining percentages and reset epochs, credits in
tenths, and the update epoch. Missing windows use `-1` and a zero reset epoch.
Account identity, email, prompts, transcripts, and tool output never enter the
Serial command or numeric cache. Refreshes are minute-gated and preserve the
last good cache at
`~/Library/Application Support/CodexPet/codexbar-quota-cache.json`.

The legacy `usage` capability remains for older firmware. Only when `quota` is
absent does the daemon read local `~/.codex/sessions` `token_count` events and
send aggregate integers. `--sessions-root` applies only to that fallback. Those
local aggregates are not subscription quota or billing data.

## 1. Install Python; optionally install CodexBar for quota

CodexBar is optional and required only for account quota display. Lifecycle,
clock, and weather synchronization do not depend on it. To enable quota,
install and sign in to [CodexBar](https://github.com/steipete/CodexBar). The
daemon accepts either the `codexbar` executable on `PATH` or the helper bundled
inside `CodexBar.app`. Confirm its Codex provider works before starting the
daemon:

```bash
codexbar --provider codex --source oauth --format json --json-only
```

Treat that terminal output as private because CodexBar may include account
identity fields; Codex Pet filters them before caching or sending data.

```bash
cd /path/to/codex-pet-dev-board/mac
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements.txt
```

## 2. Test the daemon before changing Codex

```bash
.venv/bin/python codex_pet_daemon.py --dry-run --once
```

With no recent hook event, it prints:

```text
idle
```

Run the persistent bridge manually:

```bash
.venv/bin/python codex_pet_daemon.py --port auto
```

If more than one plausible Espressif device is attached, compare the macOS port
list before and after reconnecting the P4 native USB connector, confirm the chip,
then pass its exact `/dev/cu.*` path using `--port`. Both automatic and explicit
selection require current USB metadata that identifies the P4 by its exact
`ESP32-P4` or `JC4880P443C` descriptor; C6 devices, generic Espressif VID
`303A` `USB JTAG/serial debug unit` descriptors, and unidentified CH340 adapters
are rejected by the ordinary selector. There is no VID/PID-only or
`--allow-generic` bypass.

If connector #4 exposes only that generic descriptor, establish a separate
pinned identity before running the daemon:

1. On connector #5 in Download Mode, run `esptool --chip esp32p4 chip_id` and
   record the P4 MAC.
2. Move to connector #4 and inspect `python -m serial.tools.list_ports --verbose`.
3. Require the exact USB serial to equal the chip-ID MAC after canonicalization.
4. Use both the explicit path and that serial:

```bash
.venv/bin/python codex_pet_daemon.py \
  --port /dev/cu.<verified-p4-port> \
  --p4-usb-serial <chip-id-matched-usb-serial>
```

Pinned selection remains fail-closed: `/dev/cu.*`, VID:PID `303A:1001`, exact
Espressif metadata, one unique serial match, no C6 identity, an unchanged
post-open identity, and the exact P4 `ping`/capability handshake are all
required. The pin prevents accidental device confusion; USB metadata and the
plaintext protocol are not cryptographic authentication. It is never accepted
by `auto`, never auto-enrolled, and never authorizes flashing.
Stop the LaunchAgent and every bridge/monitor first, verify `lsof "$PORT"` is
clear, and keep exactly one serial owner for each test.
The daemon re-sends the selected state every five seconds by default so a board
reset cannot silently desynchronize the display. Use `--heartbeat SECONDS` to
choose another positive interval. On a P4 that advertises `clock`, `weather`,
and `quota`, it also sends local time once per minute, fetches Hong Kong weather
in a background thread every 15 minutes, and refreshes CodexBar quota at most
once per minute. Each worker starts only after capability negotiation and never
during `--dry-run`. Use `--no-weather` to disable weather retrieval or
`--no-usage` to disable both CodexBar quota and legacy local usage sync. Use
`--sessions-root PATH` only when an older P4 lacks `quota` and Codex stores its
session JSONL somewhere other than `~/.codex/sessions`:

```bash
.venv/bin/python codex_pet_daemon.py \
  --port /dev/cu.<verified-p4-port> \
  --p4-usb-serial <chip-id-matched-usb-serial> \
  --sessions-root /path/to/codex/sessions
```

Omit `--p4-usb-serial` when the descriptor already names the P4. A configured
pin and port are one identity tuple; both must still match after every reset or
reconnect before lifecycle, clock, weather, usage, or quota data is written.

An incomplete capability response is retried instead of silently downgrading the
v2 board. Weather, quota, and legacy usage
failures retain their last good caches and are reported once per distinct error
until a successful refresh.

## 3. Install or update the launchd runtime

macOS may deny background LaunchAgents access to source code kept under
`Documents`. The installer maintains a small runtime copy under
`~/Library/Application Support/CodexPet/runtime`, installs its isolated Python
environment, copies the usage reader with the daemon, and loads
`com.coke1120.codex-pet` as a per-user LaunchAgent:

```bash
cd /path/to/codex-pet-dev-board
bash mac/install.sh
```

Rerun the same command after pulling a new repository version. It first copies
an existing venv (or creates a new one) into a sibling staged runtime, then
updates the daemon, device selector, hook, usage reader, requirements, and hash-locked
dependencies only in that stage. The live runtime remains untouched until the
launchd unload preflight succeeds. When `--port` is omitted, an existing explicit port is
preserved; pass `--port /dev/cu.usbmodem...` when more than one plausible board
is attached, or `--port auto` to reset an explicit selection. When an attested
pin is required, pass `--p4-usb-serial <serial>` with an explicit port; the
installer preserves the port/pin tuple together, and
`--clear-p4-usb-serial` explicitly removes the pin. A preserved or
explicit path is still rejected at runtime unless its current metadata identifies
the P4 by the exact descriptor rules above or matches the separately enrolled
pin contract. Generic Espressif USB metadata without a pin cannot be selected.
The installer marks its plist as Codex Pet managed and recognizes
an older unmarked plist only when its normalized Python and daemon paths exactly
match the current runtime. It stages the replacement runtime tree off-path,
proves every recognized competing job and the selected job are unloaded, and
only then swaps the staged runtime and atomically installs the new plist. Before
any unload it snapshots every affected plist and loaded state. A partial
unload, runtime/plist replacement, cleanup, or bootstrap failure restores the
original runtime and plist files before re-bootstrapping only the jobs that
were previously loaded. If runtime restoration fails, no prior job is restarted;
an incomplete rollback is reported explicitly.
`--skip-launchctl` is therefore accepted for same-label file refreshes only;
it refuses any label migration that would leave
competing jobs for the next login. The installer unloads/removes default,
legacy, and recognized custom-label competitors when necessary so only the
selected service can own the Serial port. The installed LaunchAgent uses the
default
`~/.codex/sessions` root and enables usage collection when the P4 advertises it;
`--no-usage` and `--sessions-root` are manual daemon options, not installer
flags. The daemon connection log identifies `clock, quota, usage, weather`
after a successful current-firmware capability handshake. CodexBar itself is
not copied into the runtime and must remain installed separately.

To remove it:

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.coke1120.codex-pet.plist
rm ~/Library/LaunchAgents/com.coke1120.codex-pet.plist
```

Logs are written beside the runtime under
`~/Library/Application Support/CodexPet/daemon.out.log` and `daemon.err.log`.

## 4. Configure Codex hooks

Codex loads user hooks from `~/.codex/hooks.json`. After installing the isolated
runtime in step 3, use the merger from the repository root to add every
maintained lifecycle event without replacing unrelated hooks:

```bash
python3 tools/install_codex_hooks.py \
  --hooks "$HOME/.codex/hooks.json" \
  --python "$HOME/Library/Application Support/CodexPet/runtime/bin/python" \
  --hook-script "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_hook.py"
```

The merger is additive: it preserves unrelated hooks and does not silently
replace a different existing command. When migrating an older Codex Pet setup,
inspect `~/.codex/hooks.json` and remove only obsolete Codex Pet groups that
still point into a repository path before trusting the installed-runtime group.

[`examples/codex-hooks.json`](../examples/codex-hooks.json) shows the resulting
event groups and can also be merged manually after replacing
`/ABSOLUTE/PATH/TO/codex-pet-dev-board` with the real repository path.

The hook commands should point to the Application Support runtime shown above;
rerunning the installer keeps that copy current without requiring
Codex/background processes to access repository source under `Documents`.
Confirm the installed hook hash matches the intended repository source before
trusting it. Repeat both the runtime installation and hook merge/trust flow on
every Mac that will drive the board; a `/dev/cu.*` path from another Mac is not
portable.

Restart Codex Desktop after changing hooks. Codex requires non-managed command
hooks to be reviewed and trusted before they run. Open `/hooks` in Codex, inspect
the exact commands, and trust them only when they point to the verified
Application Support runtime. Repository-source commands under `Documents` may
work in an interactive shell yet fail in the background due to macOS privacy
controls; do not treat interactive readability as hook-runtime proof.

The hook always exits successfully and never makes allow/deny decisions, so a
display or Serial failure cannot block a Codex turn.

## Verification

With the daemon running and the JC4880P443C-I-W connected:

1. Verify exactly one process owns the explicit, USB-identified P4 port.
2. In one direct serial session, require `pong`, `STATE ...`, and the full
   `CAPABILITIES 2 ...` response before starting launchd.
3. Open or resume a Codex conversation: `idle`.
4. Submit a prompt: `running`.
5. Let Codex run tests, lint, review, or type checking: `review`.
6. Trigger an approval request when the selected permission mode supports it: `waiting`.
7. Let the turn finish: `idle`.
8. On the P4 Home screen, swipe up and compare five-hour/weekly remaining,
   reset times, and credits against CodexBar. A missing CodexBar window must
   display as unavailable rather than `100%`.

Run the local regression tests after changes:

```bash
mac/.venv/bin/python -m unittest discover -s tests -v
PYTHONPYCACHEPREFIX=/tmp/codex-pet-pycache \
  mac/.venv/bin/python -m py_compile mac/*.py tools/*.py tests/*.py
```

## Current limitations

- Codex exposes lifecycle events, not a stable public API for the decorative on-screen pet's exact animation frame. This integration reflects agent activity states rather than scraping UI pixels.
- `PermissionRequest` appears only when Codex actually asks for approval. A configuration such as `approval_policy = "never"` will not emit that event.
- Hook definitions are security-sensitive executable configuration. Review and trust are intentionally user-controlled in Codex; do not bypass that trust flow for normal desktop use.
- Wi-Fi settings are managed on the optional P4/C6 wireless candidate, not by
  this host runtime. Credentials are RAM-only on the P4, disappear on reboot,
  and require an explicit reconnect; the host never receives or persists them.
- CodexBar does not yet expose a supported command for reading the menu-bar
  app's persisted cache, so the daemon invokes the same official provider stack
  through its OAuth JSON CLI. If that command fails, the last numeric snapshot
  remains visible and the daemon emits a deduplicated warning.
- Codex session JSONL remains only as compatibility input for firmware without
  `quota`; it is not a stable billing API.
