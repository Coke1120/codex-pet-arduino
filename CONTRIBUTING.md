# Contributing

Thank you for helping improve Codex Pet.

## Good contributions

- Reproducible fixes for ST7735 tab variants or colour ordering
- Lightweight animations that fit Arduino Uno memory constraints
- Serial bridge reliability and cross-platform improvements
- Reproducible pet-atlas conversion, palette, compression, and frame-mapping improvements
- Documentation, wiring clarity, and safety corrections

## Development workflow

1. Fork the repository and create a focused branch.
2. Keep unrelated changes out of the patch.
3. Never commit usernames, absolute home-directory paths, serial-device inventories, credentials, private logs, or pet artwork that you do not have permission to redistribute.
4. For Arduino changes, verify the sketch for an Arduino Uno and report flash/RAM usage when available.
5. Run the regression suite, Python syntax checks, and Uno compile:

   ```bash
   python3 -m unittest discover -s tests -v
   PYTHONPYCACHEPREFIX=/tmp/codex-pet-pycache \
     python3 -m py_compile mac/*.py tools/*.py tests/*.py
   arduino-cli compile --fqbn arduino:avr:uno arduino/CodexPet
   ```

6. Explain the hardware tested, display tab setting, expected behaviour, and actual result in the pull request.

## Code style

- Prefer clear, small functions and non-blocking animation based on `millis()`.
- Avoid dynamic allocation and full-screen buffers on Arduino Uno.
- Keep Serial commands lowercase, newline-delimited, and backward compatible.
- Add comments for hardware assumptions rather than restating obvious code.

## Pull requests

Include:

- Summary of the change
- Hardware/software test environment without personal paths or identifiers
- Exact verification steps and output
- Photos or short video for visual changes when practical
- Any memory, performance, wiring, or compatibility trade-offs

By contributing, you agree that your contribution is licensed under the MIT License.
