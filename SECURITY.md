# Security Policy

## Supported versions

The latest revision on the default branch receives security and privacy fixes.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting feature if it is enabled for this repository. Otherwise, contact the maintainer through the private contact method listed on the GitHub profile rather than opening a public issue.

Please include a concise description, affected component, reproduction steps, and expected impact. Do not include credentials, usernames, absolute home-directory paths, serial-device inventories, or unrelated private logs.

## Hardware safety

Arduino Uno GPIO is 5V logic, while the ST7735 controller is normally 3.3V logic. Verify that the breakout provides level shifting or use a suitable external level shifter. Confirm backlight current limiting before connecting `BLK` or `LED` to 5V.
