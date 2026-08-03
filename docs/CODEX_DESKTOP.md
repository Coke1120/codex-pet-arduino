# Direct Codex Desktop and CLI synchronization

The Python hook and Serial daemon connect Codex on macOS to the
JC4880P443C-I-W over USB Serial. The ESP32-P4 negotiates lifecycle, clock, Hong
Kong weather, and local Codex Usage synchronization before the daemon starts
optional data workers.

The basic `codex_pet_bridge.py` is intentionally manual: it sends only the state supplied through `--state`, `--interactive`, or `--stdin`. It does not inspect Codex Desktop automatically.

For direct reflection, this repository uses the official Codex lifecycle hooks documented at <https://developers.openai.com/codex/hooks>:

```text
Codex lifecycle event ──▶ codex_pet_hook.py ──▶ lifecycle state ─┐
                                                                   ├─▶ daemon ──▶ USB Serial ──▶ Pet
~/.codex/sessions ──▶ codex_pet_usage.py ──▶ token aggregates ─┘
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

## Codex Usage data

By default, the daemon reads Codex's local session files under
`~/.codex/sessions` on macOS. It accepts only JSONL `event_msg`
records whose payload type is `token_count`, then sends these five integers to a
P4 that advertises the `usage` capability:

- total tokens reported by the newest session event
- sum of today's per-event token deltas
- today's cached input tokens
- today's input tokens, used with the cached count to calculate the displayed ratio
- the local update time as a Unix timestamp

The reader does not serialize prompt text, assistant messages, tool calls, tool
output, paths, or arbitrary JSON fields. Its cache contains only the same five
aggregate integers. These values describe locally recorded Codex activity; they
are **not** a subscription quota, billing balance, or account-wide usage report.

Today's totals follow the computer's local calendar day. The daemon refreshes
the aggregate at most once per minute and preserves the last good cache if a
session file is temporarily unreadable. The P4 marks the display aging after
five minutes and stale after 30 minutes. An empty or missing sessions directory
produces zero aggregates rather than guessing account usage. The default cache
is `~/Library/Application Support/CodexPet/usage-cache.json`.

## 1. Install Python dependency

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
The daemon re-sends the selected state every five seconds by default so a board reset cannot silently desynchronize the display. Use `--heartbeat SECONDS` to choose another positive interval. On a P4 that advertises `clock`, `weather`, and `usage`, it also sends local time once per minute, fetches Hong Kong weather in a background thread every 15 minutes, and reads local token aggregates at most once per minute. Each worker starts only after capability negotiation and never during `--dry-run`. Use `--no-weather` to disable network weather retrieval or `--no-usage` to disable local session scanning. Use `--sessions-root PATH` when Codex stores session JSONL files somewhere other than `~/.codex/sessions`:

```bash
.venv/bin/python codex_pet_daemon.py \
  --port /dev/cu.<verified-p4-port> \
  --sessions-root /path/to/codex/sessions
```

An incomplete capability response is retried instead of silently downgrading the
v2 board. Weather and usage
failures retain their last good caches and are reported once per distinct error
until a successful refresh.

## 3. Configure Codex hooks

Codex loads user hooks from `~/.codex/hooks.json`. Start from
[`examples/codex-hooks.json`](../examples/codex-hooks.json), replace every
`/ABSOLUTE/PATH/TO/codex-pet-dev-board` with the real repository path, and merge
its event groups into any existing `~/.codex/hooks.json` rather than overwriting
unrelated hooks.

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
flags. The daemon connection log identifies `clock, usage, weather` after a
successful P4 capability handshake.

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
6. On the P4 Home screen, swipe up and verify latest-session tokens, today's
   total, cached-input ratio, and update time. Compare only against local
   `token_count` events, not an account quota.

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
- Codex session JSONL is a local implementation surface, not a stable billing
  API. If its `token_count` schema changes, the reader keeps the last good
  aggregate and reports a warning instead of reading unrelated transcript data.
