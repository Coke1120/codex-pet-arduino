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

The hook stores only a hashed session key, mapped state, event name, and timestamp under:

```text
~/Library/Application Support/CodexPet/sessions/
```

It does **not** store prompts, assistant messages, tool output, transcript paths, or working-directory paths.

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

## 1. Install CodexBar and the Python dependency

Install and sign in to [CodexBar](https://github.com/steipete/CodexBar). The
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
.venv/bin/python -m pip install -r requirements.txt
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
then pass its exact `/dev/cu.*` path using `--port`.
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
  --sessions-root /path/to/codex/sessions
```

An incomplete capability response is retried instead of silently downgrading the
v2 board. Weather, quota, and legacy usage
failures retain their last good caches and are reported once per distinct error
until a successful refresh.

## 3. Configure Codex hooks

Codex loads user hooks from `~/.codex/hooks.json`. From the repository root,
use the merger to add every maintained lifecycle event without replacing
unrelated hooks:

```bash
python3 tools/install_codex_hooks.py \
  --hooks ~/.codex/hooks.json \
  --python python3 \
  --hook-script mac/codex_pet_hook.py
```

[`examples/codex-hooks.json`](../examples/codex-hooks.json) shows the resulting
event groups and can also be merged manually after replacing
`/ABSOLUTE/PATH/TO/codex-pet-dev-board` with the real repository path.

After installing the macOS runtime in step 4, the hook commands may instead
point to `~/Library/Application Support/CodexPet/runtime/codex_pet_hook.py`;
rerunning the installer keeps that copy current without granting a LaunchAgent
access to the repository under `Documents`.

Restart Codex Desktop after changing hooks. Codex requires non-managed command hooks to be reviewed and trusted before they run. Open `/hooks` in Codex, inspect the exact commands, and trust them only if the paths point to this local repository.

The hook always exits successfully and never makes allow/deny decisions, so a display or Serial failure cannot block a Codex turn.

## 4. Install or update the launchd runtime

macOS may deny background LaunchAgents access to source code kept under
`Documents`. The installer maintains a small runtime copy under
`~/Library/Application Support/CodexPet/runtime`, installs its isolated Python
environment, copies the usage reader with the daemon, and loads
`com.coke1120.codex-pet` as a per-user LaunchAgent:

```bash
cd /path/to/codex-pet-dev-board
bash mac/install.sh
```

Rerun the same command after pulling a new repository version. It atomically
updates the copied daemon, hook, requirements, and plist before restarting the
single service. When `--port` is omitted, an existing explicit port is
preserved; pass `--port /dev/cu.usbmodem...` when more than one plausible board
is attached, or `--port auto` to reset an explicit selection. The installer also
migrates the former `org.example.codex-pet` LaunchAgent so only one daemon can
own the Serial port. The installed LaunchAgent uses the default
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

## Verification

With the daemon running and the JC4880P443C-I-W connected:

1. Open or resume a Codex conversation: `idle`.
2. Submit a prompt: `running`.
3. Let Codex run tests, lint, review, or type checking: `review`.
4. Trigger an approval request when the selected permission mode supports it: `waiting`.
5. Let the turn finish: `idle`.
6. On the P4 Home screen, swipe up and compare five-hour/weekly remaining,
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
- CodexBar does not yet expose a supported command for reading the menu-bar
  app's persisted cache, so the daemon invokes the same official provider stack
  through its OAuth JSON CLI. If that command fails, the last numeric snapshot
  remains visible and the daemon emits a deduplicated warning.
- Codex session JSONL remains only as compatibility input for firmware without
  `quota`; it is not a stable billing API.
