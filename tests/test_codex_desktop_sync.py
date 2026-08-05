#!/usr/bin/env python3
"""Tests for Codex lifecycle state mapping and Serial synchronization."""

import importlib.util
import io
import json
import http.client
import stat
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
device = load("codex_pet_device_tests", "mac/codex_pet_device.py")


def fake_port(device: str, description: str) -> ListPortInfo:
    port = ListPortInfo(device)
    port.description = description
    return port


def fake_generic_espressif_port(device: str) -> ListPortInfo:
    port = fake_port(device, "USB JTAG/serial debug unit")
    port.manufacturer = "Espressif"
    port.vid = 0x303A
    return port


def fake_pinned_p4(
    path: str = "/dev/cu.usbmodem3101",
    serial_number: str = "A1B2C3D4E5F6",
) -> ListPortInfo:
    port = fake_generic_espressif_port(path)
    port.pid = 0x1001
    port.serial_number = serial_number
    return port


def hook_record_path(state_dir: Path, digit: str) -> Path:
    return state_dir / ((digit * 24) + ".json")


def write_record(path: Path, state: str, updated_at: float) -> None:
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "state": state,
                "event": "UserPromptSubmit",
                "updated_at": updated_at,
            }
        ),
        encoding="utf-8",
    )


class HookTests(unittest.TestCase):
    def test_default_state_dir_contract_is_shared(self) -> None:
        expected = Path(
            "/Users/example/Library/Application Support/CodexPet/sessions"
        )
        for module in (hook, daemon):
            with self.subTest(module=module.__name__), patch.dict(
                module.os.environ, {}, clear=True
            ), patch.object(module.Path, "home", return_value=Path("/Users/example")):
                self.assertEqual(module.default_state_dir(), expected)

    def test_state_dir_override_contract_is_shared(self) -> None:
        expected = Path("/private/tmp/codex-pet-state")
        for module in (hook, daemon):
            with self.subTest(module=module.__name__), patch.dict(
                module.os.environ,
                {"CODEX_PET_STATE_DIR": str(expected)},
                clear=True,
            ):
                self.assertEqual(module.default_state_dir(), expected)

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
            active_path = hook_record_path(state_dir, "a")
            stale_path = hook_record_path(state_dir, "b")
            invalid_state_path = hook_record_path(state_dir, "c")
            future_path = hook_record_path(state_dir, "d")
            write_record(active_path, "running", 99.0)
            write_record(stale_path, "review", 1.0)
            write_record(invalid_state_path, "secret", 99.0)
            write_record(future_path, "waiting", 1000.0)

            active = daemon.read_active_states(
                state_dir, now=100.0, active_ttl=10.0
            )

            self.assertEqual(active, [("running", 99.0)])
            self.assertTrue(active_path.exists())
            for pruned in (
                stale_path,
                invalid_state_path,
                future_path,
            ):
                with self.subTest(path=pruned.name):
                    self.assertFalse(pruned.exists())

    def test_transient_read_error_preserves_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = hook_record_path(Path(temporary), "a")
            write_record(path, "running", 99.0)
            with patch.object(Path, "read_text", side_effect=OSError("busy")):
                active = daemon.read_active_states(
                    path.parent, now=100.0, active_ttl=10.0
                )

            self.assertEqual(active, [])
            self.assertTrue(path.exists())

    def test_transient_unlink_error_is_nonfatal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = hook_record_path(Path(temporary), "a")
            write_record(path, "running", 1.0)
            with patch.object(Path, "unlink", side_effect=OSError("busy")):
                active = daemon.read_active_states(
                    path.parent, now=100.0, active_ttl=10.0
                )

            self.assertEqual(active, [])
            self.assertTrue(path.exists())

    def test_unrelated_json_files_are_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state_dir = Path(temporary)
            unrelated = state_dir / "settings.json"
            malformed_candidate = hook_record_path(state_dir, "a")
            wrong_contract = hook_record_path(state_dir, "b")
            unrelated.write_text('{"theme":"dark"}', encoding="utf-8")
            malformed_candidate.write_text("{", encoding="utf-8")
            wrong_contract.write_text(
                json.dumps({"version": 1, "state": "running", "updated_at": 1}),
                encoding="utf-8",
            )

            self.assertEqual(
                daemon.read_active_states(state_dir, now=100.0, active_ttl=10.0),
                [],
            )

            self.assertTrue(unrelated.exists())
            self.assertTrue(malformed_candidate.exists())
            self.assertTrue(wrong_contract.exists())


