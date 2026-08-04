#!/usr/bin/env python3
"""Tests for the non-destructive Codex hook installer."""

import importlib.util
import json
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "codex-hooks.json"
SPEC = importlib.util.spec_from_file_location(
    "install_codex_hooks", ROOT / "tools" / "install_codex_hooks.py"
)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(installer)


class InstallHooksTests(unittest.TestCase):
    def test_checked_in_example_matches_the_installer_event_contract(self) -> None:
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        hooks = example["hooks"]
        self.assertEqual(set(hooks), set(installer.EVENTS))

        expected = {
            "type": "command",
            "command": (
                "python3 /ABSOLUTE/PATH/TO/codex-pet-dev-board/"
                "mac/codex_pet_hook.py"
            ),
            "timeout": 3,
        }
        for event in installer.EVENTS:
            with self.subTest(event=event):
                commands = [
                    command
                    for group in hooks[event]
                    for command in group.get("hooks", [])
                ]
                self.assertIn(expected, commands)

    def test_merge_preserves_unrelated_hooks_and_is_idempotent(self) -> None:
        existing = {
            "hooks": {
                "Stop": [{"hooks": [{"type": "command", "command": "keep-me"}]}]
            },
            "other": True,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hooks.json"
            hook_script = root / "codex_pet_hook.py"
            hook_script.write_text("# hook\n", encoding="utf-8")
            path.write_text(json.dumps(existing), encoding="utf-8")
            installer.install(
                path,
                "/usr/bin/python3",
                hook_script,
            )
            first = json.loads(path.read_text(encoding="utf-8"))
            installer.install(
                path,
                "/usr/bin/python3",
                hook_script,
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

    def test_null_hooks_is_initialized_and_existing_mode_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hooks.json"
            hook_script = root / "hook.py"
            hook_script.write_text("# hook\n", encoding="utf-8")
            path.write_text('{"hooks": null, "other": true}', encoding="utf-8")
            path.chmod(0o640)

            installer.install(path, "/usr/bin/python3", hook_script)

            installed = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(installed["other"])
            self.assertEqual(set(installed["hooks"]), set(installer.EVENTS))
            self.assertEqual(
                installed["hooks"]["SessionStart"][0]["matcher"],
                installer.EVENT_MATCHERS["SessionStart"],
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)

    def test_complete_session_start_matcher_counts_as_existing_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hooks.json"
            hook_script = root / "hook.py"
            hook_script.write_text("# hook\n", encoding="utf-8")
            command = installer.command_string("/usr/bin/python3", hook_script.resolve())
            session_group = {
                "matcher": installer.EVENT_MATCHERS["SessionStart"],
                "hooks": [{"type": "command", "command": command}],
            }
            path.write_text(
                json.dumps({"hooks": {"SessionStart": [session_group]}}),
                encoding="utf-8",
            )

            installer.install(path, "/usr/bin/python3", hook_script)

            installed = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(installed["hooks"]["SessionStart"], [session_group])

    def test_matcher_scoped_and_malformed_groups_are_preserved_but_do_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hooks.json"
            hook_script = root / "hook.py"
            hook_script.write_text("# hook\n", encoding="utf-8")
            command = installer.command_string("/usr/bin/python3", hook_script.resolve())
            existing_groups = [
                None,
                {"matcher": "Bash", "hooks": [{"type": "command", "command": command}]},
                {"hooks": None, "keep": True},
            ]
            path.write_text(
                json.dumps({"hooks": {"PreToolUse": existing_groups}}),
                encoding="utf-8",
            )

            installer.install(path, "/usr/bin/python3", hook_script)

            installed = json.loads(path.read_text(encoding="utf-8"))
            groups = installed["hooks"]["PreToolUse"]
            self.assertEqual(groups[:3], existing_groups)
            unscoped = [group for group in groups if isinstance(group, dict) and not group.get("matcher")]
            self.assertTrue(
                any(
                    item.get("command") == command
                    for group in unscoped
                    for item in group.get("hooks") or []
                    if isinstance(item, dict)
                )
            )

    def test_invalid_structures_and_missing_hook_do_not_overwrite_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "hooks.json"
            hook_script = root / "hook.py"
            hook_script.write_text("# hook\n", encoding="utf-8")
            original = '{"hooks": []}'
            path.write_text(original, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "hooks.*JSON object"):
                installer.install(path, "/usr/bin/python3", hook_script)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

            with self.assertRaisesRegex(ValueError, "existing file"):
                installer.install(path, "/usr/bin/python3", root / "missing.py")
            self.assertEqual(path.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
