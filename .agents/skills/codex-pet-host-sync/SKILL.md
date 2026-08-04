---
name: codex-pet-host-sync
description: Evidence-gated diagnosis and verification of Codex Pet's macOS lifecycle hook, launchd daemon, USB Serial capability negotiation, clock, Hong Kong weather, CodexBar quota, and legacy usage fallback. Use when the JC4880P443C-I-W stays idle, time/date/weather/quota is missing or stale, CodexBar disagrees with the display, a daemon owns the wrong port, or the host runtime and hooks are installed or changed.
---

# Codex Pet Host Sync

Read [references/host-sync-runbook.md](references/host-sync-runbook.md) before changing or operating the host integration.

Keep each evidence layer independent:

1. Confirm the source revision, installed Application Support runtime/hash, explicit P4 USB identity, port, and advertised capabilities.
2. Stop every daemon or monitor before direct Serial tests; require one exclusive owner and keep one persistent session.
3. Prove `ping`, `status`, and `capabilities`, then inject clock, weather, and quota test values with exact acknowledgements.
4. Test privacy-safe hook mapping and state aggregation without Serial before diagnosing launchd.
5. Start one daemon, confirm negotiated capabilities, and trigger real lifecycle transitions.
6. Treat weather retrieval, CodexBar retrieval, Serial delivery, and physical rendering as separate results.
7. Access live CodexBar account data only with explicit user authorization. Never expose raw identity-bearing JSON.
8. Review/trust the verified Application Support hook path in Codex; interactive repository access under `Documents` is not background-hook proof.
9. Report exact requests/replies, daemon and hook evidence, sanitized numeric provider values, visible UI state, and any unproven layer.
10. Treat runtime plus LaunchAgent replacement as one transaction: stage the full venv/runtime before unload, recognize managed jobs by marker (or an exact legacy runtime identity), snapshot plist files and loaded states, restore the prior runtime and plists before any re-bootstrap after transition failure, never restart prior jobs when runtime restore fails, report incomplete rollback, and reject `--skip-launchctl` label migrations that would leave competitors.

`STATE IDLE` proves only the P4's current state. Injected values prove the wire/UI path, not live providers. A successful provider query proves retrieval, not Serial delivery or visible pixels.

Port identity is strict: only exact `ESP32-P4` or `JC4880P443C` USB metadata is
identified as the target. Generic Espressif VID `303A` `USB JTAG/serial debug
unit` metadata is rejected in both automatic and explicit selection; there is no
generic-descriptor override. The bridge completes the exact P4 `ping` handshake
before writing state, while the daemon completes both `ping` and capability
negotiation first.

Wi-Fi credentials belong only to the optional P4/C6 wireless candidate: they are
RAM-only, lost on reboot, require reconnect, and never pass through the host
runtime.

Use `$embedded-display-development` for USB download mode, flashing, flash verification, boot/panic capture, blank screens, or P4/C6 display regressions.