class ManualBridgeTests(unittest.TestCase):
    def test_state_normalization(self) -> None:
        self.assertEqual(bridge.normalise_state(" REVIEW \n"), "review")
        with self.assertRaisesRegex(ValueError, "invalid state"):
            bridge.normalise_state("sleeping")

    def test_port_helpers(self) -> None:
        unsupported = fake_port("/dev/cu.usbmodem1", "ESP32-C6 USB JTAG")
        unsupported.vid = 0x303A
        unsupported.pid = 0x1001
        esp32_p4 = fake_port("/dev/cu.usbmodem2101", "ESP32-P4 USB JTAG/serial debug unit")
        esp32_p4.vid = 0x303A
        esp32_p4.pid = 0x1001
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")
        generic_esp = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        c6 = fake_port("/dev/cu.usbmodem4101", "ESP32-C6 USB JTAG/serial debug unit")
        self.assertEqual(bridge.board_score(unsupported), 0)
        self.assertGreater(bridge.board_score(esp32_p4), bridge.board_score(adapter))
        self.assertEqual(bridge.board_score(generic_esp), 0)
        self.assertEqual(bridge.board_score(c6), 0)
        self.assertIn("VID:PID=303A:1001", bridge.port_description(esp32_p4))
        with patch.object(
            bridge, "detected_ports", return_value=[adapter, generic_esp, esp32_p4]
        ):
            self.assertEqual(bridge.choose_port("auto"), esp32_p4.device)
            self.assertEqual(bridge.choose_port(esp32_p4.device), esp32_p4.device)
            with self.assertRaisesRegex(SystemExit, "not an identifiable"):
                bridge.choose_port(adapter.device)
            with self.assertRaisesRegex(SystemExit, "generic.*rejected"):
                bridge.choose_port(generic_esp.device)
        second_p4 = fake_port(
            "/dev/cu.usbmodem2201", "JC4880P443C-I-W ESP32-P4"
        )
        with patch.object(bridge, "detected_ports", return_value=[second_p4, esp32_p4]):
            with self.assertRaisesRegex(SystemExit, "will not guess"):
                bridge.choose_port("auto")

    def test_auto_port_rejects_single_generic_espressif_candidate(self) -> None:
        generic = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        with patch.object(bridge, "detected_ports", return_value=[generic]):
            with self.assertRaisesRegex(SystemExit, "No identifiable"):
                bridge.choose_port("auto")

    def test_auto_port_rejects_generic_espressif_candidates(self) -> None:
        first = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        second = fake_generic_espressif_port("/dev/cu.usbmodem4101")
        with patch.object(bridge, "detected_ports", return_value=[first, second]):
            with self.assertRaisesRegex(SystemExit, "No identifiable"):
                bridge.choose_port("auto")

    def test_auto_port_excludes_generic_usb_serial_adapter(self) -> None:
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")
        adapter.manufacturer = "FTDI"
        with patch.object(bridge, "detected_ports", return_value=[adapter]):
            with self.assertRaisesRegex(SystemExit, "No identifiable"):
                bridge.choose_port("auto")

    def test_only_macos_outbound_serial_ports_are_discovered(self) -> None:
        callout = fake_port("/dev/cu.usbmodem2101", "ESP32-P4")
        inbound = fake_port("/dev/tty.usbmodem2101", "ESP32-P4")
        with patch.object(bridge.list_ports, "comports", return_value=[inbound, callout]):
            self.assertEqual(
                [port.device for port in bridge.detected_ports()], [callout.device]
            )

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
                    bridge,
                    "detected_ports",
                    return_value=[fake_port("/dev/cu.test", "ESP32-P4")],
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
        ), patch.object(
            bridge,
            "detected_ports",
            return_value=[fake_port("/dev/cu.test", "ESP32-P4")],
        ), patch.object(
            bridge.serial, "Serial", return_value=board
        ) as serial_open, patch.object(bridge.time, "sleep"), patch.object(
            bridge.time, "monotonic", side_effect=lambda: next(ticks) * 0.3
        ):
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(bridge.main(), 0)

        self.assertEqual(board.writes, [b"ping\n", b"running\n"])
        self.assertTrue(serial_open.call_args.kwargs["exclusive"])

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
            bridge,
            "detected_ports",
            return_value=[fake_port("/dev/cu.test", "ESP32-P4")],
        ), patch.object(
            bridge.serial,
            "Serial",
            side_effect=bridge.serial.SerialException("busy"),
        ):
            stderr = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                self.assertEqual(bridge.main(), 1)

        self.assertIn("Serial error: busy", stderr.getvalue())

    def test_baud_must_be_positive_and_bounded(self) -> None:
        self.assertEqual(bridge.valid_baud("115200"), 115200)
        for raw in ("0", "-1", str(bridge.MAX_BAUD + 1), "1.5"):
            with self.subTest(raw=raw), self.assertRaises(
                bridge.argparse.ArgumentTypeError
            ):
                bridge.valid_baud(raw)

    def test_pinned_identity_is_revalidated_after_open_before_handshake(self) -> None:
        selected = fake_pinned_p4()
        changed = fake_pinned_p4(serial_number="001122334455")
        board = FakeBoard()
        with patch.object(
            bridge.sys,
            "argv",
            [
                "codex_pet_bridge.py",
                "--port",
                selected.device,
                "--p4-usb-serial",
                "a1:b2:c3:d4:e5:f6",
                "--state",
                "running",
            ],
        ), patch.object(
            bridge, "detected_ports", side_effect=[[selected], [changed]]
        ), patch.object(
            bridge.serial, "Serial", return_value=board
        ), patch.object(bridge.time, "sleep"), redirect_stdout(
            io.StringIO()
        ), redirect_stderr(io.StringIO()):
            self.assertEqual(bridge.main(), 1)

        self.assertEqual(board.writes, [])
        self.assertTrue(board.closed)


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
    def test_auto_port_requires_one_unambiguous_p4(self) -> None:
        first = fake_port(
            "/dev/cu.usbmodem2101", "ESP32-P4 USB JTAG/serial debug unit"
        )
        second = fake_port("/dev/cu.usbmodem2201", "JC4880P443C-I-W ESP32-P4")
        unsupported = fake_port("/dev/cu.usbmodem1", "ESP32-C6 USB JTAG")
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")

        with patch.object(daemon, "detected_ports", return_value=[first]):
            self.assertEqual(daemon.choose_port("auto"), first.device)
            self.assertEqual(daemon.choose_port(first.device), first.device)
        with patch.object(daemon, "detected_ports", return_value=[adapter]):
            self.assertIsNone(daemon.choose_port("auto"))
            self.assertIsNone(daemon.choose_port(adapter.device))
        with patch.object(daemon, "detected_ports", return_value=[first, second]):
            self.assertIsNone(daemon.choose_port("auto"))
        with patch.object(daemon, "detected_ports", return_value=[unsupported, first]):
            self.assertEqual(daemon.choose_port("auto"), first.device)
        generic = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        with patch.object(daemon, "detected_ports", return_value=[generic, first]):
            self.assertEqual(daemon.choose_port("auto"), first.device)

    def test_auto_port_rejects_single_generic_espressif_candidate(self) -> None:
        generic = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        with patch.object(daemon, "detected_ports", return_value=[generic]):
            self.assertIsNone(daemon.choose_port("auto"))
            self.assertIsNone(daemon.choose_port(generic.device))

    def test_auto_port_rejects_generic_espressif_candidates(self) -> None:
        first = fake_generic_espressif_port("/dev/cu.usbmodem3101")
        second = fake_generic_espressif_port("/dev/cu.usbmodem4101")
        with patch.object(daemon, "detected_ports", return_value=[first, second]):
            self.assertIsNone(daemon.choose_port("auto"))

    def test_auto_port_excludes_generic_usb_serial_adapter(self) -> None:
        adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")
        adapter.manufacturer = "FTDI"
        with patch.object(daemon, "detected_ports", return_value=[adapter]):
            self.assertIsNone(daemon.choose_port("auto"))

    def test_missing_port_warning_is_throttled(self) -> None:
        self.assertTrue(daemon.should_warn_port(0.0, 0.0))
        self.assertFalse(daemon.should_warn_port(29.99, 30.0))
        self.assertTrue(daemon.should_warn_port(30.0, 30.0))

    def test_exclusive_serial_lock_failure_is_reported_clearly(self) -> None:
        error = daemon.serial.SerialException(
            "Could not exclusively lock port /dev/cu.test: busy"
        )
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--once",
            ],
        ), patch.object(
            daemon, "choose_port", return_value="/dev/cu.test"
        ), patch.object(
            daemon, "P4Link", side_effect=error
        ), patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(daemon.main(), 1)

        self.assertIn("Could not exclusively lock port", stderr.getvalue())

    def test_pinned_identity_change_closes_before_all_payloads(self) -> None:
        def open_link(*args, **kwargs):
            self.assertFalse(kwargs["identity_validator"]())
            raise OSError("ESP32-P4 USB identity changed after opening the port")

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--p4-usb-serial",
                "A1B2C3D4E5F6",
                "--once",
            ],
        ), patch.object(
            daemon, "choose_port", side_effect=["/dev/cu.test", None]
        ), patch.object(
            daemon, "P4Link", side_effect=open_link
        ), patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(daemon.main(), 1)


