---
name: embedded-display-development
description: Evidence-gated ESP32-P4 display bring-up and blank-screen recovery for the GUITION JC4880P443C-I-W. Use when identifying its USB connectors, flashing or verifying P4 firmware, capturing early boot failures, testing the serial protocol, isolating display regressions, preparing safe/wireless A/B artifacts, or verifying icon and glyph rendering.
---

# Embedded Display Development

Read [references/jc4880p443c-i-w-bringup.md](references/jc4880p443c-i-w-bringup.md) before changing firmware or operating the board.

Work from runtime evidence:

1. Preserve the user's worktree and record the exact source revision.
2. Stop every serial owner and identify the physical connector, current USB identity, and newly enumerated port after each reset.
3. Probe chip and flash only in confirmed P4 Download Mode.
4. Verify bootloader, partition table, and application independently against the exact binaries intended for comparison.
5. Build only with ESP-IDF 5.5.1 in a clean isolated build directory and isolated effective sdkconfig; never flash repo-local `build/` or `sdkconfig` state.
6. Require `CONFIG_ESP_MAIN_TASK_STACK_SIZE=7680`, a successful fatal 768-byte frame gate, and non-empty `.su` stack-usage evidence for every P4 variant.
7. Capture a complete normal boot from before reset through readiness or panic, including all main-init stack-high-water and internal-heap checkpoints.
8. Test `ping`, `status`, and `capabilities` in one persistent, exclusive, explicitly identified P4 serial session.
9. Record the physical screen state separately from USB, flash, boot, and backlight evidence.
10. Isolate the first regressing subsystem before editing configuration or firmware.
11. After a fix, clean-build the exact P4 target, run tests, flash only the P4, repeat all three read-back verifies, recapture boot/protocol evidence, and obtain visual confirmation.
12. Keep display-safe P4, wireless P4, and matching C6 artifacts in separate directories with their own hashes and configuration identity; keep the C6 untouched during display-safe recovery.
13. Verify requested glyph coverage before using Unicode. Use LVGL primitives or licensed image assets when the configured fonts lack emoji.
14. Treat copied bundles and wireless-enabled builds as candidates until their exact binaries pass read-back, boot, protocol, resource, and physical checks.

ESP-IDF is the sole maintained MCU framework; LVGL, the BSP, and ESP-Hosted are
components, while Arduino is unsupported and inactive. Do not infer display
success from compilation, write-side hashes, USB enumeration, boot readiness,
or backlight alone. Do not change GPIO, DSI timing, BSP, or PSRAM settings
without runtime evidence pointing there. Do not flash the ESP32-C6 unless it is
explicitly in scope.

Report the exact device/port, chip and flash identity, each flash-region result, boot or panic evidence, protocol replies, physical screen state, root cause, changed files, verification, and any remaining hardware-only evidence.

Use `$codex-pet-host-sync` after direct protocol succeeds when the remaining issue is lifecycle hooks, launchd, clock, weather, CodexBar quota, or legacy usage synchronization.
