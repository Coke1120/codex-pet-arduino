#!/usr/bin/env python3
"""macOS Serial bridge for the ESP32-P4 Codex Pet board.

Examples:
  python3 codex_pet_bridge.py --list
  python3 codex_pet_bridge.py --port /dev/cu.usbmodemXXXX --state running
  python3 codex_pet_bridge.py --port auto --interactive
  printf 'review\nidle\n' | python3 codex_pet_bridge.py --port auto --stdin

Automatic integration can pipe newline-delimited states to --stdin, or call
this script with --state whenever Codex changes phase.
"""

import argparse
import sys
import time
from typing import Iterable, List

try:
    import serial
    from serial.tools import list_ports
    from serial.tools.list_ports_common import ListPortInfo
except ImportError as exc:
    raise SystemExit(
        "pyserial is required. Install it with: python3 -m pip install pyserial"
    ) from exc

VALID_STATES = ("idle", "running", "waiting", "review")


def port_description(port: ListPortInfo) -> str:
    """Return useful public hardware metadata without exposing local paths."""
    details = [port.device]
    if port.description and port.description != "n/a":
        details.append(port.description)
    if port.vid is not None and port.pid is not None:
        details.append("VID:PID={:04X}:{:04X}".format(port.vid, port.pid))
    return " — ".join(details)


def detected_ports() -> List[ListPortInfo]:
    """Return outbound macOS serial devices."""
    return sorted(
        (p for p in list_ports.comports() if p.device.startswith("/dev/cu.")),
        key=lambda p: p.device,
    )


def board_score(port: ListPortInfo) -> int:
    """Rank ports for supported Codex Pet boards without guessing adapters."""
    text = " ".join(
        str(value or "")
        for value in (port.description, port.manufacturer, port.product, port.interface)
    ).lower()
    if "esp32-c6" in text or "esp32c6" in text:
        return 0
    if "esp32-p4" in text or "esp32p4" in text or "jc4880p443c" in text:
        return 150
    is_espressif = port.vid == 0x303A or "espressif" in text
    if (
        is_espressif
        and port.device.startswith("/dev/cu.usbmodem")
        and "usb jtag/serial debug unit" in text
    ):
        return 10
    return 0


def choose_port(requested: str) -> str:
    if requested != "auto":
        return requested

    ports = detected_ports()
    scored = [(board_score(port), port) for port in ports]
    plausible = [(score, port) for score, port in scored if score > 0]
    if not plausible:
        raise SystemExit(
            "No identifiable Codex Pet board serial port found. Reconnect the board, "
            "inspect the port list, then choose the verified port with --port."
        )
    strongest_score = max(score for score, _port in plausible)
    strongest = [port for score, port in plausible if score == strongest_score]
    if len(strongest) != 1:
        joined = "\n  ".join(port_description(port) for port in strongest)
        raise SystemExit(
            "More than one supported Codex Pet board was found; auto mode will "
            "not guess. Verify the intended device and choose it with --port:\n  "
            + joined
        )
    return strongest[0].device


def normalise_state(raw: str) -> str:
    state = raw.strip().lower()
    if state not in VALID_STATES:
        raise ValueError(
            "invalid state {!r}; expected {}".format(raw.strip(), ", ".join(VALID_STATES))
        )
    return state


def exchange(
    board: serial.Serial, command: str, expected: str, duration: float = 0.75
) -> str:
    board.write((command + "\n").encode("ascii"))
    board.flush()
    deadline = time.monotonic() + duration
    received: List[str] = []
    while time.monotonic() < deadline:
        line = board.readline()
        if line:
            reply = line.decode("utf-8", errors="replace").strip()
            if not reply:
                continue
            received.append(reply)
            print("Board:", reply)
            if reply == expected:
                return reply
        else:
            time.sleep(0.01)
    raise OSError(
        "ESP32-P4 did not acknowledge {!r}; received {}".format(command, received)
    )


def send_state(board: serial.Serial, raw: str) -> None:
    state = normalise_state(raw)
    exchange(board, state, "OK " + state.upper())
    print("Sent:", state)


def stdin_states() -> Iterable[str]:
    for line in sys.stdin:
        if line.strip():
            yield line


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Codex Pet states to the board.")
    parser.add_argument("--port", default="auto", help="serial port or 'auto'")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    parser.add_argument("--state", choices=VALID_STATES, help="send one state and exit")
    parser.add_argument("--interactive", action="store_true", help="prompt for states")
    parser.add_argument("--stdin", action="store_true", help="read states line-by-line from stdin")
    args = parser.parse_args()

    if args.list:
        ports = detected_ports()
        print("\n".join(port_description(p) for p in ports) if ports else "No serial ports found.")
        return 0

    selected_modes = sum(bool(x) for x in (args.state, args.interactive, args.stdin))
    if selected_modes != 1:
        parser.error("choose exactly one of --state, --interactive, or --stdin")

    port = choose_port(args.port)
    print("Opening {} at {} baud...".format(port, args.baud))

    # Opening the USB serial port resets the ESP32-P4; allow it to boot.
    try:
        board = serial.Serial(port, args.baud, timeout=0.08, write_timeout=1.0)
    except (OSError, serial.SerialException) as exc:
        print("Serial error:", exc, file=sys.stderr)
        return 1

    with board:
        try:
            time.sleep(2.0)
            board.reset_input_buffer()
            exchange(board, "ping", "pong")

            if args.state:
                send_state(board, args.state)
            elif args.stdin:
                for raw in stdin_states():
                    send_state(board, raw)
            else:
                print("Type idle/running/waiting/review; q exits.")
                while True:
                    try:
                        raw = input("state> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        break
                    if raw.lower() in ("q", "quit", "exit"):
                        break
                    try:
                        send_state(board, raw)
                    except ValueError as exc:
                        print("Error:", exc)
        except ValueError as exc:
            print("Error:", exc, file=sys.stderr)
            return 2
        except (OSError, serial.SerialException) as exc:
            print("Serial error:", exc, file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