class PinnedDeviceIdentityTests(unittest.TestCase):
    PIN = "A1:B2:C3:D4:E5:F6"

    def test_complete_serial_forms_are_canonicalized(self) -> None:
        for raw in ("a1b2c3d4e5f6", "a1:b2:c3:d4:e5:f6", "a1-b2-c3-d4-e5-f6"):
            with self.subTest(raw=raw):
                self.assertEqual(device.canonicalize_usb_serial(raw), self.PIN)

    def test_malformed_partial_wildcard_mixed_and_empty_serials_are_rejected(self) -> None:
        for raw in (
            "",
            "A1B2C3D4E5",
            "A1:B2:C3:D4:E5",
            "A1:B2-C3:D4:E5:F6",
            "A1:B2:C3:D4:E5:*",
            "A1:B2:C3:D4:E5:F6:00",
            " A1B2C3D4E5F6 ",
        ):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                device.canonicalize_usb_serial(raw)

    def assert_pin_rejected(self, ports, requested="/dev/cu.usbmodem3101") -> None:
        with patch.object(daemon, "detected_ports", return_value=ports):
            self.assertIsNone(daemon.choose_port(requested, self.PIN))
        with patch.object(bridge, "detected_ports", return_value=ports):
            with self.assertRaisesRegex(SystemExit, "pinned ESP32-P4"):
                bridge.choose_port(requested, self.PIN)

    def test_correct_generic_espressif_identity_is_accepted_only_with_pin(self) -> None:
        port = fake_pinned_p4()
        with patch.object(daemon, "detected_ports", return_value=[port]):
            self.assertEqual(daemon.choose_port(port.device, self.PIN), port.device)
            self.assertIsNone(daemon.choose_port(port.device))
            self.assertIsNone(daemon.choose_port("auto"))
        with patch.object(bridge, "detected_ports", return_value=[port]):
            self.assertEqual(bridge.choose_port(port.device, self.PIN), port.device)
            with self.assertRaisesRegex(SystemExit, "generic.*rejected"):
                bridge.choose_port(port.device)

    def test_wrong_vid_or_pid_is_rejected(self) -> None:
        for attribute, value in (("vid", 0x1234), ("pid", 0x0001)):
            port = fake_pinned_p4()
            setattr(port, attribute, value)
            with self.subTest(attribute=attribute):
                self.assert_pin_rejected([port])

    def test_explicit_c6_metadata_is_rejected(self) -> None:
        for identity in (
            "ESP32-C6 USB JTAG",
            "ESP32 C6 USB JTAG",
            "ESP32_C6 USB JTAG",
            "ESP32C6 USB JTAG",
            "C6 USB JTAG",
        ):
            port = fake_pinned_p4()
            port.interface = identity
            with self.subTest(identity=identity):
                self.assert_pin_rejected([port])

    def test_vid_pid_and_pin_without_espressif_identity_are_rejected(self) -> None:
        port = fake_pinned_p4()
        port.description = "USB JTAG/serial debug unit"
        port.manufacturer = None
        self.assert_pin_rejected([port])

    def test_missing_wrong_and_malformed_port_serial_are_rejected(self) -> None:
        for serial_number in (None, "001122334455", "A1:B2:C3:D4:E5"):
            port = fake_pinned_p4()
            port.serial_number = serial_number
            with self.subTest(serial_number=serial_number):
                self.assert_pin_rejected([port])

    def test_duplicate_serial_is_rejected_across_enumerated_ports(self) -> None:
        first = fake_pinned_p4()
        second = fake_pinned_p4("/dev/cu.usbmodem4101", "a1-b2-c3-d4-e5-f6")
        self.assert_pin_rejected([first, second])

    def test_mismatched_explicit_path_is_rejected(self) -> None:
        port = fake_pinned_p4("/dev/cu.usbmodem4101")
        self.assert_pin_rejected([port])

    def test_auto_or_non_callout_port_with_pin_is_rejected_by_cli_without_echo(self) -> None:
        for module, program in (
            (bridge, "codex_pet_bridge.py"),
            (daemon, "codex_pet_daemon.py"),
        ):
            for requested in ("auto", "/dev/tty.usbmodem3101"):
                raw_pin = "a1b2c3d4e5f6"
                with self.subTest(module=module.__name__, requested=requested), patch.object(
                    module.sys,
                    "argv",
                    [program, "--port", requested, "--p4-usb-serial", raw_pin],
                ), redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                    module.main()
                self.assertNotIn(raw_pin, stderr.getvalue())

    def test_malformed_cli_pin_is_rejected_without_echo(self) -> None:
        raw_pin = "A1:B2:C3:*"
        for module, program in (
            (bridge, "codex_pet_bridge.py"),
            (daemon, "codex_pet_daemon.py"),
        ):
            with self.subTest(module=module.__name__), patch.object(
                module.sys,
                "argv",
                [
                    program,
                    "--port",
                    "/dev/cu.usbmodem3101",
                    "--p4-usb-serial",
                    raw_pin,
                ],
            ), redirect_stderr(io.StringIO()) as stderr, self.assertRaises(SystemExit):
                module.main()
            self.assertNotIn(raw_pin, stderr.getvalue())


