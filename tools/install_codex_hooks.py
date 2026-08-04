#!/usr/bin/env python3
"""Merge Codex Pet lifecycle hooks without replacing unrelated user hooks."""

import argparse
import json
import os
import shlex
import stat
import tempfile
from pathlib import Path
from typing import Any, Dict

EVENTS = (
    "SessionStart", "SessionEnd", "UserPromptSubmit", "PreToolUse",
    "PostToolUse", "PermissionRequest", "PreCompact", "PostCompact",
    "SubagentStart", "SubagentStop", "Stop",
)
EVENT_MATCHERS = {"SessionStart": "startup|resume|clear|compact"}


def command_string(python: str, hook: Path) -> str:
    return shlex.join([python, str(hook)])


def install(destination: Path, python: str, hook: Path) -> None:
    hook = hook.expanduser().resolve()
    if not hook.is_file():
        raise ValueError("hook script must be an existing file: {}".format(hook))

    data: Dict[str, Any] = {}
    existing_mode = 0o600
    if destination.exists():
        existing_mode = stat.S_IMODE(destination.stat().st_mode)
        loaded = json.loads(destination.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("existing hooks file must contain a JSON object")
        data = loaded
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
        data["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise ValueError("existing 'hooks' value must be a JSON object")

    command = command_string(python, hook)
    for event in EVENTS:
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            raise ValueError("existing hook event {!r} must contain a list".format(event))
        expected_matcher = EVENT_MATCHERS.get(event)
        already_present = any(
            item.get("command") == command
            for group in groups
            if isinstance(group, dict)
            and (
                not group.get("matcher")
                or group.get("matcher") == expected_matcher
            )
            for item in (
                group.get("hooks") if isinstance(group.get("hooks"), list) else []
            )
            if isinstance(item, dict)
        )
        if not already_present:
            group = {
                "hooks": [{"type": "command", "command": command, "timeout": 3}]
            }
            if expected_matcher is not None:
                group["matcher"] = expected_matcher
            groups.append(group)

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".tmp.", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, existing_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = -1
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hooks", type=Path, required=True)
    parser.add_argument("--python", required=True)
    parser.add_argument("--hook-script", type=Path, required=True)
    args = parser.parse_args()
    install(args.hooks.expanduser(), args.python, args.hook_script)
    print("Codex Pet hooks installed in {}".format(args.hooks.expanduser()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
