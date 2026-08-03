# JC4880P443C-I-W BSP source snapshot

This directory preserves the redistributable ESP-IDF board-support sources from
the vendor package `JC4880P443C_I_W.zip` supplied on 2026-08-04.

## Provenance

- Source archive SHA-256:
  `7cea2154667033a639b62a42d1952066ca55c78e187846351f5facb0c3f5232f`
- Source archive size: `309232242` bytes
- Archive subtrees:
  - `1-Demo/idf_examples/ESP-IDF_5.5.4/xiaozhi-esp32-main/main/boards/guition-jc4880p443/`
  - `1-Demo/idf_examples/ESP-IDF_5.5.4/common_components/`
- Imported files: 65 board, component, metadata, documentation, test, and
  license files
- Normalization: trailing whitespace was removed from imported text files; no
  executable statements, configuration values, binary assets, or license text
  were changed
- Per-file provenance: [`SOURCE_MANIFEST.tsv`](SOURCE_MANIFEST.tsv) records the
  vendored and original archive-entry SHA-256 values plus both paths

Included model-specific board support:

- `boards/guition-jc4880p443/config.h`
- `boards/guition-jc4880p443/config.json`
- `boards/guition-jc4880p443/jc4880p443.cc`
- `boards/guition-jc4880p443/README.md`

These are the package's JC4880-specific board files. They define the 480×800
panel timing, two-lane MIPI-DSI configuration, ST7701 initialization, LCD reset
GPIO5, backlight GPIO23, and GT911 interrupt/reset GPIO21/22.

Included common components used by the supplied examples:

- `bsp_extra` version `0.0.2`
- `espressif__esp32_p4_function_ev_board` version `5.2.3`
- `espressif__esp_lcd_st7701` version `1.1.3`

The ST7701 component is included because the common BSP declares it as a
relative local dependency. The model-specific board source and its copied
`xiaozhi-esp32-main` license are MIT-licensed. The common components retain
their Apache-2.0 licenses; the imported `example_rgb_avoid_tearing.c` example is
marked CC0-1.0 in its source header.

## Scope and integration

The original 309 MB archive is intentionally not committed. It also contains
videos, prebuilt firmware, Windows utilities, full example applications, and
third-party packages outside this BSP's buildable source boundary.

This snapshot is retained for hardware provenance, comparison, and a future
controlled BSP migration. The model-specific files depend on the surrounding
Xiaozhi application abstractions and are not selected directly by this
repository's CMake build. The production Codex Pet firmware continues to use
the known-working, commit-pinned `csvke/esp32_p4_jc4880p433c_bsp` dependency
declared in `esp32-p4/main/idf_component.yml`; vendoring this reference does not
silently change display timings, pin routing, camera behavior, or the verified
build.

Before switching the active dependency, compare the vendor configuration against
the exact `JC4880P443C-I-W` PCB revision and repeat the physical display, touch,
PSRAM, Serial, and camera-inactive acceptance checklist.