class P4LinkTests(unittest.TestCase):
    def test_identity_revalidation_closes_before_handshake(self) -> None:
        board = FakeBoard([b"pong\n", b"CAPABILITIES clock\n"])
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ), self.assertRaisesRegex(OSError, "identity changed"):
            daemon.P4Link("/dev/cu.test", identity_validator=lambda: False)

        self.assertEqual(board.writes, [])
        self.assertEqual(board.reset_count, 0)
        self.assertTrue(board.closed)

    def test_constructor_handshake_and_state_protocol(self) -> None:
        board = FakeBoard(
            [b"boot message\n", b"pong\n", b"CAPABILITIES clock weather usage\n"]
        )
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ):
            link = daemon.P4Link("/dev/cu.test", 9600)

        board.replies.append(b"OK RUNNING\n")
        link.send_state("running")
        link.close()

        self.assertEqual(
            board.writes, [b"ping\n", b"capabilities\n", b"running\n"]
        )
        self.assertEqual(board.flush_count, 3)
        self.assertEqual(board.reset_count, 1)
        self.assertTrue(board.closed)
        self.assertEqual(link.capabilities, {"clock", "weather", "usage"})

    def test_constructor_requests_exclusive_serial_ownership(self) -> None:
        board = FakeBoard([b"pong\n", b"CAPABILITIES clock\n"])
        with patch.object(
            daemon.serial, "Serial", return_value=board
        ) as serial_open, patch.object(daemon.time, "sleep"):
            daemon.P4Link("/dev/cu.test")

        self.assertTrue(serial_open.call_args.kwargs["exclusive"])

    def test_capability_probe_enables_only_known_v2_features(self) -> None:
        board = FakeBoard(
            [b"pong\n", b"OK CAPABILITIES clock future_feature quota usage weather\n"]
        )
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ):
            link = daemon.P4Link("/dev/cu.test")

        self.assertEqual(link.capabilities, {"clock", "quota", "usage", "weather"})
        self.assertEqual(board.writes, [b"ping\n", b"capabilities\n"])

    def test_capability_timeout_is_retryable_transport_failure(self) -> None:
        link = daemon.P4Link.__new__(daemon.P4Link)
        link.board = FakeBoard()
        with patch.object(
            daemon.time, "monotonic", side_effect=[0.0, 0.1, 0.5]
        ), self.assertRaisesRegex(OSError, "capability probe timed out"):
            link._probe_capabilities(0.5)
        self.assertEqual(link.board.writes, [b"capabilities\n"])

    def test_capability_rejection_does_not_fall_back_to_legacy_mode(self) -> None:
        link = daemon.P4Link.__new__(daemon.P4Link)
        link.board = FakeBoard([b"ERR unknown\n"])
        with patch.object(
            daemon.time, "monotonic", side_effect=[0.0, 0.1]
        ), self.assertRaisesRegex(OSError, "rejected capability probe"):
            link._probe_capabilities(0.5)
        self.assertEqual(link.board.writes, [b"capabilities\n"])

    def test_clock_weather_and_usage_require_exact_ack_and_exact_writes(self) -> None:
        snapshot = daemon.WeatherSnapshot(
            29.5, 27.0, 32.0, 82, "rain", 1_722_730_800
        )
        link = daemon.P4Link.__new__(daemon.P4Link)
        usage_snapshot = daemon.UsageSnapshot(100, 200, 50, 150, 1_722_730_800)
        quota_snapshot = daemon.CodexBarQuotaSnapshot(-1, 0, 52, 1_786_173_679, 0, 1_785_853_587)
        link.board = FakeBoard(
            [b"OK CLOCK\n", b"OK WEATHER\n", b"OK USAGE\n", b"OK QUOTA\n"]
        )

        link.send_clock(1_722_730_800, 28_800)
        link.send_weather(snapshot)
        link.send_usage(usage_snapshot)
        link.send_quota(quota_snapshot)

        self.assertEqual(
            link.board.writes,
            [
                b"clock 1722730800 28800\n",
                b"weather 29.5 27 32 82 rain 1722730800\n",
                b"usage 100 200 50 150 1722730800\n",
                b"quota -1 0 52 1786173679 0 1785853587\n",
            ],
        )

    def test_clock_and_weather_reject_invalid_fields_before_write(self) -> None:
        invalid_snapshots = (
            daemon.WeatherSnapshot(float("nan"), 27, 32, 82, "rain", 1),
            daemon.WeatherSnapshot(29, 33, 32, 82, "rain", 1),
            daemon.WeatherSnapshot(29, 27, 32, 101, "rain", 1),
            daemon.WeatherSnapshot(29, 27, 32, 82, "rain later", 1),
            daemon.WeatherSnapshot(29, 27, 32, 82, "rain", -1),
        )
        link = daemon.P4Link.__new__(daemon.P4Link)
        link.board = FakeBoard()
        with self.assertRaises(ValueError):
            link.send_clock(1.5, 28_800)
        with self.assertRaises(ValueError):
            link.send_clock(daemon.MAX_UNIX_EPOCH + 1, 28_800)
        with self.assertRaises(ValueError):
            link.send_clock(1, 60_000)
        for snapshot in invalid_snapshots:
            with self.subTest(snapshot=snapshot), self.assertRaises(ValueError):
                link.send_weather(snapshot)
        self.assertEqual(link.board.writes, [])

    def test_constructor_closes_board_when_handshake_fails(self) -> None:
        board = FakeBoard()
        with patch.object(daemon.serial, "Serial", return_value=board), patch.object(
            daemon.time, "sleep"
        ), patch.object(
            daemon.time, "monotonic", side_effect=[0.0, 0.1, 2.1]
        ):
            with self.assertRaisesRegex(OSError, "did not acknowledge"):
                daemon.P4Link("/dev/cu.test")

        self.assertEqual(board.writes, [b"ping\n"])
        self.assertTrue(board.closed)

    def test_invalid_state_is_rejected_without_writing(self) -> None:
        link = daemon.P4Link.__new__(daemon.P4Link)
        link.board = FakeBoard()
        with self.assertRaisesRegex(ValueError, "invalid state"):
            link.send_state("sleeping")
        self.assertEqual(link.board.writes, [])

    def test_exchange_reports_unexpected_replies(self) -> None:
        for reply in (b"ERR unknown\n", b"pong extra\n"):
            with self.subTest(reply=reply):
                link = daemon.P4Link.__new__(daemon.P4Link)
                link.board = FakeBoard([reply])
                with patch.object(
                    daemon.time, "monotonic", side_effect=[0.0, 0.1, 2.1]
                ):
                    with self.assertRaisesRegex(
                        OSError, reply.decode().strip()
                    ):
                        link._exchange("ping", "pong")

    def test_close_error_does_not_mask_serial_recovery(self) -> None:
        link = daemon.P4Link.__new__(daemon.P4Link)
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

    def test_baud_must_be_positive_and_bounded(self) -> None:
        self.assertEqual(daemon.valid_baud("115200"), 115200)
        for raw in ("0", "-1", str(daemon.MAX_BAUD + 1), "1.5"):
            with self.subTest(raw=raw), self.assertRaises(
                daemon.argparse.ArgumentTypeError
            ):
                daemon.valid_baud(raw)


