#!/usr/bin/env python3
"""Tests for privacy-safe local Codex token usage aggregation."""

import importlib.util
import json
import os
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load {}".format(relative))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


usage = load("codex_pet_usage_tests", "mac/codex_pet_usage.py")
HK = timezone(timedelta(hours=8))


def token_event(timestamp, total, last, cached, input_tokens, **private):
    record = {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {"total_tokens": total},
                "last_token_usage": {
                    "total_tokens": last,
                    "cached_input_tokens": cached,
                    "input_tokens": input_tokens,
                },
            },
        },
    }
    record.update(private)
    return record


def write_session(root: Path, directory_day: datetime, name: str, records) -> Path:
    directory = root / directory_day.strftime("%Y/%m/%d")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(
        "\n".join(
            json.dumps(record) if not isinstance(record, str) else record
            for record in records
        ),
        encoding="utf-8",
    )
    return path


class UsageAggregationTests(unittest.TestCase):
    def test_today_sums_deltas_and_newest_event_sets_latest_session_total(self):
        now = datetime(2026, 8, 4, 12, 0, tzinfo=HK)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_session(
                root,
                now,
                "one.jsonl",
                [
                    token_event("2026-08-04T01:00:00Z", 100, 100, 30, 80),
                    token_event("2026-08-04T02:00:00Z", 150, 50, 20, 40),
                ],
            )
            write_session(
                root,
                now,
                "two.jsonl",
                [token_event("2026-08-04T03:00:00Z", 40, 40, 5, 30)],
            )

            snapshot = usage.collect_usage(root, now)

        self.assertEqual(snapshot.latest_session_tokens, 40)
        self.assertEqual(snapshot.today_tokens, 190)
        self.assertEqual(snapshot.today_cached_input_tokens, 55)
        self.assertEqual(snapshot.today_input_tokens, 150)
        self.assertEqual(snapshot.updated_epoch, int(now.timestamp()))

    def test_yesterday_directory_is_scanned_for_session_crossing_midnight(self):
        now = datetime(2026, 8, 4, 1, 0, tzinfo=HK)
        yesterday = now - timedelta(days=1)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_session(
                root,
                yesterday,
                "crossing.jsonl",
                [
                    token_event("2026-08-03T15:59:00Z", 10, 10, 2, 8),
                    token_event("2026-08-03T16:01:00Z", 30, 20, 7, 15),
                ],
            )

            snapshot = usage.collect_usage(root, now)

        self.assertEqual(snapshot.latest_session_tokens, 30)
        self.assertEqual(snapshot.today_tokens, 20)
        self.assertEqual(snapshot.today_cached_input_tokens, 7)
        self.assertEqual(snapshot.today_input_tokens, 15)

    def test_same_timestamp_burst_keeps_latest_cumulative_total(self):
        now = datetime(2026, 8, 4, 12, 0, tzinfo=HK)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_session(
                root,
                now,
                "burst.jsonl",
                [
                    token_event("2026-08-04T03:00:00.123Z", 100, 100, 10, 80),
                    token_event("2026-08-04T03:00:00.123Z", 150, 50, 20, 40),
                ],
            )

            snapshot = usage.collect_usage(root, now)

        self.assertEqual(snapshot.latest_session_tokens, 150)
        self.assertEqual(snapshot.today_tokens, 150)

    def test_recently_appended_session_is_found_outside_day_directories(self):
        now = datetime(2026, 8, 4, 12, 0, tzinfo=HK)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = write_session(
                root,
                now - timedelta(days=3),
                "long-running.jsonl",
                [token_event("2026-08-04T03:00:00Z", 90, 30, 5, 20)],
            )
            os.utime(path, (now.timestamp(), now.timestamp()))

            snapshot = usage.collect_usage(root, now)

        self.assertEqual(snapshot.latest_session_tokens, 90)
        self.assertEqual(snapshot.today_tokens, 30)

    def test_malformed_and_non_usage_records_are_ignored_without_exposing_content(self):
        now = datetime(2026, 8, 4, 12, 0, tzinfo=HK)
        secret = "private prompt and tool output"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_session(
                root,
                now,
                "mixed.jsonl",
                [
                    "{not json",
                    {"timestamp": "bad", "type": "event_msg", "payload": {}},
                    token_event("2026-08-04T02:00:00Z", -1, 1, 0, 1),
                    token_event(
                        "2026-08-04T03:00:00Z",
                        12,
                        12,
                        2,
                        10,
                        prompt=secret,
                        tool_output=secret,
                    ),
                ],
            )
            snapshot = usage.collect_usage(root, now)
            command = usage.build_usage_command(snapshot)

        self.assertEqual(command, "usage 12 12 2 10 1785816000")
        self.assertNotIn(secret, command)
        self.assertEqual(
            set(snapshot.__dict__),
            {
                "latest_session_tokens",
                "today_tokens",
                "today_cached_input_tokens",
                "today_input_tokens",
                "updated_epoch",
            },
        )

    def test_wire_values_reject_negative_fractional_boolean_and_overflow(self):
        invalid = (-1, 1.5, True, usage.MAX_INT64 + 1)
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                usage.build_usage_command(usage.UsageSnapshot(value, 0, 0, 0, 0))

        with self.assertRaisesRegex(ValueError, "cached input"):
            usage.build_usage_command(usage.UsageSnapshot(0, 0, 2, 1, 0))


