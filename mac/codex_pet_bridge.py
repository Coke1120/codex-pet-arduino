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
from pathlib import Path
from typing import Iterable, List, Optional

MAC_DIR = Path(__file__).resolve().parent
if str(MAC_DIR) not in sys.path:
    sys.path.insert(0, str(MAC_DIR))

from codex_pet_device import board_score, canonicalize_usb_serial, select_p4_port

try:
    import serial
    from serial.tools import list_ports
    from serial.tools.list_ports_common import ListPortInfo
except ImportError as exc:
    raise SystemExit(
        "pyserial is required. Install it with: python3 -m pip install pyserial"
    ) from exc

VALID_STATES = ("idle", "running", "waiting", "review")
MAX_BAUD = 4_000_000


def valid_baud(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise argparse.ArgumentTypeError("expected an integer baud rate") from exc
    if not 1 <= value <= MAX_BAUD:
        raise argparse.ArgumentTypeError(
            "expected a baud rate between 1 and {}".format(MAX_BAUD)
        )
    return value


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


def choose_port(requested: str, pinned_serial: Optional[str] = None) -> str:
    ports = detected_ports()
    selected = select_p4_port(ports, requested, pinned_serial)
    if selected is not None:
        return selected
    if pinned_serial is not None:
        raise SystemExit(
            "The requested port does not uniquely match the pinned ESP32-P4 USB "
            "identity. Verify the explicit /dev/cu.* path and current USB metadata."
        )
    if requested != "auto":
        raise SystemExit(
            "The requested port is not an identifiable Codex Pet P4. "
            "Exact ESP32-P4/JC4880P443C metadata is required; generic "
            "Espressif USB JTAG/serial descriptors are rejected. Inspect "
            "the port list and pass the verified /dev/cu.* device."
        )
    plausible = [port for port in ports if board_score(port) > 0]
    if not plausible:
        raise SystemExit(
            "No identifiable Codex Pet board serial port found. Reconnect the board, "
            "inspect the port list, then choose the verified port with --port."
        )
    if len(plausible) != 1:
        joined = "\n  ".join(port_description(port) for port in plausible)
        raise SystemExit(
            "More than one supported Codex Pet board was found; auto mode will "
            "not guess. Verify the intended device and choose it with --port:\n  "
            + joined
        )
    raise AssertionError("shared selector rejected one descriptor-qualified port")


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
    parser.add_argument(
        "--port",
        default="auto",
        help=(
            "verified P4 /dev/cu.* path or 'auto'; exact ESP32-P4/JC4880P443C "
            "metadata is required"
        ),
    )
    parser.add_argument("--baud", type=valid_baud, default=115200)
    parser.add_argument(
        "--p4-usb-serial",
        help="pin one explicit P4 /dev/cu.* port by its complete USB serial",
    )
    parser.add_argument("--list", action="store_true", help="list serial ports and exit")
    parser.add_argument("--state", choices=VALID_STATES, help="send one state and exit")
    parser.add_argument("--interactive", action="store_true", help="prompt for states")
    parser.add_argument("--stdin", action="store_true", help="read states line-by-line from stdin")
    args = parser.parse_args()

    if args.p4_usb_serial is not None:
        if args.port == "auto" or not args.port.startswith("/dev/cu."):
            parser.error("--p4-usb-serial requires an explicit /dev/cu.* --port")
        try:
            args.p4_usb_serial = canonicalize_usb_serial(args.p4_usb_serial)
        except ValueError:
            parser.error("--p4-usb-serial must be a complete 12-hex USB serial")

    if args.list:
        ports = detected_ports()
        print("\n".join(port_description(p) for p in ports) if ports else "No serial ports found.")
        return 0

    selected_modes = sum(bool(x) for x in (args.state, args.interactive, args.stdin))
    if selected_modes != 1:
        parser.error("choose exactly one of --state, --interactive, or --stdin")

    port = choose_port(args.port, args.p4_usb_serial)
    print("Opening {} at {} baud...".format(port, args.baud))

    # Opening the USB serial port resets the ESP32-P4; allow it to boot.
    try:
        board = serial.Serial(
            port,
            args.baud,
            timeout=0.08,
            write_timeout=1.0,
            exclusive=True,
        )
    except (OSError, serial.SerialException) as exc:
        print("Serial error:", exc, file=sys.stderr)
        return 1

    with board:
        try:
            if (
                select_p4_port(detected_ports(), args.port, args.p4_usb_serial)
                != port
            ):
                raise OSError("ESP32-P4 USB identity changed after opening the port")
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