class WeatherSyncTests(unittest.TestCase):
    def test_capability_parser_accepts_both_response_shapes(self) -> None:
        self.assertEqual(
            daemon.parse_capabilities("CAPABILITIES clock weather"),
            {"clock", "weather"},
        )
        self.assertEqual(
            daemon.parse_capabilities("OK CAPABILITIES weather future"), {"weather"}
        )
        self.assertEqual(
            daemon.parse_capabilities(
                "CAPABILITIES 2 lifecycle clock weather today-v1"
            ),
            {"clock", "weather"},
        )
        self.assertEqual(daemon.parse_capabilities("OK CLOCK"), set())

    def test_usage_capability_is_recognized(self) -> None:
        self.assertEqual(
            daemon.parse_capabilities("OK CAPABILITIES usage future"), {"usage"}
        )

    def test_wmo_mapping_covers_protocol_conditions(self) -> None:
        cases = {
            0: "clear",
            2: "partly_cloudy",
            3: "cloudy",
            45: "fog",
            61: "rain",
            75: "snow",
            95: "thunder",
            999: "unknown",
            "bad": "unknown",
        }
        for code, expected in cases.items():
            with self.subTest(code=code):
                self.assertEqual(daemon.wmo_condition(code), expected)

    def test_open_meteo_response_is_parsed_deterministically(self) -> None:
        snapshot = daemon.parse_open_meteo(
            {
                "current": {
                    "time": 1_722_730_800,
                    "temperature_2m": 29.4,
                    "weather_code": 80,
                },
                "daily": {
                    "temperature_2m_min": [27.1],
                    "temperature_2m_max": [32.2],
                    "precipitation_probability_max": [82],
                    "weather_code": [80],
                },
            }
        )
        self.assertEqual(
            snapshot,
            daemon.WeatherSnapshot(29.4, 27.1, 32.2, 82, "rain", 1_722_730_800),
        )

    def test_today_forecast_condition_can_report_rain_later(self) -> None:
        snapshot = daemon.parse_open_meteo(
            {
                "current": {
                    "time": 1_722_730_800,
                    "temperature_2m": 29.4,
                    "weather_code": 3,
                },
                "daily": {
                    "temperature_2m_min": [27.1],
                    "temperature_2m_max": [32.2],
                    "precipitation_probability_max": [82],
                    "weather_code": [95],
                },
            }
        )

        self.assertEqual(snapshot.condition, "thunder")

    def test_open_meteo_request_uses_hong_kong_without_dependencies(self) -> None:
        payload = {
            "current": {
                "time": 1_722_730_800,
                "temperature_2m": 29,
                "weather_code": 0,
            },
            "daily": {
                "temperature_2m_min": [27],
                "temperature_2m_max": [32],
                "precipitation_probability_max": [10],
                "weather_code": [0],
            },
        }

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, _kind, _value, _traceback):
                return None

            def read(self):
                return json.dumps(payload).encode("utf-8")

        with patch.object(
            daemon.urllib.request, "urlopen", return_value=Response()
        ) as urlopen:
            daemon.fetch_hong_kong_weather(timeout=3.0)

        request = urlopen.call_args.args[0]
        self.assertIn("latitude=22.3193", request.full_url)
        self.assertIn("longitude=114.1694", request.full_url)
        self.assertIn("timezone=Asia%2FHong_Kong", request.full_url)
        self.assertIn("forecast_days=1", request.full_url)
        self.assertIn("timeformat=unixtime", request.full_url)
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 3.0)

    def test_weather_worker_preserves_privacy_safe_cached_snapshot(self) -> None:
        snapshot = daemon.WeatherSnapshot(29, 27, 32, 82, "rain", 1_722_730_800)
        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "weather-cache.json"
            daemon._save_weather_cache(cache, snapshot)
            fetcher = unittest.mock.Mock(side_effect=AssertionError("not started"))
            worker = daemon.WeatherWorker(cache, fetcher=fetcher)

            self.assertEqual(worker.snapshot(), snapshot)
            self.assertEqual(
                set(json.loads(cache.read_text(encoding="utf-8"))),
                {
                    "current",
                    "low",
                    "high",
                    "rain_pct",
                    "condition",
                    "updated_epoch",
                },
            )
            fetcher.assert_not_called()

    def test_weather_worker_failure_preserves_snapshot_and_uses_retry_delay(
        self,
    ) -> None:
        snapshot = daemon.WeatherSnapshot(29, 27, 32, 82, "rain", 1_722_730_800)

        class OneIterationStop:
            def __init__(self):
                self.stopped = False
                self.delays = []

            def is_set(self):
                return self.stopped

            def wait(self, delay):
                self.delays.append(delay)
                self.stopped = True

        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "weather-cache.json"
            daemon._save_weather_cache(cache, snapshot)
            worker = daemon.WeatherWorker(
                cache,
                retry_interval=60.0,
                fetcher=unittest.mock.Mock(side_effect=OSError("offline")),
            )
            stop = OneIterationStop()
            worker._stop = stop

            worker._run()

            self.assertEqual(worker.snapshot(), snapshot)
            self.assertEqual(worker.last_error(), "OSError: offline")
            self.assertEqual(stop.delays, [60.0])

    def test_weather_worker_retries_http_protocol_failures(self) -> None:
        class OneIterationStop:
            stopped = False

            def __init__(self):
                self.delays = []

            def is_set(self):
                return self.stopped

            def wait(self, delay):
                self.delays.append(delay)
                self.stopped = True

        with tempfile.TemporaryDirectory() as temporary:
            worker = daemon.WeatherWorker(
                Path(temporary) / "weather-cache.json",
                retry_interval=7.0,
                fetcher=unittest.mock.Mock(
                    side_effect=http.client.IncompleteRead(b"partial")
                ),
            )
            stop = OneIterationStop()
            worker._stop = stop

            worker._run()

            self.assertIsNone(worker.snapshot())
            self.assertIn("IncompleteRead", worker.last_error())
            self.assertEqual(stop.delays, [7.0])

    def test_weather_cache_write_is_private_atomic_and_unique(self) -> None:
        snapshot = daemon.WeatherSnapshot(29, 27, 32, 82, "rain", 200)
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary) / "cache"
            parent.mkdir(mode=0o755)
            cache = parent / "weather-cache.json"
            old_shared_temp = parent / "weather-cache.json.tmp"
            old_shared_temp.write_text("unrelated", encoding="utf-8")

            daemon._save_weather_cache(cache, snapshot)

            self.assertEqual(stat.S_IMODE(parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(cache.stat().st_mode), 0o600)
            self.assertEqual(old_shared_temp.read_text(encoding="utf-8"), "unrelated")
            self.assertEqual(
                [
                    path
                    for path in parent.iterdir()
                    if path.name.startswith(".weather-cache.json-")
                ],
                [],
            )

    def test_weather_worker_success_replaces_cache_and_uses_refresh_delay(
        self,
    ) -> None:
        original = daemon.WeatherSnapshot(28, 26, 31, 40, "cloudy", 100)
        refreshed = daemon.WeatherSnapshot(29, 27, 32, 82, "rain", 200)

        class OneIterationStop:
            def __init__(self):
                self.stopped = False
                self.delays = []

            def is_set(self):
                return self.stopped

            def wait(self, delay):
                self.delays.append(delay)
                self.stopped = True

        with tempfile.TemporaryDirectory() as temporary:
            cache = Path(temporary) / "weather-cache.json"
            daemon._save_weather_cache(cache, original)
            fetcher = unittest.mock.Mock(return_value=refreshed)
            worker = daemon.WeatherWorker(
                cache,
                refresh_interval=900.0,
                timeout=3.0,
                fetcher=fetcher,
            )
            stop = OneIterationStop()
            worker._stop = stop

            worker._run()

            self.assertEqual(worker.snapshot(), refreshed)
            self.assertIsNone(worker.last_error())
            self.assertEqual(
                json.loads(cache.read_text(encoding="utf-8")),
                {
                    "current": 29,
                    "low": 27,
                    "high": 32,
                    "rain_pct": 82,
                    "condition": "rain",
                    "updated_epoch": 200,
                },
            )
            self.assertEqual(stop.delays, [900.0])
            fetcher.assert_called_once_with(3.0)

    def test_once_with_usage_capability_refreshes_and_sends_aggregate(self) -> None:
        snapshot = daemon.UsageSnapshot(100, 200, 50, 150, 1_722_730_800)
        link = unittest.mock.Mock()
        link.capabilities = {"usage"}
        worker = unittest.mock.Mock()
        worker.refresh_if_due.return_value = snapshot
        worker.last_error.return_value = None

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--sessions-root",
                str(Path(temporary) / "codex-sessions"),
                "--port",
                "/dev/cu.test",
                "--once",
            ],
        ), patch.object(daemon, "choose_port", return_value="/dev/cu.test"), patch.object(
            daemon, "P4Link", return_value=link
        ), patch.object(
            daemon, "UsageWorker", return_value=worker
        ) as worker_class, patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(daemon.main(), 0)

        worker_class.assert_called_once_with(
            Path(temporary) / "codex-sessions",
            Path(temporary).parent / "usage-cache.json",
        )
        worker.refresh_if_due.assert_called_once_with(blocking=True)
        link.send_usage.assert_called_once_with(snapshot)
        link.close.assert_called_once_with()

    def test_no_usage_disables_local_session_scanning(self) -> None:
        link = unittest.mock.Mock()
        link.capabilities = {"usage"}
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--no-usage",
                "--once",
            ],
        ), patch.object(daemon, "choose_port", return_value="/dev/cu.test"), patch.object(
            daemon, "P4Link", return_value=link
        ), patch.object(daemon, "UsageWorker") as worker_class, patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(daemon.main(), 0)

        worker_class.assert_not_called()
        link.send_usage.assert_not_called()

    def test_codexbar_quota_is_preferred_over_local_usage(self) -> None:
        snapshot = daemon.CodexBarQuotaSnapshot(-1, 0, 52, 1000, 0, 900)
        link = unittest.mock.Mock()
        link.capabilities = {"quota", "usage"}
        worker = unittest.mock.Mock()
        worker.refresh_if_due.return_value = snapshot
        worker.last_error.return_value = None

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--once",
            ],
        ), patch.object(daemon, "choose_port", return_value="/dev/cu.test"), patch.object(
            daemon, "P4Link", return_value=link
        ), patch.object(
            daemon, "CodexBarQuotaWorker", return_value=worker
        ) as worker_class, patch.object(
            daemon, "UsageWorker"
        ) as local_worker_class, patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(daemon.main(), 0)

        worker_class.assert_called_once_with(
            Path(temporary).parent / "codexbar-quota-cache.json"
        )
        local_worker_class.assert_not_called()
        worker.refresh_if_due.assert_called_once_with(blocking=True)
        link.send_quota.assert_called_once_with(snapshot)
        link.send_usage.assert_not_called()
        link.close.assert_called_once_with()

    def test_once_with_v2_link_sends_lifecycle_clock_and_weather(self) -> None:
        snapshot = daemon.WeatherSnapshot(29.5, 27.0, 32.0, 82, "rain", 200)
        link = unittest.mock.Mock()
        link.capabilities = {"weather", "clock"}
        worker = unittest.mock.Mock()
        worker.snapshot.return_value = snapshot
        worker.last_error.return_value = None

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--once",
            ],
        ), patch.object(daemon, "choose_port", return_value="/dev/cu.test"), patch.object(
            daemon, "P4Link", return_value=link
        ), patch.object(
            daemon, "WeatherWorker", return_value=worker
        ), patch.object(
            daemon.signal, "signal"
        ), patch.object(
            daemon.time, "time", return_value=1_722_730_800
        ), patch.object(
            daemon, "local_utc_offset_seconds", return_value=28_800
        ), redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()):
            self.assertEqual(daemon.main(), 0)

        link.send_state.assert_called_once_with("idle")
        link.send_clock.assert_called_once_with(1_722_730_800, 28_800)
        link.send_weather.assert_called_once_with(snapshot)
        worker.start.assert_called_once_with()
        worker.stop.assert_called_once_with()
        self.assertIn(
            "Connected to /dev/cu.test [clock, weather]", stdout.getvalue()
        )
        link.close.assert_called_once_with()

    def test_weather_worker_error_is_reported_by_daemon_loop(self) -> None:
        link = unittest.mock.Mock()
        link.capabilities = {"weather"}
        worker = unittest.mock.Mock()
        worker.snapshot.return_value = None
        worker.last_error.return_value = "OSError: offline"

        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--port",
                "/dev/cu.test",
                "--once",
            ],
        ), patch.object(daemon, "choose_port", return_value="/dev/cu.test"), patch.object(
            daemon, "P4Link", return_value=link
        ), patch.object(daemon, "WeatherWorker", return_value=worker), patch.object(
            daemon.signal, "signal"
        ), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as stderr:
            self.assertEqual(daemon.main(), 0)

        self.assertIn(
            "Codex Pet weather warning: OSError: offline", stderr.getvalue()
        )
        worker.start.assert_called_once_with()
        worker.stop.assert_called_once_with()

    def test_dry_run_never_starts_weather_or_network(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            daemon.sys,
            "argv",
            [
                "codex_pet_daemon.py",
                "--state-dir",
                temporary,
                "--dry-run",
                "--once",
            ],
        ), patch.object(daemon, "WeatherWorker") as worker, patch.object(
            daemon.urllib.request, "urlopen"
        ) as urlopen, redirect_stdout(io.StringIO()):
            self.assertEqual(daemon.main(), 0)

        worker.assert_not_called()
        urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
