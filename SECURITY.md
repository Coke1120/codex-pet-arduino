# Security Policy

## Supported versions

The latest revision on the default branch receives security and privacy fixes
for the GUITION JC4880P443C-I-W firmware and macOS host runtime. Retired hardware
targets and non-macOS host environments are not supported.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature if it is enabled for this
repository. Otherwise, contact the maintainer through the private contact method
listed on the GitHub profile rather than opening a public issue.

Include a concise description, affected component, reproduction steps, and
expected impact. Do not include credentials, usernames, absolute home-directory
paths, serial-device inventories, Wi-Fi network details, or unrelated private
logs.

## Hardware safety

- Confirm the PCB model is exactly `JC4880P443C-I-W` before flashing or changing
  display, touch, SDIO, backlight, or power configuration.
- The ESP32-P4 and ESP32-C6 are separate flash targets. Identify the chip and
  connector before writing an image.
- Disconnect power before changing internal connections. Do not substitute
  timings, voltages, or GPIO assignments from a visually similar board.
- Treat a successful build as software evidence only. Complete the physical
  acceptance checklist in [`docs/ESP32_P4.md`](docs/ESP32_P4.md) before relying
  on changed hardware behavior.
