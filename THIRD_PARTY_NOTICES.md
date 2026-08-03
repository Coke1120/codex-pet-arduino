# Third-party components

Codex Pet is MIT-licensed. Its optional build dependencies retain their own
licenses and are not relicensed by this repository.

## ESP32-P4 target

ESP-IDF Component Manager resolves the exact component graph recorded in
`esp32-p4/dependencies.lock`. Each component remains subject to its upstream
license.

The JC4880P443C-I-W target currently pins:

- `csvke/esp32_p4_jc4880p433c_bsp` at
  `932af3aaee532af144087b6126aaa48eb9124be4`
- Espressif [`esp_wifi_remote` 1.6.3](https://components.espressif.com/components/espressif/esp_wifi_remote/versions/1.6.3),
  licensed under Apache-2.0
- Espressif [`esp_hosted` 2.12.12](https://components.espressif.com/components/espressif/esp_hosted/versions/2.12.12),
  licensed under Apache-2.0; its managed source includes the matching ESP32-C6
  slave project

The pinned `csvke` BSP snapshot does not include a machine-readable license or
a license file. Therefore this repository does **not** vendor that BSP's source or
publish prebuilt firmware binaries containing it. Before distributing such a
binary, obtain written license clarification from the BSP author or replace the
BSP with a clearly licensed implementation. Building it locally for hardware
bring-up does not grant redistribution rights.

Private/custom pet artwork is also excluded from this repository. Generated
`pet_generated.c` files must not be published unless the artwork's
redistribution rights are explicit.
