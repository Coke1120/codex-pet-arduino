#!/usr/bin/env python3
"""Privacy-safe local token aggregates and CodexBar quota snapshots."""

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Tuple


MAX_INT64 = (1 << 63) - 1
MAX_UNIX_EPOCH = 253_402_250_399
MIN_REFRESH_INTERVAL = 60.0
UNKNOWN_QUOTA = -1
CODEXBAR_CLI_CANDIDATES = (
    Path("/opt/homebrew/bin/codexbar"),
    Path("/usr/local/bin/codexbar"),
    Path("/Applications/CodexBar.app/Contents/Helpers/CodexBarCLI"),
    Path.home() / "Applications/CodexBar.app/Contents/Helpers/CodexBarCLI",
)


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


def _quota_percent(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError("{} must be numeric".format(name))
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("{} must be numeric".format(name)) from exc
    if not decimal.is_finite() or not Decimal(0) <= decimal <= Decimal(100):
        raise ValueError("{} must be between 0 and 100".format(name))
    return int((Decimal(100) - decimal).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _iso_epoch(value: Any, name: str, missing: int = 0) -> int:
    if value is None:
        return missing
    if not isinstance(value, str):
        raise ValueError("{} must be an ISO-8601 timestamp".format(name))
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("{} must be an ISO-8601 timestamp".format(name)) from exc
    if parsed.tzinfo is None:
        raise ValueError("{} must include a timezone".format(name))
    epoch = _nonnegative_int64(int(parsed.timestamp()), name)
    if epoch > MAX_UNIX_EPOCH:
        raise ValueError("{} is outside the supported range".format(name))
    return epoch


def _credit_tenths(value: Any) -> int:
    if value is None:
        return UNKNOWN_QUOTA
    if isinstance(value, bool):
        raise ValueError("credits remaining must be numeric")
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("credits remaining must be numeric") from exc
    if not decimal.is_finite() or decimal < 0:
        raise ValueError("credits remaining must be nonnegative")
    converted = int((decimal * 10).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    if converted > MAX_INT64:
        raise ValueError("credits remaining is too large")
    return converted


@dataclass(frozen=True)
class CodexBarQuotaSnapshot:
    session_remaining_percent: int
    session_reset_epoch: int
    weekly_remaining_percent: int
    weekly_reset_epoch: int
    credits_remaining_tenths: int
    updated_epoch: int

    def validated(self) -> "CodexBarQuotaSnapshot":
        for name in ("session_remaining_percent", "weekly_remaining_percent"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not -1 <= value <= 100:
                raise ValueError("{} must be -1 or between 0 and 100".format(name))
        for name in ("session_reset_epoch", "weekly_reset_epoch", "updated_epoch"):
            value = _nonnegative_int64(getattr(self, name), name)
            if value > MAX_UNIX_EPOCH:
                raise ValueError("{} is outside the supported range".format(name))
        if (
            isinstance(self.credits_remaining_tenths, bool)
            or not isinstance(self.credits_remaining_tenths, int)
            or not -1 <= self.credits_remaining_tenths <= MAX_INT64
        ):
            raise ValueError("credits_remaining_tenths must be -1 or a nonnegative integer")
        if self.session_remaining_percent < 0 and self.session_reset_epoch != 0:
            raise ValueError("missing session quota cannot have a reset time")
        if self.weekly_remaining_percent < 0 and self.weekly_reset_epoch != 0:
            raise ValueError("missing weekly quota cannot have a reset time")
        return self


def build_quota_command(snapshot: CodexBarQuotaSnapshot) -> str:
    if not isinstance(snapshot, CodexBarQuotaSnapshot):
        raise ValueError("snapshot must be a CodexBarQuotaSnapshot")
    valid = snapshot.validated()
    return "quota {} {} {} {} {} {}".format(
        valid.session_remaining_percent,
        valid.session_reset_epoch,
        valid.weekly_remaining_percent,
        valid.weekly_reset_epoch,
        valid.credits_remaining_tenths,
        valid.updated_epoch,
    )


def find_codexbar_cli() -> Optional[Path]:
    override = os.environ.get("CODEXBAR_CLI")
    candidates = ([Path(override).expanduser()] if override else []) + list(
        CODEXBAR_CLI_CANDIDATES
    )
    discovered = shutil.which("codexbar")
    if discovered:
        candidates.insert(0, Path(discovered))
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate
    return None


def parse_codexbar_quota(payload: Any) -> CodexBarQuotaSnapshot:
    records = payload if isinstance(payload, list) else [payload]
    record = next(
        (
            item
            for item in records
            if isinstance(item, dict) and item.get("provider") == "codex"
        ),
        None,
    )
    if record is None:
        raise ValueError("CodexBar output has no Codex provider")
    if record.get("error"):
        raise OSError("CodexBar could not refresh the Codex provider")
    usage = record.get("usage")
    if not isinstance(usage, dict):
        raise ValueError("CodexBar output has no usage snapshot")

    def window_values(name: str) -> Tuple[int, int]:
        window = usage.get(name)
        if window is None:
            return UNKNOWN_QUOTA, 0
        if not isinstance(window, dict):
            raise ValueError("CodexBar {} window must be an object".format(name))
        remaining = _quota_percent(window.get("usedPercent"), name + " usedPercent")
        reset_epoch = _iso_epoch(window.get("resetsAt"), name + " resetsAt")
        return remaining, reset_epoch

    session_remaining, session_reset = window_values("primary")
    weekly_remaining, weekly_reset = window_values("secondary")
    if session_remaining < 0 and weekly_remaining < 0:
        raise ValueError("CodexBar returned no quota windows")
    credits = record.get("credits")
    credits_tenths = _credit_tenths(
        credits.get("remaining") if isinstance(credits, dict) else None
    )
    return CodexBarQuotaSnapshot(
        session_remaining,
        session_reset,
        weekly_remaining,
        weekly_reset,
        credits_tenths,
        _iso_epoch(usage.get("updatedAt"), "usage updatedAt"),
    ).validated()


def collect_codexbar_quota(
    cli_path: Optional[Path] = None,
    timeout: float = 30.0,
    runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> CodexBarQuotaSnapshot:
    cli = cli_path or find_codexbar_cli()
    if cli is None:
        raise OSError("CodexBar CLI is not installed")
    command = [
        str(cli),
        "--provider",
        "codex",
        "--source",
        "oauth",
        "--format",
        "json",
        "--json-only",
    ]
    try:
        completed = runner(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise OSError("CodexBar usage probe failed") from exc
    try:
        payload = json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise OSError(
            "CodexBar usage probe returned invalid JSON (exit {})".format(
                completed.returncode
            )
        ) from exc
    if completed.returncode != 0:
        raise OSError("CodexBar usage probe failed (exit {})".format(completed.returncode))
    return parse_codexbar_quota(payload)


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
    local_now = datetime.now().astimezone() if now is None else now
    if local_now.tzinfo is None:
        raise ValueError("now must include a timezone")
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


def _save_cache(path: Optional[Path], snapshot: Any) -> None:
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


def _load_quota_cache(path: Optional[Path]) -> Optional[CodexBarQuotaSnapshot]:
    if path is None:
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if set(record) != set(CodexBarQuotaSnapshot.__dataclass_fields__):
            return None
        return CodexBarQuotaSnapshot(**record).validated()
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None


class CodexBarQuotaWorker:
    """Minute-gated CodexBar refresh that preserves the last good quota."""

    def __init__(
        self,
        cache_path: Optional[Path] = None,
        refresh_interval: float = MIN_REFRESH_INTERVAL,
        collector: Callable[[], CodexBarQuotaSnapshot] = collect_codexbar_quota,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cache_path = cache_path
        self.refresh_interval = max(MIN_REFRESH_INTERVAL, refresh_interval)
        self.collector = collector
        self.monotonic_clock = monotonic_clock
        self._snapshot = _load_quota_cache(cache_path)
        self._last_error: Optional[str] = None
        self._next_refresh_at = 0.0
        self._lock = threading.Lock()
        self._refresh_thread: Optional[threading.Thread] = None

    def snapshot(self) -> Optional[CodexBarQuotaSnapshot]:
        with self._lock:
            return self._snapshot

    def last_error(self) -> Optional[str]:
        with self._lock:
            return self._last_error

    def _refresh(self) -> None:
        try:
            snapshot = self.collector().validated()
        except (OSError, TypeError, ValueError, OverflowError) as exc:
            with self._lock:
                self._last_error = "{}: {}".format(type(exc).__name__, exc)
            return
        with self._lock:
            self._snapshot = snapshot
            self._last_error = None
        _save_cache(self.cache_path, snapshot)

    def refresh_if_due(self, blocking: bool = False) -> Optional[CodexBarQuotaSnapshot]:
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
                name="codexbar-quota",
                daemon=True,
            )
            with self._lock:
                self._refresh_thread = thread
            thread.start()
        return self.snapshot()
