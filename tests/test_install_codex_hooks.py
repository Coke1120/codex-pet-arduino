#!/usr/bin/env python3
"""Tests for the non-destructive Codex hook installer."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "install_codex_hooks", ROOT / "tools" / "install_codex_hooks.py"
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallHooksTests(unittest.TestCase):
    def test_merge_preserves_unrelated_hooks_and_is_idempotent(self) -> None:
        existing = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "keep-me"}]}]
            },
            "other": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "hooks.json"
            path.write_text(json.dumps(existing), encoding="utf-8")
            installer.install(
                path,
                "/usr/bin/python3",
                Path("/Library/Application Support/CodexPet/codex_pet_hook.py"),
            )
            first = json.loads(path.read_text(encoding="utf-8"))
            installer.install(
                path,
                "/usr/bin/python3",
                Path("/Library/Application Support/CodexPet/codex_pet_hook.py"),
            )
            second = json.loads(path.read_text(encoding="utf-8"))

        self.assertTrue(first["other"])
        commands = [
            hook["command"]
            for group in first["hooks"]["Stop"]
            for hook in group.get("hooks", [])
        ]
        self.assertIn("keep-me", commands)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
