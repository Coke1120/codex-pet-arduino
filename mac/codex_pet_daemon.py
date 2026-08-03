#!/usr/bin/env python3
"""Persistent cross-platform Codex lifecycle and board Serial bridge."""

import argparse
import json
import math
import os
import signal
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional, Set, Tuple

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
KNOWN_CAPABILITIES = frozenset(("clock", "weather"))
WEATHER_CONDITIONS = frozenset(
    (
        "clear",
        "partly_cloudy",
        "cloudy",
        "fog",
        "rain",
        "snow",
        "thunder",
        "unknown",
    )
)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
MAX_UNIX_EPOCH = 253_402_250_399


def positive_float(raw: str) -> float:
    value = float(raw)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError("expected a positive finite number")
    return value


def parse_capabilities(line: str) -> Set[str]:
    """Parse a v2 capability response without enabling unknown extensions."""
    parts = line.strip().lower().split()
    if parts[:2] == ["ok", "capabilities"]:
        names = parts[2:]
    elif parts[:1] == ["capabilities"]:
        names = parts[1:]
    else:
        return set()
    return set(names).intersection(KNOWN_CAPABILITIES)


def _validated_epoch(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError("{} must be an integer Unix epoch".format(name))
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("{} must be an integer Unix epoch".format(name)) from exc
    if converted != value or converted < 0 or converted > MAX_UNIX_EPOCH:
        raise ValueError(
            "{} must be an integer Unix epoch between 0 and {}".format(
                name, MAX_UNIX_EPOCH
            )
        )
    return converted


def _validated_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError("{} must be an integer".format(name))
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("{} must be an integer".format(name)) from exc
    if converted != value or not minimum <= converted <= maximum:
        raise ValueError(
            "{} must be an integer between {} and {}".format(name, minimum, maximum)
        )
    return converted


def build_clock_command(unix_epoch: Any, utc_offset_seconds: Any) -> str:
    epoch = _validated_epoch(unix_epoch, "unix_epoch")
    offset = _validated_integer(
        utc_offset_seconds, "utc_offset_seconds", -50_400, 50_400
    )
    return "clock {} {}".format(epoch, offset)


def _temperature_text(value: Any, name: str) -> str:
    try:
        converted = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("{} must be numeric".format(name)) from exc
    if not math.isfinite(converted) or not -100.0 <= converted <= 100.0:
        raise ValueError("{} must be finite and between -100 and 100".format(name))
    return ("{:.1f}".format(converted)).rstrip("0").rstrip(".")


@dataclass(frozen=True)
class WeatherSnapshot:
    current: float
    low: float
    high: float
    rain_pct: int
    condition: str
    updated_epoch: int


def build_weather_command(snapshot: WeatherSnapshot) -> str:
    if not isinstance(snapshot, WeatherSnapshot):
        raise ValueError("snapshot must be a WeatherSnapshot")
    current = _temperature_text(snapshot.current, "current")
    low = _temperature_text(snapshot.low, "low")
    high = _temperature_text(snapshot.high, "high")
    if float(snapshot.low) > float(snapshot.high):
        raise ValueError("low must not exceed high")
    rain_pct = _validated_integer(snapshot.rain_pct, "rain_pct", 0, 100)
    condition = str(snapshot.condition).strip().lower()
    if condition not in WEATHER_CONDITIONS:
        raise ValueError("invalid weather condition: {}".format(snapshot.condition))
    updated_epoch = _validated_epoch(snapshot.updated_epoch, "updated_epoch")
    return "weather {} {} {} {} {} {}".format(
        current, low, high, rain_pct, condition, updated_epoch
    )


def wmo_condition(code: Any) -> str:
    try:
        value = int(code)
    except (TypeError, ValueError, OverflowError):
        return "unknown"
    if value != code:
        return "unknown"
    if value == 0:
        return "clear"
    if value in (1, 2):
        return "partly_cloudy"
    if value == 3:
        return "cloudy"
    if value in (45, 48):
        return "fog"
    if value in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "rain"
    if value in (71, 73, 75, 77, 85, 86):
        return "snow"
    if value in (95, 96, 99):
        return "thunder"
    return "unknown"


def parse_open_meteo(payload: Any) -> WeatherSnapshot:
    if not isinstance(payload, dict):
        raise ValueError("Open-Meteo response must be an object")
    try:
        current = payload["current"]
        daily = payload["daily"]
        rain_pct = _validated_integer(
            daily["precipitation_probability_max"][0], "rain_pct", 0, 100
        )
        updated_epoch = _validated_epoch(current["time"], "updated_epoch")
        forecast_condition = wmo_condition(daily["weather_code"][0])
        if forecast_condition == "unknown":
            forecast_condition = wmo_condition(current["weather_code"])
        snapshot = WeatherSnapshot(
            current=float(current["temperature_2m"]),
            low=float(daily["temperature_2m_min"][0]),
            high=float(daily["temperature_2m_max"][0]),
            rain_pct=rain_pct,
            condition=forecast_condition,
            updated_epoch=updated_epoch,
        )
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError("incomplete Open-Meteo response") from exc
    # Reuse command validation as the single protocol boundary.
    build_weather_command(snapshot)
    return snapshot


def fetch_hong_kong_weather(timeout: float = 10.0) -> WeatherSnapshot:
    query = urllib.parse.urlencode(
        {
            "latitude": "22.3193",
            "longitude": "114.1694",
            "current": "temperature_2m,weather_code",
            "daily": (
                "temperature_2m_max,temperature_2m_min,"
                "precipitation_probability_max,weather_code"
            ),
            "timezone": "Asia/Hong_Kong",
            "forecast_days": "1",
            "timeformat": "unixtime",
        }
    )
    request = urllib.request.Request(
        OPEN_METEO_URL + "?" + query,
        headers={"User-Agent": "Codex-Pet/2 weather-sync"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return parse_open_meteo(payload)


def _load_weather_cache(path: Path) -> Optional[WeatherSnapshot]:
    try:
        snapshot = WeatherSnapshot(**json.loads(path.read_text(encoding="utf-8")))
        build_weather_command(snapshot)
        return snapshot
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_weather_cache(path: Path, snapshot: WeatherSnapshot) -> None:
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_text(json.dumps(asdict(snapshot)), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        try:
            temporary.unlink()
        except OSError:
            pass


class WeatherWorker:
    """Fetch weather off-thread; Serial remains owned by the daemon loop."""

    def __init__(
        self,
        cache_path: Path,
        refresh_interval: float = 900.0,
        retry_interval: float = 60.0,
        timeout: float = 10.0,
        fetcher: Callable[[float], WeatherSnapshot] = fetch_hong_kong_weather,
    ) -> None:
        self.cache_path = cache_path
        self.refresh_interval = refresh_interval
        self.retry_interval = retry_interval
        self.timeout = timeout
        self.fetcher = fetcher
        self._snapshot = _load_weather_cache(cache_path)
        self._last_error: Optional[str] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="codex-pet-weather", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=0.2)

    def snapshot(self) -> Optional[WeatherSnapshot]:
        with self._lock:
            return self._snapshot

    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                snapshot = self.fetcher(self.timeout)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                message = "{}: {}".format(type(exc).__name__, exc)
                with self._lock:
                    self._last_error = message
                delay = self.retry_interval
            else:
                with self._lock:
                    self._snapshot = snapshot
                    self._last_error = None
                _save_weather_cache(self.cache_path, snapshot)
                delay = self.refresh_interval
            self._stop.wait(delay)


def local_utc_offset_seconds(timestamp: Optional[float] = None) -> int:
    instant = datetime.fromtimestamp(
        time.time() if timestamp is None else timestamp
    ).astimezone()
    offset = instant.utcoffset()
    return 0 if offset is None else int(offset.total_seconds())


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


def board_score(port: ListPortInfo) -> int:
    text = " ".join(
        str(value or "")
        for value in (port.description, port.manufacturer, port.product, port.interface)
    ).lower()
    score = 0
    if "arduino" in text:
        score += 100
    if "uno" in text:
        score += 50
    if "esp32-p4" in text or "esp32p4" in text or "jc4880p443c" in text:
        score += 150
    if port.device.startswith("/dev/cu.usbmodem"):
        score += 10
    if port.device.upper().startswith("COM") and port.vid is not None:
        score += 10
    return score


def arduino_score(port: ListPortInfo) -> int:
    return board_score(port)


def choose_port(requested: str) -> Optional[str]:
    if requested != "auto":
        if sys.platform == "win32":
            return requested if requested.upper().startswith("COM") else None
        return requested if Path(requested).exists() else None
    candidates = [p for p in detected_ports() if board_score(p) > 0]
    if not candidates:
        return None
    return candidates[0].device if len(candidates) == 1 else None


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
    def __init__(
        self, port: str, baud: int = 115200, capability_timeout: float = 0.5
    ) -> None:
        self.port = port
        self.capabilities: Set[str] = set()
        self.board = serial.Serial(port, baud, timeout=0.25, write_timeout=1.0)
        try:
            time.sleep(2.1)
            self.board.reset_input_buffer()
            self._exchange("ping", "pong")
            self.capabilities = self._probe_capabilities(capability_timeout)
        except (OSError, serial.SerialException):
            try:
                self.board.close()
            except (OSError, serial.SerialException):
                pass
            raise

    def close(self) -> None:
        self.board.close()

    def _exchange(self, command: str, expected: str, timeout: float = 2.0) -> str:
        self.board.write((command + "\n").encode("ascii"))
        self.board.flush()
        deadline = time.monotonic() + timeout
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

    def _probe_capabilities(self, timeout: float) -> Set[str]:
        self.board.write(b"capabilities\n")
        self.board.flush()
        deadline = time.monotonic() + timeout
        received: List[str] = []
        while time.monotonic() < deadline:
            line = self.board.readline().decode("utf-8", errors="replace").strip()
            if not line:
                continue
            received.append(line)
            if line.upper().startswith("ERR"):
                return set()
            capabilities = parse_capabilities(line)
            if capabilities or line.lower() in ("capabilities", "ok capabilities"):
                return capabilities
        raise OSError(
            "Codex Pet capability probe timed out; received {}".format(received)
        )

    def send_state(self, state: str) -> None:
        if state not in VALID_STATES:
            raise ValueError("invalid state: {}".format(state))
        self._exchange(state, "OK " + state.upper())

    def send_clock(self, unix_epoch: Any, utc_offset_seconds: Any) -> None:
        self._exchange(build_clock_command(unix_epoch, utc_offset_seconds), "OK CLOCK")

    def send_weather(self, snapshot: WeatherSnapshot) -> None:
        self._exchange(build_weather_command(snapshot), "OK WEATHER")


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
    parser.add_argument("--clock-interval", type=positive_float, default=60.0)
    parser.add_argument("--weather-interval", type=positive_float, default=900.0)
    parser.add_argument("--weather-retry", type=positive_float, default=60.0)
    parser.add_argument("--weather-timeout", type=positive_float, default=10.0)
    parser.add_argument("--no-weather", action="store_true")
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
    next_clock_at = 0.0
    next_port_warning_at = 0.0
    weather_worker: Optional[WeatherWorker] = None
    sent_weather_epoch: Optional[int] = None
    reported_weather_error: Optional[str] = None

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
                    next_clock_at = 0.0
                    sent_weather_epoch = None
                    if (
                        "weather" in link.capabilities
                        and not args.no_weather
                        and weather_worker is None
                    ):
                        weather_worker = WeatherWorker(
                            args.state_dir.parent / "weather-cache.json",
                            refresh_interval=args.weather_interval,
                            retry_interval=args.weather_retry,
                            timeout=args.weather_timeout,
                        )
                        weather_worker.start()
                        reported_weather_error = None
                    negotiated = ", ".join(sorted(link.capabilities))
                    if not negotiated:
                        negotiated = "lifecycle-only"
                    print(
                        "Connected to {} [{}]".format(selected, negotiated),
                        flush=True,
                    )
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

        now = time.monotonic()
        if link is not None and "clock" in link.capabilities and now >= next_clock_at:
            try:
                epoch = int(time.time())
                link.send_clock(epoch, local_utc_offset_seconds(epoch))
                next_clock_at = time.monotonic() + args.clock_interval
            except (OSError, serial.SerialException) as exc:
                print("Codex Pet serial warning: {}".format(exc), file=sys.stderr)
                _close_quietly(link)
                link = None
                next_connect_at = time.monotonic() + 2.0

        if (
            link is not None
            and "weather" in link.capabilities
            and weather_worker is not None
        ):
            snapshot = weather_worker.snapshot()
            if snapshot is not None and snapshot.updated_epoch != sent_weather_epoch:
                try:
                    link.send_weather(snapshot)
                    sent_weather_epoch = snapshot.updated_epoch
                except (OSError, serial.SerialException) as exc:
                    print("Codex Pet serial warning: {}".format(exc), file=sys.stderr)
                    _close_quietly(link)
                    link = None
                    next_connect_at = time.monotonic() + 2.0

        if weather_worker is not None:
            weather_error = weather_worker.last_error()
            if weather_error is None:
                reported_weather_error = None
            elif weather_error != reported_weather_error:
                print(
                    "Codex Pet weather warning: {}".format(weather_error),
                    file=sys.stderr,
                )
                reported_weather_error = weather_error

        if args.once:
            break
        time.sleep(args.poll)

    if link is not None:
        _close_quietly(link)
    if weather_worker is not None:
        weather_worker.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
