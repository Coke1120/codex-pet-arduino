## Summary

<!-- What changed and why? -->

## Verification

<!-- Exact commands, hardware, and observed results. Remove personal paths and identifiers. -->

- [ ] Python tests pass with `python3 -m unittest discover -s tests -v`
- [ ] Python syntax passes with `python3 -m py_compile mac/*.py tools/*.py tests/*.py`
- [ ] ESP32-P4 firmware builds with ESP-IDF 5.5.1, or the limitation is explained
- [ ] ESP32-C6 slave builds when ESP-Hosted or wireless behavior changes
- [ ] Visual/touch changes were checked on a JC4880P443C-I-W, or the limitation is explained

## Safety and privacy

- [ ] No credentials, usernames, absolute home-directory paths, serial numbers, or private logs are included
- [ ] Wi-Fi details and private/custom pet artwork are excluded
- [ ] Wiring, GPIO, timing, power, or connector assumptions are documented
- [ ] P4 flash/PSRAM, display timing, and event-loop impact were considered
- [ ] The change stays within the JC4880P443C-I-W and macOS support policy
