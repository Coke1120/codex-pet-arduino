#!/usr/bin/env python3
"""Tests for Codex lifecycle state mapping and Serial synchronization."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from serial.tools.list_ports_common import ListPortInfo

ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load {}".format(relative))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hook = load("codex_pet_hook", "mac/codex_pet_hook.py")
bridge = load("codex_pet_bridge", "mac/codex_pet_bridge.py")
daemon = load("codex_pet_daemon", "mac/codex_pet_daemon.py")


def fake_port(device: str, description: str) -> ListPortInfo:
    port = ListPortInfo(device)
    port.description = description
    return port


def write_record(path: Path, state: str, updated_at: float) -> None:
    path.write_text(
        json.dumps({"version": 1, "state": state, "updated_at": updated_at}),
        encoding="utf-8",
    )


class HookTests(unittest.TestCase):
    def test_default_state_dir_is_platform_appropriate(self) -> None:
        with patch.dict(hook.os.environ, {"LOCALAPPDATA": r"C:\Users\Example\AppData\Local"}, clear=True), patch.object(hook.sys, "platform", "win32"):
            self.assertEqual(
                hook.default_state_dir(),
                Path(r"C:\Users\Example\AppData\Local") / "CodexPet" / "sessions",
            )

    def test_event_mapping(self) -> None:
        cases = {
            "SessionStart": "idle",
            "UserPromptSubmit": "running",
            "PermissionRequest": "waiting",
            "PreCompact": "review",
            "PostCompact": "review",
            "SubagentStart": "running",
            "SubagentStop": "running",
            "Stop": "idle",
            "SessionEnd": "idle",
            "UnknownEvent": "idle",
        }
        for event, expected in cases.items():
            with self.subTest(event=event):
                self.assertEqual(
                    hook.event_state({"hook_event_name": event}), expected
                )

    def test_tool_mapping_distinguishes_review_work(self) -> None:
        cases = {
            "python -m pytest": "review",
            "ruff check .": "review",
            "npm run lint": "review",
            "npm run typecheck": "review",
            "git diff --check": "review",
            "python build.py": "running",
            "git checkout main": "running",
            "echo contest": "running",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(
                    hook.event_state(
                        {
                            "hook_event_name": "PreToolUse",
                            "tool_name": "Bash",
                            "tool_input": {"command": command},
                        }
                    ),
                    expected,
                )

    def test_written_event_is_privacy_safe(self) -> None:
        payload = {
            "session_id": "private-session-a",
            "hook_event_name": "UserPromptSubmit",
            "prompt": "do not persist this",
            "cwd": "/private/worktree",
            "transcript_path": "/private/transcript.jsonl",
        }
        with tempfile.TemporaryDirectory() as temporary:
            output = hook.write_event(payload, Path(temporary))
            serialized = output.read_text(encoding="utf-8")
            record = json.loads(serialized)

        self.assertNotIn(payload["session_id"], output.name)
        self.assertEqual(
            set(record), {"version", "state", "event", "updated_at"}
        )
        self.assertEqual(record["state"], "running")
        for private_value in (
            payload["prompt"],
            payload["cwd"],
            payload["transcript_path"],
        ):
            self.assertNotIn(private_value, serialized)


class AggregationTests(unittest.TestCase):
    def test_priority_and_empty_state(self) -> None:
        active = [("running", 10.0), ("review", 9.0), ("waiting", 8.0)]
        self.assertEqual(daemon.aggregate_state(active), "waiting")
        self.assertEqual(daemon.aggregate_state([]), "idle")

    def test_active_records_are_read_and_stale_or_invalid_files_are_pruned(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            active_path = state_dir / "active.json"
            stale_path = state_dir / "stale.json"
            invalid_json_path = state_dir / "invalid-json.json"
            invalid_state_path = state_dir / "invalid-state.json"
            future_path = state_dir / "future.json"
            write_record(active_path, "running", 99.0)
            write_record(stale_path, "review", 1.0)
            invalid_json_path.write_text("{", encoding="utf-8")
            write_record(invalid_state_path, "secret", 99.0)
            write_record(future_path, "waiting", 1000.0)

            active = daemon.read_active_states(
                state_dir, now=100.0, active_ttl=10.0
            )

            self.assertEqual(active, [("running", 99.0)])
            self.assertTrue(active_path.exists())
            for pruned in (
                stale_path,
                invalid_json_path,
                invalid_state_path,
                future_path,
            ):
                with self.subTest(path=pruned.name):
                    self.assertFalse(pruned.exists())

    def test_transient_read_error_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "session.json"
            write_record(path, "running", 99.0)
            with patch.object(Path, "read_text", side_effect=OSError("busy")):
                active = daemon.read_active_states(
                    path.parent, now=100.0, active_ttl=10.0
                )

            self.assertEqual(active, [])
            self.assertTrue(path.exists())

    def test_transient_unlink_error_is_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "stale.json"
            write_record(path, "running", 1.0)
            with patch.object(Path, "unlink", side_effect=OSError("busy")):
                active = daemon.read_active_states(
                    path.parent, now=100.0, active_ttl=10.0
                )

            self.assertEqual(active, [])
            self.assertTrue(path.exists())


class ManualBridgeTests(unittest.TestCase):
    def test_state_normalization(self) -> None:
        self.assertEqual(bridge.normalise_state(" REVIEW \n"), "review")
        with self.assertRaisesRegex(ValueError, "invalid state"):
            bridge.normalise_state("sleeping")

    def test_port_helpers(self) -> None:
        uno = fake_port("/dev/cu.usbmodem1", "Arduino UNO")
        uno.vid = 0x2341
        uno.pid = 0x0043
        esp32_p4 = fake_port("/dev/cu.usbmodem2101", "ESP32-P4 USB JTAG/serial debug unit")
        esp32_p4.vid = 0x303A
        esp32_p4.pid = 0x1001
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")
        generic_esp = fake_port("/dev/cu.usbmodem3101", "USB JTAG/serial debug unit")
        c6 = fake_port("/dev/cu.usbmodem4101", "ESP32-C6 USB JTAG/serial debug unit")
        self.assertGreater(bridge.board_score(uno), bridge.board_score(adapter))
        self.assertGreater(bridge.board_score(esp32_p4), bridge.board_score(adapter))
        self.assertEqual(bridge.board_score(generic_esp), 10)
        self.assertEqual(bridge.board_score(c6), 10)
        self.assertIn("VID:PID=2341:0043", bridge.port_description(uno))
        with patch.object(bridge, "detected_ports", return_value=[adapter, esp32_p4]):
            self.assertEqual(bridge.choose_port("auto"), esp32_p4.device)
        with patch.object(bridge, "detected_ports", return_value=[uno, esp32_p4]):
            with self.assertRaisesRegex(SystemExit, "will not guess"):
                bridge.choose_port("auto")

    def test_windows_com_ports_are_discovered(self) -> None:
        com = fake_port("COM4", "Arduino UNO")
        unix = fake_port("/dev/cu.usbmodem1", "Arduino UNO")
        with patch.object(bridge.list_ports, "comports", return_value=[com, unix]), patch.object(bridge.sys, "platform", "win32"):
            self.assertEqual([port.device for port in bridge.detected_ports()], ["COM4"])

    def test_stdin_states_ignores_blank_lines(self) -> None:
        with patch.object(bridge.sys, "stdin", io.StringIO("\nrunning\n  \nidle\n")):
            self.assertEqual(list(bridge.stdin_states()), ["running\n", "idle\n"])

    def test_state_send_requires_exact_pong_handshake(self) -> None:
        for replies in ([], [b"pong extra\n"], [b"not pong\n"]):
            with self.subTest(replies=replies):
                board = FakeBoard(replies)
                ticks = iter(range(100))
                with patch.object(
                    bridge.sys,
                    "argv",
                    [
                        "codex_pet_bridge.py",
                        "--port",
                        "/dev/cu.test",
                        "--state",
                        "running",
                    ],
                ), patch.object(
                    bridge.serial, "Serial", return_value=board
                ), patch.object(
                    bridge.time, "sleep"
                ), patch.object(
                    bridge.time,
                    "monotonic",
                    side_effect=lambda: next(ticks) * 0.3,
                ):
                    with redirect_stdout(io.StringIO()), redirect_stderr(
                        io.StringIO()
                    ):
                        result = bridge.main()

                self.assertEqual(result, 1)
                self.assertEqual(board.writes, [b"ping\n"])

    def test_exact_pong_allows_state_send(self) -> None:
        board = FakeBoard([b"pong\n", b"OK RUNNING\n"])
        ticks = iter(range(100))
        with patch.object(
            bridge.sys,
            "argv",
            [
                "codex_pet_bridge.py",
                "--port",
                "/dev/cu.test",
                "--state",
                "running",
            ],
        ), patch.object(bridge.serial, "Serial", return_value=board), patch.object(
            bridge.time, "sleep"
        ), patch.object(
            bridge.time, "monotonic", side_effect=lambda: next(ticks) * 0.3
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(bridge.main(), 0)

        self.assertEqual(board.writes, [b"ping\n", b"running\n"])

    def test_serial_open_failure_is_reported_without_traceback(self) -> None:
        with patch.object(
            bridge.sys,
            "argv",
            [
                "codex_pet_bridge.py",
                "--port",
                "/dev/cu.test",
                "--state",
                "running",
            ],
        ), patch.object(
            bridge.serial,
            "Serial",
            side_effect=bridge.serial.SerialException("busy"),
        ):
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                self.assertEqual(bridge.main(), 1)

        self.assertIn("Serial error: busy", stderr.getvalue())


class FakeBoard:
    def __init__(self, replies=(), close_error=None):
        self.replies = list(replies)
        self.close_error = close_error
        self.writes = []
        self.flush_count = 0
        self.reset_count = 0
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    def flush(self) -> None:
        self.flush_count += 1

    def readline(self) -> bytes:
        return self.replies.pop(0) if self.replies else b""

    def reset_input_buffer(self) -> None:
        self.reset_count += 1

    def close(self) -> None:
        if self.close_error is not None:
            raise self.close_error
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self.close()


class DaemonPortTests(unittest.TestCase):
    def test_explicit_windows_port_does_not_require_a_filesystem_node(self) -> None:
        with patch.object(daemon.sys, "platform", "win32"):
            self.assertEqual(daemon.choose_port("COM7"), "COM7")

    def test_auto_port_requires_one_unambiguous_arduino(self) -> None:
        first = fake_port("/dev/cu.usbmodem1", "Arduino UNO")
        second = fake_port("/dev/cu.usbmodem2", "Arduino UNO")
        p4 = fake_port("/dev/cu.usbmodem2101", "ESP32-P4 USB JTAG/serial debug unit")
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")

        with patch.object(daemon, "detected_ports", return_value=[first]):
            self.assertEqual(daemon.choose_port("auto"), first.device)
        with patch.object(daemon, "detected_ports", return_value=[adapter]):
            self.assertIsNone(daemon.choose_port("auto"))
        with patch.object(daemon, "detected_ports", return_value=[first, second]):
            self.assertIsNone(daemon.choose_port("auto"))
        with patch.object(daemon, "detected_ports", return_value=[first, p4]):
            self.assertIsNone(daemon.choose_port("auto"))

    def test_missing_port_warning_is_throttled(self) -> None:
        self.assertTrue(daemon.should_warn_port(0.0, 0.0))
        self.assertFalse(daemon.should_warn_port(29.99, 30.0))
        self.assertTrue(daemon.should_warn_port(30.0, 30.0))


class ArduinoLinkTests(unittest.TestCase):
    def test_constructor_handshake_and_state_protocol(self) -> None:
        board = FakeBoard([b"boot message\n", b"pong\n"])
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ):
            link = daemon.ArduinoLink("/dev/cu.test", 9600)

        board.replies.append(b"OK RUNNING\n")
        link.send_state("running")
        link.close()

        self.assertEqual(board.writes, [b"ping\n", b"running\n"])
        self.assertEqual(board.flush_count, 2)
        self.assertEqual(board.reset_count, 1)
        self.assertTrue(board.closed)

    def test_constructor_closes_board_when_handshake_fails(self) -> None:
        board = FakeBoard()
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ), patch.object(
            daemon.time, "monotonic", side_effect=[0.0, 0.1, 2.1]
        ):
            with self.assertRaisesRegex(OSError, "did not acknowledge"):
                daemon.ArduinoLink("/dev/cu.test")

        self.assertEqual(board.writes, [b"ping\n"])
        self.assertTrue(board.closed)

    def test_invalid_state_is_rejected_without_writing(self) -> None:
        link = daemon.ArduinoLink.__new__(daemon.ArduinoLink)
        link.board = FakeBoard()
        with self.assertRaisesRegex(ValueError, "invalid state"):
            link.send_state("sleeping")
        self.assertEqual(link.board.writes, [])

    def test_exchange_reports_unexpected_replies(self) -> None:
        for reply in (b"ERR unknown\n", b"pong extra\n"):
            with self.subTest(reply=reply):
                link = daemon.ArduinoLink.__new__(daemon.ArduinoLink)
                link.board = FakeBoard([reply])
                with patch.object(
                    daemon.time, "monotonic", side_effect=[0.0, 0.1, 2.1]
                ):
                    with self.assertRaisesRegex(
                        OSError, reply.decode().strip()
                    ):
                        link._exchange("ping", "pong")

    def test_close_error_does_not_mask_serial_recovery(self) -> None:
        link = daemon.ArduinoLink.__new__(daemon.ArduinoLink)
        link.board = FakeBoard(close_error=OSError("device disappeared"))
        daemon._close_quietly(link)


class HeartbeatTests(unittest.TestCase):
    def test_state_change_is_sent_before_heartbeat(self) -> None:
        self.assertTrue(
            daemon.should_send_state("review", "running", 1.0, 100.0)
        )

    def test_unchanged_state_is_resent_on_heartbeat_after_board_reset(self) -> None:
        self.assertFalse(
            daemon.should_send_state("running", "running", 4.99, 5.0)
        )
        self.assertTrue(
            daemon.should_send_state("running", "running", 5.0, 5.0)
        )

    def test_intervals_must_be_positive_and_finite(self) -> None:
        self.assertEqual(daemon.positive_float("0.25"), 0.25)
        for raw in ("0", "-1", "nan", "inf"):
            with self.subTest(raw=raw):
                with self.assertRaises(daemon.argparse.ArgumentTypeError):
                    daemon.positive_float(raw)


if __name__ == "__main__":
    unittest.main()
