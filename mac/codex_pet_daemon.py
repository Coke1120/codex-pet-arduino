#!/usr/bin/env python3
"""Persistent cross-platform Codex lifecycle and Arduino Serial bridge."""

import argparse
import json
import math
import os
import signal
import sys
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

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
PORT_WARNING_INTERVAL = 30.0


def positive_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return value


def default_state_dir() -> Path:
    override = os.environ.get("CODEX_PET_STATE_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return Path(local_app_data) / "CodexPet" / "sessions"
        return Path.home() / "AppData" / "Local" / "CodexPet" / "sessions"
    return Path.home() / "Library" / "Application Support" / "CodexPet" / "sessions"


def detected_ports() -> List[ListPortInfo]:
    def supported(device: str) -> bool:
        if sys.platform == "win32":
            return device.upper().startswith("COM")
        return device.startswith("/dev/cu.")

    return sorted(
        (p for p in list_ports.comports() if supported(p.device)),
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
    if port.device.upper().startswith("COM") and port.vid is not None:
        score += 10
    return score


def choose_port(requested: str) -> Optional[str]:
    if requested != "auto":
        if sys.platform == "win32":
            return requested if requested.upper().startswith("COM") else None
        return requested if Path(requested).exists() else None
    candidates = [p for p in detected_ports() if arduino_score(p) > 0]
    if not candidates:
        return None
    best = max(arduino_score(p) for p in candidates)
    winners = [p.device for p in candidates if arduino_score(p) == best]
    return winners[0] if len(winners) == 1 else None


def _file_identity(path: Path) -> Optional[Tuple[int, int, int, int]]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)


def _prune_if_unchanged(
    path: Path, identity: Optional[Tuple[int, int, int, int]]
) -> None:
    if identity is None or _file_identity(path) != identity:
        return
    try:
        path.unlink()
    except OSError:
        # Another hook may have replaced it, or a transient filesystem error
        # may make it readable again on the next poll.
        pass


def read_active_states(
    state_dir: Path, now: Optional[float] = None, active_ttl: float = 900.0
) -> List[Tuple[str, float]]:
    current = time.time() if now is None else now
    active: List[Tuple[str, float]] = []
    if not state_dir.exists():
        return active
    for path in state_dir.glob("*.json"):
        identity = _file_identity(path)
        if identity is None:
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            state = record["state"]
            updated_at = float(record["updated_at"])
        except OSError:
            continue
        except (ValueError, TypeError, KeyError):
            _prune_if_unchanged(path, identity)
            continue
        if state not in VALID_STATES or not math.isfinite(updated_at):
            _prune_if_unchanged(path, identity)
            continue
        age = current - updated_at
        if age < -60 or age > active_ttl:
            _prune_if_unchanged(path, identity)
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


def should_send_state(
    desired: str, sent: Optional[str], now: float, next_heartbeat_at: float
) -> bool:
    return desired != sent or now >= next_heartbeat_at


def should_warn_port(now: float, next_warning_at: float) -> bool:
    return now >= next_warning_at


class ArduinoLink:
    def __init__(self, port: str, baud: int = 115200) -> None:
        self.port = port
        self.board = serial.Serial(port, baud, timeout=0.25, write_timeout=1.0)
        try:
            time.sleep(2.1)
            self.board.reset_input_buffer()
            self._exchange("ping", "pong")
        except (OSError, serial.SerialException):
            try:
                self.board.close()
            except (OSError, serial.SerialException):
                pass
            raise

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
            if line == expected:
                return line
        raise OSError(
            "Arduino did not acknowledge {!r}; received {}".format(command, received)
        )

    def send_state(self, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError("invalid state: {}".format(state))
        self._exchange(state, "OK " + state.upper())


def _close_quietly(link: ArduinoLink) -> None:
    try:
        link.close()
    except (OSError, serial.SerialException):
        pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Continuously mirror Codex lifecycle hooks to Codex Pet."
    )
    parser.add_argument("--port", default="auto", help="serial port or 'auto'")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--poll", type=positive_float, default=0.25)
    parser.add_argument("--active-ttl", type=positive_float, default=900.0)
    parser.add_argument(
        "--heartbeat",
        type=positive_float,
        default=5.0,
        help="seconds between state resynchronizations after board resets (default: 5)",
    )
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
    desired: Optional[str] = None
    sent: Optional[str] = None
    next_connect_at = 0.0
    next_heartbeat_at = 0.0
    next_port_warning_at = 0.0

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
                    sent = None
                    next_heartbeat_at = 0.0
                    print("Connected to {}".format(selected), flush=True)
                except (OSError, serial.SerialException) as exc:
                    print("Codex Pet connection warning: {}".format(exc), file=sys.stderr)
                    link = None
                    next_connect_at = time.monotonic() + 2.0
            else:
                now = time.monotonic()
                if should_warn_port(now, next_port_warning_at):
                    print(
                        "No unique Arduino port found; reconnect or set --port "
                        "after arduino-cli board list",
                        file=sys.stderr,
                    )
                    next_port_warning_at = now + PORT_WARNING_INTERVAL
                next_connect_at = now + 2.0

        now = time.monotonic()
        if link is not None and should_send_state(
            desired, sent, now, next_heartbeat_at
        ):
            changed = desired != sent
            try:
                link.send_state(desired)
                sent = desired
                next_heartbeat_at = time.monotonic() + args.heartbeat
                if changed:
                    print("State: {}".format(desired), flush=True)
            except (OSError, serial.SerialException) as exc:
                print("Codex Pet serial warning: {}".format(exc), file=sys.stderr)
                _close_quietly(link)
                link = None
                next_connect_at = time.monotonic() + 2.0

        if args.once:
            break
        time.sleep(args.poll)

    if link is not None:
        _close_quietly(link)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
