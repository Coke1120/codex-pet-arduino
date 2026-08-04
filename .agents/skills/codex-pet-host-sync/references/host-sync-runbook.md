# Codex Pet macOS host-sync runbook

## Contents

- [Evidence layers](#evidence-layers)
- [Safety and privacy](#safety-and-privacy)
- [Establish identity](#establish-identity)
- [Test the P4 protocol directly](#test-the-p4-protocol-directly)
- [Diagnose an always-idle pet](#diagnose-an-always-idle-pet)
- [Verify the installed hook path and trust](#verify-the-installed-hook-path-and-trust)
- [Verify clock and weather](#verify-clock-and-weather)
- [Verify CodexBar quota](#verify-codexbar-quota)
- [Install and inspect the daemon](#install-and-inspect-the-daemon)
- [Completion evidence](#completion-evidence)

## Evidence layers

Do not collapse these layers into one success claim:

| Layer | Evidence |
|---|---|
| Firmware protocol | Exact `ping`, `status`, and `capabilities` replies |
| Direct data path | Exact ACK for injected `clock`, `weather`, and `quota` commands |
| Hook mapping | Privacy-safe state file changes for known Codex events |
| Daemon | One process exclusively owns the USB-identified P4 port and negotiates current capabilities |
| Provider | Open-Meteo or CodexBar returns a valid snapshot |
| Physical UI | The observer confirms the expected state and values on the panel |

An injected snapshot does not prove a provider. A provider snapshot does not
prove Serial delivery. Readiness or an ACK does not prove visible pixels.

## Safety and privacy

- Stop direct bridges, monitors, and the LaunchAgent before opening Serial.
- Do not use a CH340 port as the P4 application console.
- Keep one exclusive, persistent Serial owner; reopening the port can reset the board.
- Merge Codex hooks without replacing unrelated hooks. Keep hook trust user-controlled.
- Never log prompts, transcripts, tool output, working directories, Wi-Fi passwords,
  CodexBar email, account identity, or raw OAuth JSON.
- Obtain explicit authorization before a live CodexBar OAuth refresh. A version
  check or fixture test is not live account access.
- Wi-Fi credentials never enter the host runtime. The optional P4/C6 wireless
  candidate keeps them in RAM only, loses them on reboot, and requires reconnect.
- Use `$embedded-display-development` before any flash or P4/C6 hardware change.

## Establish identity

From the repository root, record:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse origin/main
```

Check source/runtime drift when the LaunchAgent is already installed:

```bash
shasum -a 256 mac/codex_pet_daemon.py mac/codex_pet_hook.py mac/codex_pet_usage.py
shasum -a 256 \
  "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_daemon.py" \
  "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_hook.py" \
  "$HOME/Library/Application Support/CodexPet/runtime/codex_pet_usage.py"
```

Reinstall after source changes instead of debugging a stale runtime. Identify the
exact P4 `/dev/cu.*` port and run `lsof "$PORT"` before opening it. Automatic
selection must remain unambiguous; pass `--port` when multiple Espressif devices
are attached. Explicit selection is not a bypass: current USB metadata must still
identify a supported P4 by the exact `ESP32-P4` or `JC4880P443C` descriptor; C6
metadata, generic Espressif VID `303A` `USB JTAG/serial debug unit` metadata, and
generic CH340 paths are not accepted. There is no generic-descriptor override.
Require no owner before the test and one expected exclusive owner after opening
the port. The bridge must complete the exact P4 `ping` handshake before a state
write; the daemon must complete both `ping` and capability negotiation first.

## Test the P4 protocol directly

Unload the daemon first:

```bash
pkill -f 'codex_pet_daemon.py' 2>/dev/null || true
launchctl bootout "gui/$(id -u)/com.coke1120.codex-pet" 2>/dev/null || true
```

Use one interactive bridge session and send:

```text
ping
status
capabilities
```

Current firmware replies with these forms:

```text
pong
STATE <CURRENT_STATE>
CAPABILITIES 2 lifecycle clock weather today-v1 usage usage-v1 quota quota-v1 codexbar-v1 wireless settings-v1
```

Then inject deterministic test data in the same session:

```text
clock 1785853587 28800
weather 29.5 27 32 82 thunder 1785853587
quota -1 0 52 1786173679 0 1785853587
```

Require `OK CLOCK`, `OK WEATHER`, and `OK QUOTA`. Confirm time/date, weather,
condition icon, unknown five-hour quota, weekly `52%`, and credits `0` physically.
Label these as injected values, not current provider data.

## Diagnose an always-idle pet

`STATE IDLE` alone does not show whether hooks or the daemon are working. Isolate
hook mapping without Serial or network by using a temporary state directory:

```bash
HOST_SYNC_STATE="$(mktemp -d)"
CODEX_PET_STATE_DIR="$HOST_SYNC_STATE" python3 mac/codex_pet_hook.py \
  <<<'{"hook_event_name":"UserPromptSubmit","session_id":"host-sync-test"}'
CODEX_PET_STATE_DIR="$HOST_SYNC_STATE" python3 mac/codex_pet_daemon.py --dry-run --once
```

The daemon should print `running`. The hook record may contain only version,
mapped state, event name, and timestamp under a hashed filename. Test real hooks
separately after installing them: restart Codex, review and trust the configured
commands, then observe prompt → `running`, test/review work → `review`, a real
permission request → `waiting`, and turn stop → `idle`.

Multiple sessions aggregate by `waiting` → `review` → `running` → `idle`.
Records expire after 15 minutes by default. A manual status-card state is a panel
test and is replaced by the daemon heartbeat.

The hook records only `version`, mapped state, an allow-listed event name, and a
timestamp under a hashed 24-hex session filename. Require the sessions directory
to be mode `0700` and each record mode `0600`. Prompts, transcripts, tool output,
working directories, Wi-Fi credentials, and account identity must not appear.
Malformed or foreign JSON must not become lifecycle state.

## Verify the installed hook path and trust

macOS may allow an interactive shell to read repository source under
`Documents` while denying the Codex/background hook process. Use the isolated
runtime path:

```text
~/Library/Application Support/CodexPet/runtime/codex_pet_hook.py
```

After `bash mac/install.sh`, compare its SHA-256 with
`mac/codex_pet_hook.py`. Merge Codex Pet hook entries without replacing unrelated
hooks, restart Codex, open `/hooks`, inspect the exact commands, and trust only
the verified Application Support path. Interactive readability and a successful
fixture invocation do not prove the post-restart Codex trust/runtime layer.

## Verify clock and weather

The daemon sends local time once per minute and advances time on the P4 between
syncs. Weather is fetched for Hong Kong off the Serial thread every 15 minutes.
Confirm independently:

1. Direct injected commands render correctly.
2. The daemon negotiated `clock` and `weather`.
3. A live fetch updated the sanitized weather cache.
4. The panel shows the same condition and values.

Weather failures retain the last good value and emit deduplicated warnings.
Do not call stale cached data a successful current fetch.

## Verify CodexBar quota

First confirm CodexBar is installed without accessing account data:

```bash
codexbar --version
```

With explicit user authorization, Codex Pet invokes:

```text
codexbar --provider codex --source oauth --format json --json-only
```

Treat the raw output as private. The adapter must select the `codex` provider,
convert used percentages to remaining percentages, and retain only six numbers:
five-hour remaining/reset, weekly remaining/reset, credits in tenths, and update
epoch. An absent window is `-1` with reset `0`; never convert it to `100%`.

When P4 advertises `quota`, the daemon prefers CodexBar and does not scan local
sessions. Legacy `usage` aggregation runs only when `quota` is absent. A failed
refresh preserves the last good numeric cache and must be reported as stale or
failed, not as a fresh zero balance.

## Install and inspect the daemon

Install or update the isolated runtime only after direct protocol tests:

```bash
bash mac/install.sh --port /dev/cu.<verified-p4-port>
```

The current service label is `com.coke1120.codex-pet`. New plists carry a Codex
Pet managed marker; an unmarked legacy/custom plist is recognized only when its
normalized Python and daemon paths exactly match the current runtime. The
installer stages the full venv/runtime off-path, including hash-locked
dependencies, while leaving the live runtime untouched. It prepares the new
plist off-path and snapshots every affected plist and loaded state before
unloading recognized competitors and the selected service. It swaps the staged
runtime and replaces the selected plist only after those checks pass. A partial
unload, runtime/plist replacement, cleanup, or bootstrap failure restores the
original runtime and plist files before re-bootstrapping only the previously
loaded jobs. If runtime restoration fails, prior jobs remain stopped. Treat an explicit
`rollback incomplete` diagnostic as a failed installation requiring manual
launchd inspection. Because launchd state cannot be reconciled safely in that
mode, `--skip-launchctl` refuses a label
migration when a competing recognized/default/legacy plist exists; use it only
for a same-label file refresh. Inspect service state and logs:

```bash
launchctl print "gui/$(id -u)/com.coke1120.codex-pet"
tail -n 100 "$HOME/Library/Application Support/CodexPet/daemon.out.log"
tail -n 100 "$HOME/Library/Application Support/CodexPet/daemon.err.log"
```

Require one daemon process, the intended port, and a connection line containing
the negotiated `clock`, `quota`, `usage`, and `weather` capabilities. Distinct
warnings should be deduplicated and clear after a successful refresh.

## Completion evidence

Report:

1. Source and installed-runtime identity.
2. Exact P4 port, USB identity, explicit identity decision, and sole exclusive owner.
3. Exact direct protocol requests and replies.
4. Privacy-safe hook fixture, installed-runtime hash, `/hooks` path/trust review,
   file modes, and real lifecycle transition results.
5. Daemon service state, negotiated capabilities, and relevant sanitized logs.
6. Clock, weather, and CodexBar retrieval outcomes separately.
7. Sanitized quota numbers, including unavailable windows.
8. Observer-confirmed time/date/weather/icons/quota and lifecycle state.
9. Any layer not tested, especially live account or physical display evidence.
