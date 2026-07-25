#!/usr/bin/env python3
"""Mac Serial bridge for the Arduino Codex Pet.

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
    """Return pyserial port records for outbound macOS /dev/cu.* devices."""
    return sorted(
        (p for p in list_ports.comports() if p.device.startswith("/dev/cu.")),
        key=lambda p: p.device,
    )


def arduino_score(port: ListPortInfo) -> int:
    """Rank ports conservatively; a generic USB-serial adapter is not an Uno."""
    text = " ".join(
        str(value or "")
        for value in (port.description, port.manufacturer, port.product, port.interface)
    ).lower()
    score = 0
    if "arduino" in text:
        score += 100
    if "uno" in text:
        score += 50
    if port.device.startswith("/dev/cu.usbmodem"):
        score += 10
    return score


def choose_port(requested: str) -> str:
    if requested != "auto":
        return requested

    ports = detected_ports()
    plausible = [p for p in ports if arduino_score(p) > 0]
    if not plausible:
        raise SystemExit(
            "No identifiable Arduino serial port found. Reconnect the board, run "
            "'arduino-cli board list', then choose the verified port with --port."
        )
    best_score = max(arduino_score(p) for p in plausible)
    candidates = [p for p in plausible if arduino_score(p) == best_score]
    if len(candidates) != 1:
        joined = "\n  ".join(port_description(p) for p in candidates)
        raise SystemExit(
            "More than one plausible Arduino was found; verify one with "
            "'arduino-cli board list' and choose it with --port:\n  " + joined
        )
    return candidates[0].device


def normalise_state(raw: str) -> str:
    state = raw.strip().lower()
    if state not in VALID_STATES:
        raise ValueError(
            "invalid state {!r}; expected {}".format(raw.strip(), ", ".join(VALID_STATES))
        )
    return state


def read_replies(board: serial.Serial, duration: float = 0.25) -> None:
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        line = board.readline()
        if line:
            print("Arduino:", line.decode("utf-8", errors="replace").rstrip())
        else:
            time.sleep(0.01)


def send_state(board: serial.Serial, raw: str) -> None:
    state = normalise_state(raw)
    board.write((state + "\n").encode("ascii"))
    board.flush()
    print("Sent:", state)
    read_replies(board)


def stdin_states() -> Iterable[str]:
    for line in sys.stdin:
        if line.strip():
            yield line


def main() -> int:
    parser = argparse.ArgumentParser(description="Send Codex Pet states to Arduino.")
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

    # Opening the port usually resets an Uno. Wait for its bootloader/setup.
    with serial.Serial(port, args.baud, timeout=0.08, write_timeout=1.0) as board:
        time.sleep(2.0)
        board.reset_input_buffer()
        board.write(b"ping\n")
        board.flush()
        read_replies(board, 0.5)

        if args.state:
            send_state(board, args.state)
        elif args.stdin:
            try:
                for raw in stdin_states():
                    send_state(board, raw)
            except ValueError as exc:
                print("Error:", exc, file=sys.stderr)
                return 2
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