class UsageWorkerTests(unittest.TestCase):
    def test_cache_contains_aggregate_numbers_only_and_is_loaded(self):
        snapshot = usage.UsageSnapshot(10, 20, 5, 15, 100)
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "usage.json"
            worker = usage.UsageWorker(
                Path(temporary) / "sessions",
                cache,
                collector=lambda _root, _now: snapshot,
                wall_clock=lambda: 100,
                monotonic_clock=lambda: 0,
            )
            self.assertEqual(worker.refresh_if_due(blocking=True), snapshot)
            cached = json.loads(cache.read_text(encoding="utf-8"))
            reloaded = usage.UsageWorker(Path("unused"), cache)

        self.assertEqual(set(cached), set(snapshot.__dict__))
        self.assertTrue(all(isinstance(value, int) for value in cached.values()))
        self.assertEqual(reloaded.snapshot(), snapshot)

    def test_refresh_failure_preserves_last_good_and_poll_is_minute_gated(self):
        good = usage.UsageSnapshot(10, 20, 5, 15, 100)
        calls = []
        ticks = iter((0.0, 30.0, 60.0))

        def collector(_root, _now):
            calls.append(True)
            if len(calls) == 1:
                return good
            raise OSError("busy")

        worker = usage.UsageWorker(
            Path("unused"),
            refresh_interval=1.0,
            collector=collector,
            wall_clock=lambda: 100,
            monotonic_clock=lambda: next(ticks),
        )

        self.assertEqual(worker.refresh_if_due(blocking=True), good)
        self.assertEqual(worker.refresh_if_due(), good)
        self.assertEqual(worker.refresh_if_due(blocking=True), good)
        self.assertEqual(len(calls), 2)
        self.assertEqual(worker.last_error(), "OSError: busy")

    def test_regular_refresh_runs_collection_off_the_caller_thread(self):
        started = threading.Event()
        release = threading.Event()
        snapshot = usage.UsageSnapshot(10, 20, 5, 15, 100)

        def collector(_root, _now):
            started.set()
            release.wait(timeout=2)
            return snapshot

        worker = usage.UsageWorker(
            Path("unused"),
            collector=collector,
            wall_clock=lambda: 100,
            monotonic_clock=lambda: 0,
        )

        self.assertIsNone(worker.refresh_if_due())
        self.assertTrue(started.wait(timeout=1))
        self.assertIsNone(worker.snapshot())
        release.set()
        self.assertIsNotNone(worker._refresh_thread)
        worker._refresh_thread.join(timeout=1)
        self.assertEqual(worker.snapshot(), snapshot)


if __name__ == "__main__":
    unittest.main()
