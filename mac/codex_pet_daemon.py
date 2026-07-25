#!/usr/bin/env python3
"""Persistent Codex lifecycle state aggregator and Arduino Serial bridge."""

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

try:
    import serial
    from serial.tools import list_ports
    from serial.tools.list_ports_common import ListPortInfo
except ImportError as exc:
    raise SystemExit(
        "pyserial is required. Install it with: python3 -m pip install pyserial"
    ) from exc

VALID_STATES = ("idle", "running", "waiting", "review")
STATE_PRIORITY = {"idle": 0, "running": 1, "review": 2, "waiting": 3}


def default_state_dir() -> Path:
    override = os.environ.get("CODEX_PET_STATE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / "CodexPet" / "sessions"


def detected_ports() -> List[ListPortInfo]:
    return sorted(
        (p for p in list_ports.comports() if p.device.startswith("/dev/cu.")),
        key=lambda p: p.device,
    )


def arduino_score(port: ListPortInfo) -> int:
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


def choose_port(requested: str) -> Optional[str]:
    if requested != "auto":
        return requested if Path(requested).exists() else None
    candidates = [p for p in detected_ports() if arduino_score(p) > 0]
    if not candidates:
        return None
    best = max(arduino_score(p) for p in candidates)
    winners = [p.device for p in candidates if arduino_score(p) == best]
    return winners[0] if len(winners) == 1 else None


def read_active_states(
    state_dir: Path, now: Optional[float] = None, active_ttl: float = 900.0
) -> List[Tuple[str, float]]:
    current = time.time() if now is None else now
    active: List[Tuple[str, float]] = []
    if not state_dir.exists():
        return active
    for path in state_dir.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            state = record["state"]
            updated_at = float(record["updated_at"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            continue
        if state not in VALID_STATES:
            continue
        age = current - updated_at
        if age < -60 or age > active_ttl:
            continue
        active.append((state, updated_at))
    return active


def aggregate_state(active: Iterable[Tuple[str, float]]) -> str:
    entries = list(active)
    if not entries:
        return "idle"
    # A recent Stop event writes idle for that session; concurrent active
    # sessions still win through priority.
    return max(entries, key=lambda item: (STATE_PRIORITY[item[0]], item[1]))[0]


class ArduinoLink:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.board = serial.Serial(port, baud, timeout=0.25, write_timeout=1.0)
        time.sleep(2.1)
        self.board.reset_input_buffer()
        self._exchange("ping", "pong")

    def close(self) -> None:
        self.board.close()

    def _exchange(self, command: str, expected: str) -> str:
        self.board.write((command + "\n").encode("ascii"))
        self.board.flush()
        deadline = time.monotonic() + 2.0
        received: List[str] = []
        while time.monotonic() < deadline:
            line = self.board.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            received.append(line)
            if line == expected or line.startswith(expected):
                return line
        raise OSError(
            "Arduino did not acknowledge {!r}; received {}".format(command, received)
        )

    def send_state(self, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError("invalid state: {}".format(state))
        self._exchange(state, "OK " + state.upper())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuously mirror Codex lifecycle hooks to Codex Pet."
    )
    parser.add_argument("--port", default="auto", help="serial port or 'auto'")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--poll", type=float, default=0.25)
    parser.add_argument("--active-ttl", type=float, default=900.0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    stopped = False

    def request_stop(_signum, _frame) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    link: Optional[ArduinoLink] = None
    connected_port: Optional[str] = None
    desired: Optional[str] = None
    sent: Optional[str] = None
    next_connect_at = 0.0

    while not stopped:
        desired = aggregate_state(
            read_active_states(args.state_dir, active_ttl=args.active_ttl)
        )

        if args.dry_run:
            if desired != sent:
                print(desired, flush=True)
                sent = desired
            if args.once:
                break
            time.sleep(args.poll)
            continue

        if link is None and time.monotonic() >= next_connect_at:
            selected = choose_port(args.port)
            if selected:
                try:
                    link = ArduinoLink(selected, args.baud)
                    connected_port = selected
                    sent = None
                    print("Connected to {}".format(selected), flush=True)
                except (OSError, serial.SerialException) as exc:
                    print("Codex Pet connection warning: {}".format(exc), file=sys.stderr)
                    link = None
                    next_connect_at = time.monotonic() + 2.0
            else:
                next_connect_at = time.monotonic() + 2.0

        if link is not None and desired != sent:
            try:
                link.send_state(desired)
                sent = desired
                print("State: {}".format(desired), flush=True)
            except (OSError, serial.SerialException) as exc:
                print("Codex Pet serial warning: {}".format(exc), file=sys.stderr)
                link.close()
                link = None
                connected_port = None
                next_connect_at = time.monotonic() + 2.0

        if args.once:
            break
        time.sleep(args.poll)

    if link is not None:
        link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
