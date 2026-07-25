#!/usr/bin/env python3
"""Dependency-free tests for Codex lifecycle state mapping and aggregation."""

import importlib.util
import json
import tempfile
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
daemon = load("codex_pet_daemon", "mac/codex_pet_daemon.py")


def fake_port(device: str, description: str) -> ListPortInfo:
    port = ListPortInfo(device)
    port.description = description
    return port


def main() -> int:
    cases = {
        "SessionStart": "idle",
        "UserPromptSubmit": "running",
        "PermissionRequest": "waiting",
        "PreCompact": "review",
        "PostCompact": "review",
        "SubagentStart": "running",
        "Stop": "idle",
        "SessionEnd": "idle",
    }
    for event, expected in cases.items():
        actual = hook.event_state({"hook_event_name": event})
        assert actual == expected, (event, actual, expected)

    assert hook.event_state(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python -m pytest"},
        }
    ) == "review"
    assert hook.event_state(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "python build.py"},
        }
    ) == "running"

    with tempfile.TemporaryDirectory() as temporary:
        state_dir = Path(temporary)
        first = {"session_id": "private-session-a", "hook_event_name": "UserPromptSubmit"}
        output = hook.write_event(first, state_dir)
        assert "private-session-a" not in output.name
        record = json.loads(output.read_text(encoding="utf-8"))
        assert set(record) == {"version", "state", "event", "updated_at"}
        assert record["state"] == "running"

        active = daemon.read_active_states(state_dir, now=record["updated_at"] + 1)
        assert daemon.aggregate_state(active) == "running"

        waiting_path = state_dir / "another.json"
        waiting_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "state": "waiting",
                    "event": "PermissionRequest",
                    "updated_at": record["updated_at"] + 0.5,
                }
            ),
            encoding="utf-8",
        )
        active = daemon.read_active_states(state_dir, now=record["updated_at"] + 1)
        assert daemon.aggregate_state(active) == "waiting"
        assert daemon.aggregate_state([]) == "idle"
        assert daemon.read_active_states(
            state_dir, now=record["updated_at"] + 1000, active_ttl=10
        ) == []

    uno = fake_port("/dev/cu.usbmodem1", "Arduino UNO")
    adapter = fake_port("/dev/cu.usbserial-1", "USB Serial")
    with patch.object(daemon, "detected_ports", return_value=[adapter, uno]):
        assert daemon.choose_port("auto") == "/dev/cu.usbmodem1"
    with patch.object(daemon, "detected_ports", return_value=[adapter]):
        assert daemon.choose_port("auto") is None

    print("CODEX DESKTOP SYNC TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
