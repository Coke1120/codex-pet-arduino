#!/usr/bin/env python3
"""Privacy-safe aggregate Codex token usage from local session JSONL files."""

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Tuple


MAX_INT64 = (1 << 63) - 1
MIN_REFRESH_INTERVAL = 60.0


def _nonnegative_int64(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError("{} must be an integer".format(name))
    try:
        converted = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("{} must be an integer".format(name)) from exc
    if converted != value or not 0 <= converted <= MAX_INT64:
        raise ValueError("{} must be between 0 and {}".format(name, MAX_INT64))
    return converted


@dataclass(frozen=True)
class UsageSnapshot:
    latest_session_tokens: int
    today_tokens: int
    today_cached_input_tokens: int
    today_input_tokens: int
    updated_epoch: int

    def validated(self) -> "UsageSnapshot":
        validated = UsageSnapshot(
            *(
                _nonnegative_int64(getattr(self, field), field)
                for field in self.__dataclass_fields__
            )
        )
        if validated.today_cached_input_tokens > validated.today_input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return validated


def build_usage_command(snapshot: UsageSnapshot) -> str:
    if not isinstance(snapshot, UsageSnapshot):
        raise ValueError("snapshot must be a UsageSnapshot")
    valid = snapshot.validated()
    return "usage {} {} {} {} {}".format(
        valid.latest_session_tokens,
        valid.today_tokens,
        valid.today_cached_input_tokens,
        valid.today_input_tokens,
        valid.updated_epoch,
    )


def _event_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _usage_values(record: Any) -> Optional[Tuple[datetime, int, int, int, int]]:
    try:
        if (
            record["type"] != "event_msg"
            or record["payload"]["type"] != "token_count"
        ):
            return None
        timestamp = _event_time(record["timestamp"])
        if timestamp is None:
            return None
        info = record["payload"]["info"]
        total = _nonnegative_int64(
            info["total_token_usage"]["total_tokens"], "total_tokens"
        )
        last = info["last_token_usage"]
        last_total = _nonnegative_int64(last["total_tokens"], "last_total_tokens")
        cached = _nonnegative_int64(
            last["cached_input_tokens"], "last_cached_input_tokens"
        )
        input_tokens = _nonnegative_int64(last["input_tokens"], "last_input_tokens")
    except (KeyError, TypeError, ValueError):
        return None
    return timestamp, total, last_total, cached, input_tokens


def _session_files(
    sessions_root: Path,
    days: Iterable[datetime],
    modified_since: Optional[float] = None,
) -> Iterable[Path]:
    seen = set()
    for day in days:
        directory = (
            sessions_root
            / day.strftime("%Y")
            / day.strftime("%m")
            / day.strftime("%d")
        )
        if directory in seen or not directory.exists():
            continue
        seen.add(directory)
        try:
            for path in directory.glob("*.jsonl"):
                seen.add(path)
                yield path
        except OSError as exc:
            raise OSError("could not scan Codex sessions") from exc

    if modified_since is None or not sessions_root.exists():
        return
    try:
        for path in sessions_root.rglob("*.jsonl"):
            if path in seen:
                continue
            try:
                recently_modified = path.stat().st_mtime >= modified_since
            except OSError as exc:
                raise OSError("could not inspect Codex sessions") from exc
            if recently_modified:
                yield path
    except OSError as exc:
        raise OSError("could not scan Codex sessions") from exc


def collect_usage(
    sessions_root: Path, now: Optional[datetime] = None
) -> UsageSnapshot:
    """Read token_count aggregates only; no transcript fields leave this function."""
    current = datetime.now().astimezone() if now is None else now
    if current.tzinfo is None:
        raise ValueError("now must include a timezone")
    local_now = current if now is not None else current.astimezone()
    local_day = local_now.date()
    newest_time: Optional[datetime] = None
    latest_session_tokens = 0
    today_tokens = 0
    today_cached = 0
    today_input = 0

    scan_days = (local_now, local_now - timedelta(days=1))
    recently_modified = (local_now - timedelta(days=2)).timestamp()
    for path in _session_files(Path(sessions_root), scan_days, recently_modified):
        try:
            with path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    if '"token_count"' not in line:
                        continue
                    try:
                        record = json.loads(line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    values = _usage_values(record)
                    if values is None:
                        continue
                    timestamp, total, last_total, cached, input_tokens = values
                    # Codex can emit a burst of cumulative counters with the
                    # same millisecond timestamp. Prefer the later/larger
                    # counter in that burst instead of freezing on its first
                    # record.
                    if (
                        newest_time is None
                        or timestamp > newest_time
                        or (
                            timestamp == newest_time
                            and total >= latest_session_tokens
                        )
                    ):
                        newest_time = timestamp
                        latest_session_tokens = total
                    if timestamp.astimezone(local_now.tzinfo).date() == local_day:
                        today_tokens += last_total
                        today_cached += cached
                        today_input += input_tokens
        except (OSError, UnicodeError) as exc:
            raise OSError("could not read Codex usage aggregates") from exc

    return UsageSnapshot(
        latest_session_tokens=latest_session_tokens,
        today_tokens=today_tokens,
        today_cached_input_tokens=today_cached,
        today_input_tokens=today_input,
        updated_epoch=int(local_now.timestamp()),
    ).validated()


def _load_cache(path: Optional[Path]) -> Optional[UsageSnapshot]:
    if path is None:
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if set(record) != set(UsageSnapshot.__dataclass_fields__):
            return None
        return UsageSnapshot(**record).validated()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _save_cache(path: Optional[Path], snapshot: UsageSnapshot) -> None:
    if path is None:
        return
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


class UsageWorker:
    """Minute-gated background refresh that preserves the last good aggregate."""

    def __init__(
        self,
        sessions_root: Path,
        cache_path: Optional[Path] = None,
        refresh_interval: float = MIN_REFRESH_INTERVAL,
        collector: Callable[[Path, Optional[datetime]], UsageSnapshot] = collect_usage,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sessions_root = Path(sessions_root)
        self.cache_path = cache_path
        self.refresh_interval = max(MIN_REFRESH_INTERVAL, refresh_interval)
        self.collector = collector
        self.wall_clock = wall_clock
        self.monotonic_clock = monotonic_clock
        self._snapshot = _load_cache(cache_path)
        self._last_error: Optional[str] = None
        self._next_refresh_at = 0.0
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None

    def snapshot(self) -> Optional[UsageSnapshot]:
        with self._lock:
            return self._snapshot

    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def _refresh(self) -> None:
        try:
            instant = datetime.fromtimestamp(self.wall_clock()).astimezone()
            snapshot = self.collector(self.sessions_root, instant).validated()
        except (OSError, TypeError, ValueError, OverflowError) as exc:
            with self._lock:
                self._last_error = "{}: {}".format(type(exc).__name__, exc)
            return
        with self._lock:
            self._snapshot = snapshot
            self._last_error = None
        _save_cache(self.cache_path, snapshot)

    def refresh_if_due(self, blocking: bool = False) -> Optional[UsageSnapshot]:
        now = self.monotonic_clock()
        with self._lock:
            if now < self._next_refresh_at:
                return self._snapshot
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return self._snapshot
            self._next_refresh_at = now + self.refresh_interval

        if blocking:
            self._refresh()
        else:
            thread = threading.Thread(
                target=self._refresh,
                name="codex-pet-usage",
                daemon=True,
            )
            with self._lock:
                self._refresh_thread = thread
            thread.start()
        return self.snapshot()
