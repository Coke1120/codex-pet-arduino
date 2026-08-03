# Contributing

Thank you for helping improve Codex Pet. This project maintains the GUITION
JC4880P443C-I-W firmware and its macOS host runtime.

## In-scope contributions

- Reproducible ESP32-P4 display, touch, USB Serial, or ESP32-C6 radio fixes
- Codex Pet v2 action, frame-mapping, conversion, and animation improvements
- Today, Settings, Codex Usage, weather, and lifecycle interaction improvements
- macOS bridge, hook, daemon, LaunchAgent, and installer reliability
- Tests, documentation, hardware safety, privacy, and licensing corrections

Other microcontroller boards and non-macOS hosts are outside the maintained
scope. Do not add compatibility layers, installers, documentation, or roadmap
items for those targets. Code that is portable beyond macOS may remain when it
simplifies the maintained implementation, but portability is not a product
contract.

## Development workflow

1. Fork the repository and create a focused branch.
2. Keep unrelated changes out of the patch.
3. Never commit usernames, absolute home-directory paths, serial-device
   inventories, credentials, private logs, Wi-Fi details, or pet artwork that
   you do not have permission to redistribute.
4. Run the host regression suite and syntax checks on macOS:

   ```bash
   python3 -m unittest discover -s tests -v
   PYTHONPYCACHEPREFIX=/tmp/codex-pet-pycache \
     python3 -m py_compile mac/*.py tools/*.py tests/*.py
   ```

5. For firmware changes, build the ESP32-P4 target with ESP-IDF 5.5.1:

   ```bash
   cd esp32-p4
   idf.py set-target esp32p4
   idf.py build
   ```

6. If the change affects ESP-Hosted or wireless behavior, also build the matching
   ESP32-C6 slave from the resolved managed component.
7. Explain the exact board revision, macOS version, commands, expected behavior,
   and observed result in the pull request. Sanitise port names and logs.

## Code style

- Prefer small functions and non-blocking display, touch, radio, and Serial work.
- Preserve the v2 action manifest, priority, interruptibility, and frame cadence
  unless the change explicitly updates that contract.
- Keep Serial commands lowercase and newline-delimited; update protocol tests and
  documentation when the capability contract changes.
- Keep network operations away from the display and Serial critical paths.
- Add comments for hardware and concurrency assumptions, not obvious code.
- Avoid new dependencies when an existing project utility is sufficient.

## Pull requests

Include:

- A concise summary of the reason for the change
- The hardware and macOS test environment without personal paths or identifiers
- Exact verification commands and their results
- Photos or a short video for display, touch, or animation changes when practical
- Firmware size, timing, memory, protocol, privacy, or compatibility trade-offs
- Any physical verification that remains incomplete

By contributing, you agree that your contribution is licensed under the MIT License.
