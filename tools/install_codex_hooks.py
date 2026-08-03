#!/usr/bin/env python3
"""Merge Codex Pet lifecycle hooks without replacing unrelated user hooks."""

import argparse
import json
import os
import shlex
from pathlib import Path
from typing import Any, Dict

EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
    "PostToolUse", "PermissionRequest", "PreCompact", "PostCompact",
    "SubagentStart", "SubagentStop", "Stop",
)


def command_string(python: str, hook: Path) -> str:
    return shlex.join([python, str(hook)])


def install(destination: Path, python: str, hook: Path) -> None:
    data: Dict[str, Any] = {}
    if destination.exists():
        loaded = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("existing hooks file must contain a JSON object")
        data = loaded
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("existing 'hooks' value must be a JSON object")

    command = command_string(python, hook)
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError("existing hook event {!r} must contain a list".format(event))
        already_present = any(
            item.get("command") == command
            for group in groups if isinstance(group, dict)
            for item in group.get("hooks", []) if isinstance(item, dict)
        )
        if not already_present:
            groups.append({"hooks": [{"type": "command", "command": command, "timeout": 3}]})

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--hook-script", type=Path, required=True)
    args = parser.parse_args()
    install(args.hooks.expanduser(), args.python, args.hook_script.resolve())
    print("Codex Pet hooks installed in {}".format(args.hooks.expanduser()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
