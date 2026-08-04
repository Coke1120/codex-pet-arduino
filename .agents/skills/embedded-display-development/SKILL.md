---
name: embedded-display-development
description: Evidence-gated ESP32-P4 display bring-up and blank-screen recovery for the GUITION JC4880P443C-I-W. Use when identifying its USB connectors, flashing or verifying P4 firmware, capturing early boot failures, testing the serial protocol, or isolating display regressions.
---

# Embedded Display Development

Read [references/jc4880p443c-i-w-bringup.md](references/jc4880p443c-i-w-bringup.md) before changing firmware or operating the board.

Work from runtime evidence:

1. Preserve the user's worktree and record the exact source revision.
2. Stop every serial owner and identify the physical connector, current USB identity, and newly enumerated port after each reset.
3. Probe chip and flash only in confirmed P4 Download Mode.
4. Verify bootloader, partition table, and application independently against the exact binaries intended for comparison.
5. Capture a complete normal boot from before reset through readiness or panic.
6. Test `ping`, `status`, and `capabilities` in one persistent serial session.
7. Record the physical screen state separately from USB, flash, boot, and backlight evidence.
8. Isolate the first regressing subsystem before editing configuration or firmware.
9. After a fix, clean-build the exact P4 target, run tests, flash only the P4, repeat all three verifies, recapture boot/protocol evidence, and obtain visual confirmation.

Do not infer display success from compilation, write-side hashes, USB enumeration, boot readiness, or backlight alone. Do not change GPIO, DSI timing, BSP, or PSRAM settings without runtime evidence pointing there. Do not flash the ESP32-C6 unless it is explicitly in scope.

Report the exact device/port, chip and flash identity, each flash-region result, boot or panic evidence, protocol replies, physical screen state, root cause, changed files, verification, and any remaining hardware-only evidence.
