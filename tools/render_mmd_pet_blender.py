#!/usr/bin/env python3
"""Render a user-provided MMD/PMX model into Codex Pet's private frame slots.

This script runs inside Blender.  It keeps the PMX, textures, imported blend,
and rendered frames outside the repository unless the caller deliberately
chooses another output directory.

Example with a temporary legacy-style mmd_tools checkout::

    BLENDER_USER_SCRIPTS=/tmp/mmd/scripts \
    /Applications/Blender.app/Contents/MacOS/Blender --background \
      --factory-startup --python tools/render_mmd_pet_blender.py -- \
      --pmx /absolute/model.pmx --output-dir /tmp/pet-frames \
      --mmd-tools-dir /tmp/mmd/scripts/addons/mmd_tools \
      --mmd-python-modules /tmp/mmd/python-modules

The default smooth profile renders the firmware's 152-slot motion contract. A
73-frame compatibility profile remains available for legacy atlas-based assets.
The authored motion is status-oriented, and the final 16 slots are treated as
four eased gaze clips: up, right, down, and left.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONVERTER_PATH = ROOT / "tools" / "convert_codex_pet_p4.py"
SPEC = importlib.util.spec_from_file_location("convert_codex_pet_p4", CONVERTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load frame contract from {CONVERTER_PATH}")
CONVERTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONVERTER)

FRAME_SPECS = CONVERTER.FRAME_SPECS
ACTION_RANGES = CONVERTER.ACTION_RANGES
FRAME_W = CONVERTER.FRAME_W
FRAME_H = CONVERTER.FRAME_H

FRAME_CONTEXT: dict[str, tuple[int, int]] = {}
for _, first, count in ACTION_RANGES:
    for local_index, (name, _, _) in enumerate(FRAME_SPECS[first : first + count]):
        FRAME_CONTEXT[name] = (local_index, count)

MORPH_NAMES = {
    "blink": "まばたき",
    "smile_eyes": "笑い",
    "smile_mouth": "にこり口",
    "serious": "真面目",
    "concerned": "困る",
    "surprised": "びっくり",
    "failed": "絶望",
    "mouth_down": "口角下げ",
    "pupil_up": "瞳上",
    "pupil_right": "瞳右",
    "pupil_down": "瞳下",
    "pupil_left": "瞳左",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pmx", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--mmd-tools-dir", type=Path)
    parser.add_argument("--mmd-python-modules", type=Path)
    parser.add_argument("--mmd-module", default="mmd_tools")
    parser.add_argument("--scale", type=float, default=0.08)
    parser.add_argument(
        "--provenance-name",
        default="User-provided PMX model",
        help="non-path source label written to CREDITS.txt",
    )
    parser.add_argument(
        "--model-page",
        help="optional public model or license page written to CREDITS.txt",
    )
    parser.add_argument(
        "--credit",
        action="append",
        default=[],
        help="credit line written to CREDITS.txt; repeat for multiple credits",
    )
    parser.add_argument(
        "--rights-note",
        default="Verify model rights before redistributing derived assets.",
        help="rights or authorization note written to CREDITS.txt",
    )
    parser.add_argument(
        "--keep-mask",
        action="store_true",
        help="keep the model's mask materials visible (hidden by default)",
    )
    parser.add_argument(
        "--only",
        help="comma-separated exact frame names for a quick smoke render",
    )
    parser.add_argument(
        "--motion-profile",
        choices=("compat", "smooth"),
        default="smooth",
        help="smooth renders expanded high-frame-rate actions; compat keeps 73 frames",
    )
    return parser.parse_args(argv)


def blender_script_args(argv: list[str]) -> list[str]:
    if "--" not in argv:
        return []
    return argv[argv.index("--") + 1 :]


def smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def _lerp_value(start: Any, end: Any, amount: float) -> Any:
    """Interpolate scalar or tuple pose controls without changing their shape."""
    if isinstance(start, tuple):
        if len(start) != len(end):
            raise ValueError("pose interpolation tuple lengths must match")
        return tuple(
            _lerp_value(start_value, end_value, amount)
            for start_value, end_value in zip(start, end)
        )
    return start + (end - start) * amount


def _sample_pose_cycle(
    keys: tuple[dict[str, Any], ...], frame_index: int, frame_count: int
) -> dict[str, Any]:
    """Sample a closed key-pose cycle with eased in-between frames."""
    position = frame_index * len(keys) / max(frame_count, 1)
    first_index = math.floor(position) % len(keys)
    second_index = (first_index + 1) % len(keys)
    amount = smoothstep(position - math.floor(position))
    return {
        name: _lerp_value(value, keys[second_index][name], amount)
        for name, value in keys[first_index].items()
    }


def _sample_pose_path(
    keys: tuple[dict[str, Any], ...], frame_index: int, frame_count: int
) -> dict[str, Any]:
    """Sample an open action path while preserving its first and last poses."""
    position = frame_index * (len(keys) - 1) / max(frame_count - 1, 1)
    return _sample_pose_position(keys, position)


def _sample_pose_position(
    keys: tuple[dict[str, Any], ...], position: float
) -> dict[str, Any]:
    """Sample an open pose path at an explicit fractional key position."""
    first_index = min(math.floor(position), len(keys) - 1)
    second_index = min(first_index + 1, len(keys) - 1)
    amount = smoothstep(position - math.floor(position))
    return {
        name: _lerp_value(value, keys[second_index][name], amount)
        for name, value in keys[first_index].items()
    }


def _base_pose() -> dict[str, Any]:
    return {
        "root_x": 0.018,
        "root_z": 0.0,
        "root_yaw": -15.0,
        # The MMD center bone moves the torso relative to the foot IK parents.
        # Keep whole-rig placement (`root_*`) separate from weight/compression.
        "center_location": (0.0, 0.0, 0.0),
        "lower_x": 0.0,
        "lower_z": 7.0,
        # Keep lumbar and thoracic pitch separate. `upper1_x` drives 上半身;
        # `upper_x` retains the existing 上半身2/status-pose channel.
        "upper1_x": 0.0,
        "upper_x": 0.0,
        "upper_y": 4.0,
        "upper_z": -4.0,
        "head_x": -2.0,
        "head_y": 5.0,
        "head_z": 2.0,
        "right_arm_target": (-0.14, -0.22, -1.0),
        "left_arm_target": (0.20, -0.10, -1.0),
        "right_forearm_target": None,
        "right_forearm_raise": 0.86,
        "left_forearm_raise": 0.08,
        "right_wrist_flick": 0.0,
        "right_wrist_cup": 0.0,
        "right_finger_curl": 0.0,
        "right_finger_splay": 0.0,
        "left_wrist_roll": 0.0,
        # The neutral silhouette is deliberately visible at pet size: the
        # front foot crosses the body line, the support leg stays straighter,
        # and the toes never form the parallel "punishment stand" shape.
        "right_leg": (-5.0, 0.0, 2.5),
        "left_leg": (-1.0, 0.0, -1.0),
        "right_knee": (16.0, 0.0, 0.0),
        "left_knee": (3.0, 0.0, 0.0),
        "right_foot_location": (0.078, -0.080, 0.010),
        "left_foot_location": (-0.016, 0.035, 0.0),
        "right_foot_rotation": (0.0, 0.0, -15.0),
        "left_foot_rotation": (0.0, 0.0, 7.0),
        "coat_sway": 0.0,
        "braid_sway": 0.0,
        "morphs": {},
    }


def _apply_idle_key(
    pose: dict[str, Any], frame_index: int, frame_count: int = 6
) -> None:
    """Apply an eyes-first, one-leg-supported idle shared with gaze frame zero."""
    keys = (
        {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
         "upper1_x": 0.0, "upper_x": 0.0, "upper_z": -4.0,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.0, "braid_sway": 0.0},
        {"center_location": (-0.002, 0.0, -0.003), "lower_z": 7.2,
         "upper1_x": -0.4, "upper_x": -0.2, "upper_z": -3.8,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.0, "braid_sway": 0.0},
        {"center_location": (-0.004, 0.0, -0.006), "lower_z": 7.4,
         "upper1_x": -0.8, "upper_x": -0.5, "upper_z": -3.6,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.10, "braid_sway": 0.0},
        {"center_location": (-0.004, 0.0, -0.006), "lower_z": 7.6,
         "upper1_x": -0.8, "upper_x": -0.5, "upper_z": -3.5,
         "head_x": -2.0, "head_y": 7.0, "head_z": 1.5,
         "coat_sway": 0.25, "braid_sway": 0.0},
        {"center_location": (-0.002, 0.0, -0.003), "lower_z": 7.4,
         "upper1_x": -0.4, "upper_x": -0.2, "upper_z": -3.7,
         "head_x": -2.0, "head_y": 7.0, "head_z": 1.5,
         "coat_sway": 0.35, "braid_sway": -0.15},
        {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
         "upper1_x": 0.0, "upper_x": 0.0, "upper_z": -4.0,
         "head_x": -2.0, "head_y": 6.0, "head_z": 1.5,
         "coat_sway": 0.15, "braid_sway": -0.30},
        {"center_location": (0.001, 0.0, -0.002), "lower_z": 6.8,
         "upper1_x": 0.3, "upper_x": 0.2, "upper_z": -4.2,
         "head_x": -2.0, "head_y": 6.0, "head_z": 1.5,
         "coat_sway": 0.0, "braid_sway": -0.15},
        {"center_location": (0.003, 0.0, -0.004), "lower_z": 6.6,
         "upper1_x": 0.5, "upper_x": 0.3, "upper_z": -4.4,
         "head_x": -2.0, "head_y": 4.0, "head_z": 2.5,
         "coat_sway": -0.25, "braid_sway": 0.0},
        {"center_location": (0.001, 0.0, -0.002), "lower_z": 6.8,
         "upper1_x": 0.2, "upper_x": 0.1, "upper_z": -4.2,
         "head_x": -2.0, "head_y": 4.0, "head_z": 2.5,
         "coat_sway": -0.35, "braid_sway": 0.18},
        {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
         "upper1_x": 0.0, "upper_x": 0.0, "upper_z": -4.0,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.0, "braid_sway": 0.0},
        {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
         "upper1_x": 0.0, "upper_x": 0.0, "upper_z": -4.0,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.0, "braid_sway": 0.0},
        {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
         "upper1_x": 0.0, "upper_x": 0.0, "upper_z": -4.0,
         "head_x": -2.0, "head_y": 5.0, "head_z": 2.0,
         "coat_sway": 0.0, "braid_sway": 0.0},
    )
    if frame_count == 12:
        sampled = dict(keys[frame_index])
    else:
        sampled = _sample_pose_cycle(keys[:9], frame_index, frame_count)
    pose.update(sampled)


def _apply_work_step(pose: dict[str, Any], frame_index: int, frame_count: int) -> None:
    """Apply a twelve-key run with explicit support and airborne phases."""

    right_half = (
        # Right heel contact; feet stay on their anatomical sides.
        {"root_x": 0.012, "root_z": 0.000, "root_yaw": -60.0,
         "center_location": (0.016, -0.090, -0.025),
         "lower_x": 7.0, "lower_z": 7.0,
         "upper1_x": 6.0, "upper_x": 3.5, "upper_z": -6.0,
         "head_x": -3.0,
         "right_leg": (-16.0, 0.0, 4.0), "left_leg": (14.0, 0.0, -4.0),
         "right_knee": (20.0, 0.0, 0.0), "left_knee": (30.0, 0.0, 0.0),
         "right_foot_location": (-0.145, -0.120, 0.000),
         "left_foot_location": (0.115, 0.085, 0.045),
         "right_foot_rotation": (10.0, 0.0, -8.0),
         "left_foot_rotation": (-18.0, 0.0, 8.0), "arm_phase": -1.00},
        # Load: the torso drops over a firmly planted right foot.
        {"root_x": 0.010, "root_z": 0.000, "root_yaw": -60.0,
         "center_location": (0.020, -0.105, -0.115),
         "lower_x": 8.0, "lower_z": 8.0,
         "upper1_x": 7.0, "upper_x": 4.0, "upper_z": -4.0,
         "head_x": -3.5,
         "right_leg": (-10.0, 0.0, 4.0), "left_leg": (18.0, 0.0, -4.0),
         "right_knee": (30.0, 0.0, 0.0), "left_knee": (44.0, 0.0, 0.0),
         "right_foot_location": (-0.145, -0.120, 0.000),
         "left_foot_location": (0.110, 0.065, 0.080),
         "right_foot_rotation": (2.0, 0.0, -8.0),
         "left_foot_rotation": (-18.0, 0.0, 8.0), "arm_phase": -0.72},
        # Mid-stance lengthens the support leg as the free heel folds upward.
        {"root_x": 0.006, "root_z": 0.000, "root_yaw": -60.0,
         "center_location": (0.012, -0.110, -0.035),
         "lower_x": 8.0, "lower_z": 7.0,
         "upper1_x": 7.5, "upper_x": 4.5, "upper_z": -1.0,
         "head_x": -4.0,
         "right_leg": (-2.0, 0.0, 3.0), "left_leg": (20.0, 0.0, -4.0),
         "right_knee": (24.0, 0.0, 0.0), "left_knee": (52.0, 0.0, 0.0),
         "right_foot_location": (-0.145, -0.120, 0.000),
         "left_foot_location": (0.105, 0.040, 0.120),
         "right_foot_rotation": (-5.0, 0.0, -8.0),
         "left_foot_rotation": (-14.0, 0.0, 8.0), "arm_phase": -0.38},
        # Toe-off raises the support heel; neither foot is flat anymore.
        {"root_x": 0.002, "root_z": 0.010, "root_yaw": -60.0,
         "center_location": (0.004, -0.115, 0.000),
         "lower_x": 7.5, "lower_z": 2.0,
         "upper1_x": 7.0, "upper_x": 4.5, "upper_z": 2.0,
         "head_x": -4.0,
         "right_leg": (10.0, 0.0, 3.0), "left_leg": (-18.0, 0.0, -3.0),
         "right_knee": (18.0, 0.0, 0.0), "left_knee": (54.0, 0.0, 0.0),
         "right_foot_location": (-0.145, -0.120, 0.000),
         "left_foot_location": (0.110, -0.010, 0.145),
         "right_foot_rotation": (-20.0, 0.0, -8.0),
         "left_foot_rotation": (-8.0, 0.0, 8.0), "arm_phase": 0.00},
        # Flight: both feet clear the floor while the left knee leads forward.
        {"root_x": -0.004, "root_z": 0.082, "root_yaw": -60.0,
         "center_location": (-0.004, -0.100, 0.000),
         "lower_x": 7.0, "lower_z": -3.0,
         "upper1_x": 6.5, "upper_x": 4.0, "upper_z": 5.0,
         "head_x": -3.5,
         "right_leg": (20.0, 0.0, 3.0), "left_leg": (-22.0, 0.0, -3.0),
         "right_knee": (58.0, 0.0, 0.0), "left_knee": (24.0, 0.0, 0.0),
         "right_foot_location": (-0.125, 0.065, 0.145),
         "left_foot_location": (0.125, -0.065, 0.105),
         "right_foot_rotation": (-16.0, 0.0, -8.0),
         "left_foot_rotation": (0.0, 0.0, 8.0), "arm_phase": 0.56},
        # Apex: a second distinct airborne key gives both the 8-frame and
        # 24-frame contracts enough screen time to read as running, not a
        # high-stepping walk with an instantaneous hop.
        {"root_x": -0.007, "root_z": 0.095, "root_yaw": -60.0,
         "center_location": (-0.008, -0.100, 0.000),
         "lower_x": 6.8, "lower_z": -4.5,
         "upper1_x": 6.3, "upper_x": 3.8, "upper_z": 6.0,
         "head_x": -3.3,
         "right_leg": (21.0, 0.0, 3.0), "left_leg": (-20.0, 0.0, -3.0),
         "right_knee": (54.0, 0.0, 0.0), "left_knee": (26.0, 0.0, 0.0),
         "right_foot_location": (-0.132, 0.078, 0.175),
         "left_foot_location": (0.132, -0.075, 0.140),
         "right_foot_rotation": (-14.0, 0.0, -8.0),
         "left_foot_rotation": (2.0, 0.0, 8.0), "arm_phase": 0.72},
        # Left pre-contact unfolds the leading leg without touching down early.
        {"root_x": -0.010, "root_z": 0.065, "root_yaw": -60.0,
         "center_location": (-0.012, -0.090, -0.010),
         "lower_x": 6.5, "lower_z": -6.0,
         "upper1_x": 6.0, "upper_x": 3.5, "upper_z": 7.0,
         "head_x": -3.0,
         "right_leg": (22.0, 0.0, 3.0), "left_leg": (-16.0, 0.0, -4.0),
         "right_knee": (48.0, 0.0, 0.0), "left_knee": (16.0, 0.0, 0.0),
         "right_foot_location": (-0.140, 0.090, 0.155),
         "left_foot_location": (0.140, -0.105, 0.055),
         "right_foot_rotation": (-12.0, 0.0, -8.0),
         "left_foot_rotation": (8.0, 0.0, 8.0), "arm_phase": 0.86},
    )

    def mirrored(key: dict[str, Any]) -> dict[str, Any]:
        center_x, center_y, center_z = key["center_location"]
        right_foot = key["right_foot_location"]
        left_foot = key["left_foot_location"]
        right_rotation = key["right_foot_rotation"]
        left_rotation = key["left_foot_rotation"]
        right_leg = key["right_leg"]
        left_leg = key["left_leg"]
        return {
            **key,
            "root_x": -key["root_x"],
            "center_location": (-center_x, center_y, center_z),
            "lower_z": -key["lower_z"],
            "upper_z": -key["upper_z"],
            "right_leg": (left_leg[0], left_leg[1], -left_leg[2]),
            "left_leg": (right_leg[0], right_leg[1], -right_leg[2]),
            "right_knee": key["left_knee"],
            "left_knee": key["right_knee"],
            "right_foot_location": (-left_foot[0], left_foot[1], left_foot[2]),
            "left_foot_location": (-right_foot[0], right_foot[1], right_foot[2]),
            "right_foot_rotation": (
                left_rotation[0], left_rotation[1], -left_rotation[2]
            ),
            "left_foot_rotation": (
                right_rotation[0], right_rotation[1], -right_rotation[2]
            ),
            "arm_phase": -key["arm_phase"],
        }

    keys = right_half + tuple(mirrored(key) for key in right_half)
    sampled = _sample_pose_cycle(keys, frame_index, frame_count)
    arm_phase = sampled.pop("arm_phase")
    pose.update(sampled)
    # Compact runner's arm drive: forward is local -Y, and each arm opposes
    # its leg. Keep the elbows bent instead of turning the gait into a fast
    # walk with straight, hanging arms.
    pose["right_arm_target"] = (-0.38, -0.02 - 0.40 * arm_phase, -0.68)
    pose["left_arm_target"] = (0.38, -0.02 + 0.40 * arm_phase, -0.68)
    pose["right_forearm_raise"] = 0.38 + 0.18 * max(0.0, arm_phase)
    pose["left_forearm_raise"] = 0.38 + 0.18 * max(0.0, -arm_phase)
    pose["coat_sway"] = -8.0 * arm_phase
    pose["braid_sway"] = 10.0 * arm_phase


def pose_for_frame(name: str, frame_index: int, frame_count: int) -> dict[str, Any]:
    """Return a status-first pose; angle values are degrees."""
    phase = 2.0 * math.pi * frame_index / max(frame_count, 1)
    progress = frame_index / max(frame_count - 1, 1)
    pose = _base_pose()
    morphs: dict[str, float] = pose["morphs"]

    if name.startswith("IDLE_"):
        _apply_idle_key(pose, frame_index, frame_count)
        morphs["serious"] = 0.10
        if frame_count == 12:
            if frame_index in (1, 2, 3):
                morphs["pupil_right"] = (0.18, 0.22, 0.22)[frame_index - 1]
            elif frame_index == 4:
                morphs["pupil_right"] = 0.14
            elif frame_index == 5:
                morphs["smile_mouth"] = 0.06
            elif frame_index in (6, 7):
                morphs["pupil_left"] = 0.18
            elif frame_index == 8:
                morphs["pupil_left"] = 0.10
            elif frame_index == 10:
                morphs["blink"] = 0.45
            elif frame_index == 11:
                morphs["blink"] = 1.0
        elif frame_index == frame_count - 2:
            morphs["blink"] = 0.45
        elif frame_index == frame_count - 1:
            morphs["blink"] = 1.0
    elif name.startswith("RUNNING_RIGHT_"):
        _apply_work_step(pose, frame_index, frame_count)
        pose["root_yaw"] = -60.0
        pose["head_y"] = 10.0
        morphs["serious"] = 0.24
    elif name.startswith("RUNNING_LEFT_"):
        _apply_work_step(pose, frame_index, frame_count)
        pose["root_yaw"] = 60.0
        pose["head_y"] = -10.0
        morphs["serious"] = 0.24
    elif name.startswith("WAVING_"):
        wave_keys = (
            {"center_location": (-0.006, 0.0, -0.004), "lower_z": 7.5,
             "upper1_x": 0.5, "upper_x": 0.0, "upper_y": 5.0, "upper_z": -4.5,
             "head_x": -1.5, "head_y": 5.0, "head_z": -1.0,
             "right_leg": (-5.0, 0.0, 2.5), "right_knee": (16.0, 0.0, 0.0),
             "right_foot_location": (0.078, -0.080, 0.010),
             "right_foot_rotation": (-2.0, 0.0, -15.0),
             "right_arm_target": (-0.46, -0.18, -0.38),
             "right_forearm_target": (0.24, -0.40, 0.88),
             "right_forearm_raise": 0.78, "right_wrist_flick": -6.0,
             "right_wrist_cup": -5.0, "right_finger_curl": 0.30,
             "right_finger_splay": 0.02, "coat_sway": 0.0, "braid_sway": 0.0},
            {"center_location": (-0.012, 0.0, -0.012), "lower_z": 9.0,
             "upper1_x": 0.8, "upper_x": 0.0, "upper_y": 6.5, "upper_z": -6.0,
             "head_x": -2.0, "head_y": 8.0, "head_z": -1.5,
             "right_leg": (-7.0, 0.0, 3.0), "right_knee": (19.0, 0.0, 0.0),
             "right_foot_location": (0.080, -0.080, 0.016),
             "right_foot_rotation": (-7.0, 0.0, -15.0),
             "right_arm_target": (-0.58, -0.20, -0.26),
             "right_forearm_target": (0.12, -0.32, 0.94),
             "right_forearm_raise": 0.86, "right_wrist_flick": 0.0,
             "right_wrist_cup": -5.0, "right_finger_curl": 0.22,
             "right_finger_splay": 0.05, "coat_sway": -0.5, "braid_sway": 0.0},
            {"center_location": (-0.012, 0.0, -0.012), "lower_z": 9.0,
             "upper1_x": 0.8, "upper_x": 0.0, "upper_y": 7.0, "upper_z": -6.2,
             "head_x": -2.3, "head_y": 9.0, "head_z": -1.8,
             "right_leg": (-7.0, 0.0, 3.0), "right_knee": (19.0, 0.0, 0.0),
             "right_foot_location": (0.080, -0.080, 0.016),
             "right_foot_rotation": (-7.0, 0.0, -15.0),
             "right_arm_target": (-0.60, -0.20, -0.24),
             "right_forearm_target": (0.08, -0.30, 0.95),
             "right_forearm_raise": 0.88, "right_wrist_flick": 22.0,
             "right_wrist_cup": -4.0, "right_finger_curl": 0.18,
             "right_finger_splay": 0.10, "coat_sway": -0.8, "braid_sway": 0.4},
            {"center_location": (-0.012, 0.0, -0.012), "lower_z": 9.0,
             "upper1_x": 0.8, "upper_x": 0.0, "upper_y": 7.0, "upper_z": -6.2,
             "head_x": -2.3, "head_y": 9.0, "head_z": -1.8,
             "right_leg": (-7.0, 0.0, 3.0), "right_knee": (19.0, 0.0, 0.0),
             "right_foot_location": (0.080, -0.080, 0.016),
             "right_foot_rotation": (-7.0, 0.0, -15.0),
             "right_arm_target": (-0.60, -0.20, -0.24),
             "right_forearm_target": (0.10, -0.31, 0.945),
             "right_forearm_raise": 0.88, "right_wrist_flick": -16.0,
             "right_wrist_cup": -6.0, "right_finger_curl": 0.24,
             "right_finger_splay": 0.05, "coat_sway": -0.2, "braid_sway": -1.0},
            {"center_location": (-0.010, 0.0, -0.010), "lower_z": 8.8,
             "upper1_x": 0.6, "upper_x": 0.0, "upper_y": 6.5, "upper_z": -5.8,
             "head_x": -2.5, "head_y": 8.5, "head_z": -2.3,
             "right_leg": (-6.5, 0.0, 3.0), "right_knee": (18.0, 0.0, 0.0),
             "right_foot_location": (0.080, -0.080, 0.016),
             "right_foot_rotation": (-7.0, 0.0, -15.0),
             "right_arm_target": (-0.59, -0.20, -0.25),
             "right_forearm_target": (0.10, -0.31, 0.945),
             "right_forearm_raise": 0.87, "right_wrist_flick": 14.0,
             "right_wrist_cup": -4.0, "right_finger_curl": 0.18,
             "right_finger_splay": 0.08, "coat_sway": 0.3, "braid_sway": 0.8},
            {"center_location": (-0.008, 0.0, -0.008), "lower_z": 8.5,
             "upper1_x": 0.4, "upper_x": 0.0, "upper_y": 6.0, "upper_z": -5.4,
             "head_x": -3.0, "head_y": 7.0, "head_z": -3.0,
             "right_leg": (-6.0, 0.0, 3.0), "right_knee": (18.0, 0.0, 0.0),
             "right_foot_location": (0.080, -0.080, 0.016),
             "right_foot_rotation": (-7.0, 0.0, -15.0),
             "right_arm_target": (-0.58, -0.20, -0.26),
             "right_forearm_target": (0.12, -0.32, 0.94),
             "right_forearm_raise": 0.85, "right_wrist_flick": 10.0,
             "right_wrist_cup": -5.0, "right_finger_curl": 0.18,
             "right_finger_splay": 0.08, "coat_sway": 0.2, "braid_sway": 0.4},
            {"center_location": (-0.004, 0.0, -0.004), "lower_z": 7.8,
             "upper1_x": 0.2, "upper_x": 0.0, "upper_y": 5.0, "upper_z": -4.8,
             "head_x": -2.5, "head_y": 6.0, "head_z": -2.0,
             "right_leg": (-5.5, 0.0, 2.5), "right_knee": (17.0, 0.0, 0.0),
             "right_foot_location": (0.079, -0.080, 0.012),
             "right_foot_rotation": (-3.0, 0.0, -15.0),
             "right_arm_target": (-0.52, -0.19, -0.36),
             "right_forearm_target": (0.20, -0.36, 0.91),
             "right_forearm_raise": 0.80, "right_wrist_flick": 2.0,
             "right_wrist_cup": -4.0, "right_finger_curl": 0.24,
             "right_finger_splay": 0.04, "coat_sway": -0.2, "braid_sway": -0.4},
            {"center_location": (0.0, 0.0, 0.0), "lower_z": 7.0,
             "upper1_x": 0.0, "upper_x": 0.0, "upper_y": 4.0, "upper_z": -4.0,
             "head_x": -2.0, "head_y": 5.0, "head_z": 0.0,
             "right_leg": (-5.0, 0.0, 2.5), "right_knee": (16.0, 0.0, 0.0),
             "right_foot_location": (0.078, -0.080, 0.010),
             "right_foot_rotation": (0.0, 0.0, -15.0),
             "right_arm_target": (-0.34, -0.19, -0.58),
             "right_forearm_target": (0.30, -0.42, 0.85),
             "right_forearm_raise": 0.72, "right_wrist_flick": 0.0,
             "right_wrist_cup": -2.0, "right_finger_curl": 0.30,
             "right_finger_splay": 0.02, "coat_sway": 0.0, "braid_sway": 0.1},
        )
        sampled = _sample_pose_path(wave_keys, frame_index, frame_count)
        pose.update(sampled)
        pose["root_yaw"] = -18.0
        pose["left_leg"] = (-1.0, 0.0, -1.0)
        pose["left_knee"] = (4.0, 0.0, 0.0)
        pose["left_foot_location"] = (-0.016, 0.035, 0.0)
        pose["left_foot_rotation"] = (0.0, 0.0, 7.0)
        pose["left_arm_target"] = (0.22, -0.08, -1.0)
        pose["left_forearm_raise"] = 0.06
        wave_morphs = (
            {"serious": 0.16, "smile_mouth": 0.05},
            {"serious": 0.14, "smile_mouth": 0.08, "pupil_left": 0.18},
            {"serious": 0.12, "smile_mouth": 0.10, "pupil_left": 0.28},
            {"serious": 0.12, "smile_mouth": 0.12, "pupil_left": 0.18},
            {"serious": 0.10, "smile_mouth": 0.16,
             "pupil_left": 0.08, "blink": 0.22},
            {"serious": 0.10, "smile_mouth": 0.18},
            {"serious": 0.12, "smile_mouth": 0.12},
            {"serious": 0.12, "smile_mouth": 0.08},
        )
        morph_index = round(frame_index * 7 / max(frame_count - 1, 1))
        morphs.update(wave_morphs[morph_index])
    elif name.startswith("JUMPING_"):
        jump_keys = (
            # Anticipation begins from a softened asymmetric stance.
            {"root_z": 0.000, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, -0.055),
             "right_leg": (-12.0, 0.0, 1.0), "left_leg": (-8.0, 0.0, -1.0),
             "right_knee": (34.0, 0.0, 0.0), "left_knee": (28.0, 0.0, 0.0),
             "head_x": 8.0, "head_z": 0.0, "upper_x": 10.0,
             "right_forearm_raise": 0.10, "left_forearm_raise": 0.08,
             "right_foot_location": (0.030, -0.080, 0.000),
             "left_foot_location": (-0.010, 0.035, 0.000),
             "right_foot_rotation": (0.0, 0.0, -8.0),
             "left_foot_rotation": (0.0, 0.0, 8.0),
             "right_arm_target": (-0.42, 0.16, -0.72),
             "left_arm_target": (0.46, 0.16, -0.72), "coat_sway": 0.0},
            # Deep compression: the center drops while both IK feet stay planted.
            {"root_z": 0.000, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, -0.310),
             "right_leg": (-24.0, 0.0, 8.0), "left_leg": (-20.0, 0.0, -8.0),
             "right_knee": (78.0, 0.0, 0.0), "left_knee": (70.0, 0.0, 0.0),
             "head_x": 18.0, "head_z": 0.0, "upper_x": 22.0,
             "right_forearm_raise": 0.06, "left_forearm_raise": 0.05,
             "right_foot_location": (-0.100, -0.030, 0.000),
             "left_foot_location": (0.100, 0.040, 0.000),
             "right_foot_rotation": (2.0, 0.0, -6.0),
             "left_foot_rotation": (2.0, 0.0, 6.0),
             "right_arm_target": (-0.45, 0.18, -0.76),
             "left_arm_target": (0.49, 0.18, -0.76), "coat_sway": 1.0},
            # Forceful extension and toe-off.
            {"root_z": 0.020, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, 0.000),
             "right_leg": (2.0, 0.0, 1.0), "left_leg": (3.0, 0.0, -1.0),
             "right_knee": (7.0, 0.0, 0.0), "left_knee": (6.0, 0.0, 0.0),
             "head_x": -3.0, "head_z": -1.0, "upper_x": -6.0,
             "right_forearm_raise": 0.58, "left_forearm_raise": 0.50,
             "right_foot_location": (-0.005, -0.005, 0.000),
             "left_foot_location": (0.005, 0.025, 0.000),
             "right_foot_rotation": (-28.0, 0.0, -6.0),
             "left_foot_rotation": (-26.0, 0.0, 6.0),
             "right_arm_target": (-0.52, -0.10, -0.18),
             "left_arm_target": (0.56, -0.10, -0.18), "coat_sway": -4.0},
            # Rising flight keeps the legs long before the tuck.
            {"root_z": 0.155, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, 0.000),
             "right_leg": (-4.0, 0.0, 1.0), "left_leg": (-2.0, 0.0, -1.0),
             "right_knee": (16.0, 0.0, 0.0), "left_knee": (12.0, 0.0, 0.0),
             "head_x": -7.0, "head_z": 2.0, "upper_x": -8.0,
             "right_forearm_raise": 0.76, "left_forearm_raise": 0.68,
             "right_foot_location": (-0.016, 0.015, 0.100),
             "left_foot_location": (0.016, 0.025, 0.090),
             "right_foot_rotation": (-20.0, 0.0, -6.0),
             "left_foot_rotation": (-18.0, 0.0, 6.0),
             "right_arm_target": (-0.58, -0.08, 0.08),
             "left_arm_target": (0.62, -0.08, 0.08), "coat_sway": -7.0},
            # Apex tuck separates the legs and raises both feet toward the hips.
            {"root_z": 0.230, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, -0.025),
             "right_leg": (-35.0, 0.0, 10.0), "left_leg": (-30.0, 0.0, -10.0),
             "right_knee": (90.0, 0.0, 0.0), "left_knee": (82.0, 0.0, 0.0),
             "head_x": -9.0, "head_z": 4.0, "upper_x": -10.0,
             "right_forearm_raise": 0.92, "left_forearm_raise": 0.88,
             "right_foot_location": (-0.120, 0.060, 0.380),
             "left_foot_location": (0.120, 0.020, 0.320),
             "right_foot_rotation": (-8.0, 0.0, -5.0),
             "left_foot_rotation": (-6.0, 0.0, 5.0),
             "right_arm_target": (-0.66, -0.06, 0.30),
             "left_arm_target": (0.70, -0.06, 0.30), "coat_sway": -8.0},
            # Descent unfolds before the feet reach the floor.
            {"root_z": 0.170, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, 0.000),
             "right_leg": (-8.0, 0.0, 2.0), "left_leg": (-5.0, 0.0, -2.0),
             "right_knee": (26.0, 0.0, 0.0), "left_knee": (20.0, 0.0, 0.0),
             "head_x": -3.0, "head_z": 2.0, "upper_x": -4.0,
             "right_forearm_raise": 0.70, "left_forearm_raise": 0.62,
             "right_foot_location": (-0.020, 0.020, 0.145),
             "left_foot_location": (0.020, 0.030, 0.125),
             "right_foot_rotation": (8.0, 0.0, -6.0),
             "left_foot_rotation": (7.0, 0.0, 6.0),
             "right_arm_target": (-0.54, -0.08, 0.02),
             "left_arm_target": (0.58, -0.08, 0.02), "coat_sway": -3.0},
            # Toe contact precedes the deeper landing compression.
            {"root_z": 0.035, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, -0.035),
             "right_leg": (-12.0, 0.0, 1.0), "left_leg": (-10.0, 0.0, -1.0),
             "right_knee": (36.0, 0.0, 0.0), "left_knee": (30.0, 0.0, 0.0),
             "head_x": 6.0, "head_z": 1.0, "upper_x": 8.0,
             "right_forearm_raise": 0.24, "left_forearm_raise": 0.19,
             "right_foot_location": (-0.010, -0.015, 0.000),
             "left_foot_location": (0.010, 0.035, 0.000),
             "right_foot_rotation": (18.0, 0.0, -7.0),
             "left_foot_rotation": (16.0, 0.0, 7.0),
             "right_arm_target": (-0.37, -0.02, -0.75),
             "left_arm_target": (0.41, -0.02, -0.75), "coat_sway": -1.0},
            # Landing absorption: center/hips visibly yield over planted feet.
            {"root_z": 0.000, "root_yaw": -32.0,
             "center_location": (0.0, 0.0, -0.315),
             "right_leg": (-26.0, 0.0, 2.0), "left_leg": (-22.0, 0.0, -2.0),
             "right_knee": (82.0, 0.0, 0.0), "left_knee": (74.0, 0.0, 0.0),
             "head_x": 18.0, "head_z": 0.0, "upper_x": 24.0,
             "right_forearm_raise": 0.34, "left_forearm_raise": 0.30,
             "right_foot_location": (-0.100, -0.015, 0.000),
             "left_foot_location": (0.100, 0.035, 0.000),
             "right_foot_rotation": (2.0, 0.0, -7.0),
             "left_foot_rotation": (2.0, 0.0, 7.0),
             "right_arm_target": (-0.62, -0.10, -0.15),
             "left_arm_target": (0.62, -0.10, -0.15), "coat_sway": 2.0},
            # Recover to the approved model stance before the landing hold.
            {"root_z": 0.000, "root_yaw": -15.0,
             "center_location": (0.0, 0.0, 0.000),
             "right_leg": (-5.0, 0.0, 2.5), "left_leg": (-1.0, 0.0, -1.0),
             "right_knee": (16.0, 0.0, 0.0), "left_knee": (3.0, 0.0, 0.0),
             "head_x": -2.0, "head_z": 2.0, "upper_x": 0.0,
             "right_forearm_raise": 0.86, "left_forearm_raise": 0.08,
             "right_foot_location": (0.078, -0.080, 0.010),
             "left_foot_location": (-0.016, 0.035, 0.000),
             "right_foot_rotation": (0.0, 0.0, -15.0),
             "left_foot_rotation": (0.0, 0.0, 7.0),
             "right_arm_target": (-0.14, -0.22, -1.0),
             "left_arm_target": (0.20, -0.10, -1.0), "coat_sway": 0.0},
        )
        if frame_count == 30:
            jump_positions = (
                0.0, 0.15, 0.35, 0.60, 0.80,
                1.0, 1.0, 1.15, 1.35, 1.55,
                1.75, 2.0, 2.25, 2.50, 2.75,
                3.0, 3.30, 3.60, 4.0, 4.20,
                4.50, 5.0, 5.40, 5.70, 6.0,
                6.50, 7.0, 7.0, 7.50, 8.0,
            )
            sampled = _sample_pose_position(jump_keys, jump_positions[frame_index])
        else:
            sampled = _sample_pose_path(jump_keys, frame_index, frame_count)
        pose.update(sampled)
        pose["braid_sway"] = -pose["coat_sway"]
        apex_weight = max(0.0, 1.0 - abs(progress - 0.5) * 2.0)
        morphs["smile_eyes"] = 0.10 + 0.10 * apex_weight
        morphs["smile_mouth"] = 0.12 + 0.13 * apex_weight
    elif name.startswith("FAILED_"):
        failed_columns = zip(
            (0.000, -0.012, -0.036, -0.068, -0.052, -0.026, -0.008, 0.000),
            (0.000, 0.000, -0.018, -0.040, -0.028, -0.010, 0.000, 0.000),
            (7.0, 4.0, -6.0, -16.0, -7.0, 3.0, 6.0, 7.0),
            (-4.0, -2.0, 12.0, 17.0, 8.0, -1.0, -3.0, -4.0),
            (-2.0, -1.0, 4.0, 8.0, 4.0, 8.0, 4.0, -2.0),
            (5.0, 2.0, -4.0, -8.0, -3.0, -10.0, -7.0, -6.0),
            (2.0, 1.0, 7.0, 10.0, 5.0, 3.0, 2.0, 1.0),
            (0.078, 0.066, 0.020, -0.040, 0.020, 0.072, 0.082, 0.078),
            (0.010, 0.018, 0.060, 0.090, 0.040, 0.014, 0.010, 0.010),
            (16.0, 22.0, 34.0, 42.0, 32.0, 20.0, 16.0, 16.0),
            (3.0, 5.0, 12.0, 22.0, 28.0, 16.0, 6.0, 3.0),
            (-5.0, -8.0, -14.0, -20.0, -12.0, -6.0, -4.0, -5.0),
            (-1.0, -2.0, -5.0, -8.0, -12.0, -7.0, -2.0, -1.0),
            (0.0, -6.0, 4.0, 10.0, 0.0, -4.0, 0.0, 0.0),
            (-0.016, -0.016, -0.016, -0.016, -0.006, -0.010, -0.014, -0.016),
            (0.035, 0.035, 0.035, 0.035, 0.025, 0.030, 0.034, 0.035),
            (0.86, 0.78, 0.32, 0.14, 0.42, 1.00, 0.94, 0.86),
            (0.08, 0.10, 0.28, 0.62, 0.42, 0.16, 0.10, 0.08),
            (0.0, 1.0, 5.0, 8.0, 4.0, -2.0, -1.0, 0.0),
        )
        failed_keys = tuple(
            {
                "root_dx": dx, "root_z": root_z, "lower_z": hip,
                "upper_z": upper_z, "head_x": head_x, "head_y": head_y,
                "head_z": head_z, "right_foot_x": right_foot_x,
                "right_foot_z": right_foot_z,
                "right_knee": (right_knee, 0.0, 0.0),
                "left_knee": (left_knee, 0.0, 0.0),
                "right_leg": (right_leg, 0.0, 2.5),
                "left_leg": (left_leg, 0.0, -1.0),
                "right_ankle_x": right_ankle_x,
                "left_foot_location": (left_foot_x, left_foot_y, 0.0),
                "right_forearm_raise": right_hand,
                "left_forearm_raise": left_hand, "coat_sway": coat_sway,
            }
            for (
                dx, root_z, hip, upper_z, head_x, head_y, head_z,
                right_foot_x, right_foot_z, right_knee, left_knee,
                right_leg, left_leg, right_ankle_x, left_foot_x, left_foot_y,
                right_hand, left_hand, coat_sway,
            ) in failed_columns
        )
        sampled = _sample_pose_path(failed_keys, frame_index, frame_count)
        pose["root_x"] += sampled.pop("root_dx")
        right_foot_x = sampled.pop("right_foot_x")
        right_foot_z = sampled.pop("right_foot_z")
        right_ankle_x = sampled.pop("right_ankle_x")
        pose.update(sampled)
        pose["right_foot_location"] = (right_foot_x, -0.080, right_foot_z)
        pose["right_foot_rotation"] = (right_ankle_x, 0.0, -15.0)
        pose["root_yaw"] = -15.0 + 47.0 * math.sin(math.pi * progress)
        # Arms open at the stumble, then the right hand returns to the collar.
        if progress < 0.28:
            pose["left_arm_target"] = _lerp_value(
                (0.20, -0.10, -1.0), (0.42, -0.06, -0.72), progress / 0.28
            )
        elif progress < 0.48:
            pose["left_arm_target"] = _lerp_value(
                (0.42, -0.06, -0.72), (0.62, -0.04, -0.42),
                (progress - 0.28) / 0.20,
            )
            pose["right_arm_target"] = _lerp_value(
                (-0.14, -0.22, -1.0), (-0.28, -0.12, -0.82),
                (progress - 0.28) / 0.20,
            )
        elif progress < 0.72:
            pose["left_arm_target"] = _lerp_value(
                (0.62, -0.04, -0.42), (0.46, -0.08, -0.68),
                (progress - 0.48) / 0.24,
            )
            pose["right_arm_target"] = _lerp_value(
                (-0.28, -0.12, -0.82), (-0.18, -0.24, -0.96),
                (progress - 0.48) / 0.24,
            )
        else:
            pose["right_arm_target"] = _lerp_value(
                (-0.18, -0.24, -0.96), (-0.14, -0.22, -1.0),
                (progress - 0.72) / 0.28,
            )
        pose["braid_sway"] = -pose["coat_sway"]
        surprise = max(0.0, 1.0 - abs(progress - 0.43) / 0.28) * 0.68
        if surprise > 0.04:
            morphs["surprised"] = surprise
        elif 0.68 <= progress <= 0.82:
            morphs["blink"] = 0.22
        elif progress > 0.90:
            morphs["serious"] = 0.18
            morphs["smile_mouth"] = 0.08
    elif name.startswith("WAITING_"):
        waiting_keys = (
            {"root_dx": -0.020, "root_z": 0.000, "lower_z": 10.0,
             "head_x": 2.0, "head_y": -14.0, "head_z": 3.0,
             "right_foot_location": (0.090, -0.086, 0.018),
             "right_leg": (-5.0, 0.0, 2.5), "right_knee": (18.0, 0.0, 0.0),
             "left_knee": (3.0, 0.0, 0.0),
             "right_foot_rotation": (0.0, 0.0, -16.0),
             "right_forearm_raise": 0.90, "upper_z": -8.0,
             "left_forearm_raise": 0.08, "coat_sway": 0.0},
            {"root_dx": -0.030, "root_z": -0.004, "lower_z": 11.0,
             "head_x": 2.0, "head_y": -14.0, "head_z": 3.0,
             "right_foot_location": (0.104, -0.086, 0.040),
             "right_leg": (-7.0, 0.0, 2.5), "right_knee": (22.0, 0.0, 0.0),
             "left_knee": (4.0, 0.0, 0.0),
             "right_foot_rotation": (-4.0, 0.0, -16.0),
             "right_forearm_raise": 0.94, "upper_z": -10.0,
             "left_forearm_raise": 0.10, "coat_sway": -1.0},
            {"root_dx": -0.034, "root_z": -0.012, "lower_z": 12.0,
             "head_x": 3.0, "head_y": -12.0, "head_z": 3.0,
             "right_foot_location": (0.114, -0.086, 0.058),
             "right_leg": (-10.0, 0.0, 2.5), "right_knee": (26.0, 0.0, 0.0),
             "left_knee": (6.0, 0.0, 0.0),
             "right_foot_rotation": (4.0, 0.0, -16.0),
             "right_forearm_raise": 0.96, "upper_z": -12.0,
             "left_forearm_raise": 0.12, "coat_sway": -2.0},
            {"root_dx": -0.012, "root_z": 0.000, "lower_z": 7.0,
             "head_x": -1.0, "head_y": 0.0, "head_z": 0.0,
             "right_foot_location": (0.104, -0.086, 0.034),
             "right_leg": (-7.0, 0.0, 2.5), "right_knee": (22.0, 0.0, 0.0),
             "left_knee": (5.0, 0.0, 0.0),
             "right_foot_rotation": (0.0, 0.0, -16.0),
             "right_forearm_raise": 1.00, "upper_z": -5.0,
             "left_forearm_raise": 0.20, "coat_sway": 0.0},
            {"root_dx": 0.020, "root_z": 0.008, "lower_z": 5.0,
             "head_x": -2.0, "head_y": 9.0, "head_z": 6.0,
             "right_foot_location": (0.124, -0.086, 0.060),
             "right_leg": (-12.0, 0.0, 2.5), "right_knee": (28.0, 0.0, 0.0),
             "left_knee": (7.0, 0.0, 0.0),
             "right_foot_rotation": (8.0, 0.0, -16.0),
             "right_forearm_raise": 1.00, "upper_z": 2.0,
             "left_forearm_raise": 0.36, "coat_sway": 3.0},
            {"root_dx": 0.004, "root_z": 0.002, "lower_z": 8.0,
             "head_x": 0.0, "head_y": -8.0, "head_z": 3.0,
             "right_foot_location": (0.102, -0.086, 0.032),
             "right_leg": (-8.0, 0.0, 2.5), "right_knee": (22.0, 0.0, 0.0),
             "left_knee": (4.0, 0.0, 0.0),
             "right_foot_rotation": (2.0, 0.0, -16.0),
             "right_forearm_raise": 0.94, "upper_z": -2.0,
             "left_forearm_raise": 0.18, "coat_sway": 1.0},
        )
        sampled = _sample_pose_cycle(waiting_keys, frame_index, frame_count)
        pose["root_x"] += sampled.pop("root_dx")
        pose.update(sampled)
        pose["root_yaw"] = 30.0
        pose["braid_sway"] = -pose["coat_sway"]
        morphs["serious"] = 0.12
        waiting_position = frame_index * 6 / max(frame_count, 1)
        direct_weight = max(0.0, 1.0 - abs(waiting_position - 3.0) / 0.8)
        flick_weight = max(0.0, 1.0 - abs(waiting_position - 4.0) / 0.8)
        if direct_weight > 0.05:
            morphs["smile_mouth"] = 0.18 * direct_weight
        if flick_weight > 0.05:
            morphs["pupil_right"] = 0.24 * flick_weight
    elif name.startswith("RUNNING_"):
        _apply_work_step(pose, frame_index, frame_count)
        pose["head_y"] = 7.0 - 3.0 * math.sin(phase)
        pose["head_z"] = -1.5 * math.sin(phase)
        morphs["serious"] = 0.26
    elif name.startswith("REVIEW_"):
        review_keys = (
            {"root_dx": -0.025, "root_z": -0.006, "lower_z": -9.0,
             "upper_x": 10.0, "upper_z": 8.0, "head_x": 12.0,
             "head_y": -14.0, "head_z": 2.0, "right_forearm_raise": 0.98,
             "right_leg": (-2.0, 0.0, 2.5), "left_leg": (-8.0, 0.0, -1.0),
             "right_knee": (5.0, 0.0, 0.0), "left_knee": (18.0, 0.0, 0.0),
             "left_foot_location": (-0.070, -0.082, 0.012),
             "left_foot_rotation": (2.0, 0.0, 14.0),
             "left_forearm_raise": 0.34, "coat_sway": 0.0,
             "serious": 0.40},
            {"root_dx": -0.012, "root_z": 0.000, "lower_z": -8.0,
             "upper_x": 9.0, "upper_z": 5.0, "head_x": 11.0,
             "head_y": 2.0, "head_z": 0.0, "right_forearm_raise": 1.00,
             "right_leg": (-3.0, 0.0, 2.5), "left_leg": (-10.0, 0.0, -1.0),
             "right_knee": (6.0, 0.0, 0.0), "left_knee": (22.0, 0.0, 0.0),
             "left_foot_location": (-0.076, -0.084, 0.020),
             "left_foot_rotation": (4.0, 0.0, 14.0),
             "left_forearm_raise": 0.38, "coat_sway": 1.0,
             "serious": 0.38},
            {"root_dx": 0.006, "root_z": 0.006, "lower_z": -10.0,
             "upper_x": 8.0, "upper_z": 2.0, "head_x": 10.0,
             "head_y": 15.0, "head_z": -2.0, "right_forearm_raise": 1.00,
             "right_leg": (-5.0, 0.0, 2.5), "left_leg": (-13.0, 0.0, -1.0),
             "right_knee": (8.0, 0.0, 0.0), "left_knee": (26.0, 0.0, 0.0),
             "left_foot_location": (-0.084, -0.086, 0.030),
             "left_foot_rotation": (6.0, 0.0, 14.0),
             "left_forearm_raise": 0.42, "coat_sway": 2.0,
             "serious": 0.40},
            {"root_dx": 0.020, "root_z": 0.012, "lower_z": -6.0,
             "upper_x": 2.0, "upper_z": -2.0, "head_x": -2.0,
             "head_y": 0.0, "head_z": 0.0, "right_forearm_raise": 1.00,
             "right_leg": (-6.0, 0.0, 2.5), "left_leg": (-9.0, 0.0, -1.0),
             "right_knee": (10.0, 0.0, 0.0), "left_knee": (20.0, 0.0, 0.0),
             "left_foot_location": (-0.076, -0.082, 0.016),
             "left_foot_rotation": (3.0, 0.0, 14.0),
             "left_forearm_raise": 0.34, "coat_sway": 0.0,
             "serious": 0.25},
            {"root_dx": 0.002, "root_z": 0.000, "lower_z": -10.0,
             "upper_x": 7.0, "upper_z": 7.0, "head_x": 6.0,
             "head_y": -17.0, "head_z": 3.0, "right_forearm_raise": 0.90,
             "right_leg": (-4.0, 0.0, 2.5), "left_leg": (-6.0, 0.0, -1.0),
             "right_knee": (7.0, 0.0, 0.0), "left_knee": (16.0, 0.0, 0.0),
             "left_foot_location": (-0.062, -0.078, 0.006),
             "left_foot_rotation": (0.0, 0.0, 14.0),
             "left_forearm_raise": 0.26, "coat_sway": -2.0,
             "serious": 0.34},
            {"root_dx": -0.018, "root_z": -0.004, "lower_z": -9.0,
             "upper_x": 10.0, "upper_z": 9.0, "head_x": 10.0,
             "head_y": -8.0, "head_z": 2.0, "right_forearm_raise": 0.96,
             "right_leg": (-2.0, 0.0, 2.5), "left_leg": (-7.0, 0.0, -1.0),
             "right_knee": (5.0, 0.0, 0.0), "left_knee": (17.0, 0.0, 0.0),
             "left_foot_location": (-0.066, -0.080, 0.008),
             "left_foot_rotation": (1.0, 0.0, 14.0),
             "left_forearm_raise": 0.30, "coat_sway": -1.0,
             "serious": 0.38},
        )
        sampled = _sample_pose_cycle(review_keys, frame_index, frame_count)
        pose["root_x"] += sampled.pop("root_dx")
        serious = sampled.pop("serious")
        pose.update(sampled)
        pose["root_yaw"] = -32.0
        pose["right_foot_location"] = (0.018, 0.045, 0.0)
        pose["right_foot_rotation"] = (0.0, 0.0, -8.0)
        pose["right_arm_target"] = (-0.18, -0.26, -0.92)
        pose["left_arm_target"] = (0.30, -0.18, -0.78)
        pose["braid_sway"] = -pose["coat_sway"]
        morphs["serious"] = serious
        review_position = frame_index * 6 / max(frame_count, 1)
        review_key = min(5, round(review_position) % 6)
        if review_key == 0:
            morphs["pupil_left"] = 0.28
            morphs["pupil_down"] = 0.22
        elif review_key in (1, 2):
            morphs["pupil_right"] = 0.35 if review_key == 1 else 0.42
        elif review_key == 3:
            morphs["smile_mouth"] = 0.08
        elif review_key == 5:
            morphs["pupil_down"] = 0.20
    elif name.startswith("LOOK_"):
        direction_index, transition_index = divmod(frame_index, 4)
        _apply_idle_key(pose, 0)
        morphs["serious"] = 0.10
        eased = (0.0, 0.26, 0.74, 1.0)[transition_index]
        if direction_index == 0:  # up
            pose["head_x"] += -22.0 * eased
            pose["head_y"] += -5.0 * eased
            if eased > 0.0:
                morphs["pupil_up"] = eased
        elif direction_index == 1:  # screen right
            pose["head_y"] += -35.0 * eased
            pose["head_z"] += -8.0 * eased
            if eased > 0.0:
                morphs["pupil_right"] = eased
        elif direction_index == 2:  # down
            pose["head_x"] += 28.0 * eased
            pose["head_y"] += -3.0 * eased
            if eased > 0.0:
                morphs["pupil_down"] = eased
        else:  # screen left
            pose["head_y"] += 25.0 * eased
            pose["head_z"] += 7.0 * eased
            if eased > 0.0:
                morphs["pupil_left"] = eased

    return pose


def _bone(armature: Any, *names: str) -> Any:
    for name in names:
        if name in armature.pose.bones:
            return armature.pose.bones[name]
    raise RuntimeError(f"required MMD bone not found: {' / '.join(names)}")


def _optional_bone(armature: Any, *names: str) -> Any | None:
    for name in names:
        if name in armature.pose.bones:
            return armature.pose.bones[name]
    return None


def _look_at(obj: Any, target: Any) -> None:
    obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()


def _has_safe_padding(
    pixels: Any,
    width: int,
    height: int,
    margin: int = 2,
    alpha_threshold: float = 1.0 / 255.0,
) -> bool:
    """Return whether every edge keeps a transparent safety margin."""
    for y in range(height):
        for x in range(width):
            if margin <= x < width - margin and margin <= y < height - margin:
                continue
            if pixels[(y * width + x) * 4 + 3] > alpha_threshold:
                return False
    return True


def _align_bone(armature: Any, pose_bone: Any, target: tuple[float, float, float]) -> None:
    from mathutils import Vector

    rest_bone = armature.data.bones[pose_bone.name]
    rest_direction = (rest_bone.tail_local - rest_bone.head_local).normalized()
    armature_rotation = rest_direction.rotation_difference(Vector(target).normalized()).to_matrix()
    rest_basis = rest_bone.matrix_local.to_3x3()
    local_rotation = rest_basis.inverted() @ armature_rotation @ rest_basis
    pose_bone.rotation_mode = "QUATERNION"
    pose_bone.rotation_quaternion = local_rotation.to_quaternion()


def _align_posed_bone(pose_bone: Any, target: tuple[float, float, float]) -> None:
    from mathutils import Matrix, Vector

    head = pose_bone.head.copy()
    current = (pose_bone.tail - pose_bone.head).normalized()
    rotation = current.rotation_difference(Vector(target).normalized()).to_matrix().to_4x4()
    pose_bone.matrix = (
        Matrix.Translation(head)
        @ rotation
        @ Matrix.Translation(-head)
        @ pose_bone.matrix
    )


def _enable_mmd_tools(bpy: Any, args: argparse.Namespace) -> None:
    if args.mmd_python_modules is not None:
        sys.path.insert(0, str(args.mmd_python_modules.resolve()))
    if args.mmd_tools_dir is not None:
        sys.path.insert(0, str(args.mmd_tools_dir.resolve().parent))
    try:
        bpy.ops.preferences.addon_enable(module=args.mmd_module)
    except RuntimeError as error:
        raise RuntimeError(
            "mmd_tools could not be enabled; install the official Blender extension "
            "or pass --mmd-tools-dir and --mmd-python-modules"
        ) from error


def _import_model(bpy: Any, args: argparse.Namespace) -> tuple[Any, Any]:
    _enable_mmd_tools(bpy, args)
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    # The public operator always reports the absolute input path even when its
    # log level is WARNING. Use the same official importer implementation
    # directly so default headless output does not disclose local asset paths.
    importer_module = importlib.import_module(f"{args.mmd_module}.core.pmx.importer")
    translations_module = importlib.import_module(f"{args.mmd_module}.translations")
    previous_log_level = logging.getLogger().level
    logging.getLogger().setLevel(logging.WARNING)
    try:
        importer_module.PMXImporter().execute(
            filepath=str(args.pmx.resolve()),
            types={"MESH", "ARMATURE", "MORPHS"},
            scale=args.scale,
            clean_model=False,
            remove_doubles=False,
            import_adduv2_as_vertex_colors=False,
            fix_bone_order=True,
            fix_ik_links=False,
            ik_loop_factor=5,
            apply_bone_fixed_axis=False,
            rename_LR_bones=False,
            use_underscore=False,
            bone_disp_mode="OCTAHEDRAL",
            translator=translations_module.DictionaryEnum.get_translator("DISABLED"),
            use_mipmap=True,
            sph_blend_factor=1.0,
            spa_blend_factor=1.0,
        )
    finally:
        logging.getLogger().setLevel(previous_log_level)
    roots = [obj for obj in bpy.context.scene.objects if getattr(obj, "mmd_type", None) == "ROOT"]
    if not roots:
        raise RuntimeError("PMX import produced no MMD root")
    armatures = [obj for obj in bpy.context.scene.objects if obj.type == "ARMATURE"]
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not armatures or not meshes:
        raise RuntimeError("PMX import did not produce an armature and mesh")
    missing = [
        image.name
        for image in bpy.data.images
        if image.source == "FILE" and (image.size[0] == 0 or image.size[1] == 0)
    ]
    if missing:
        raise RuntimeError("PMX texture(s) failed to load: " + ", ".join(missing[:4]))
    main_mesh = max(meshes, key=lambda obj: len(obj.data.vertices))
    armature = armatures[0]
    for obj in meshes:
        if obj != main_mesh:
            obj.hide_render = True
    return armature, main_mesh


def _remove_mask_materials(args: argparse.Namespace, mesh: Any) -> None:
    """Apply the model-authored `マスク消し` result without editing the PMX."""
    material_module = importlib.import_module(f"{args.mmd_module}.core.material")
    fn_material = material_module.FnMaterial
    found: set[str] = set()
    for slot in mesh.material_slots:
        material = slot.material
        if material is None or material.name not in {"マスク", "マスク瞳"}:
            continue
        found.add(material.name)
        material.mmd_material.alpha = 0.0
        fn_material(material).update_alpha()
    missing = {"マスク", "マスク瞳"}.difference(found)
    if missing:
        raise RuntimeError("mask material(s) not found: " + ", ".join(sorted(missing)))


def _write_credits(args: argparse.Namespace) -> None:
    """Write explicit, caller-supplied provenance without persisting local paths."""
    if Path(args.provenance_name).expanduser().is_absolute():
        raise ValueError("--provenance-name must be a descriptive label, not an absolute path")
    lines = [
        "Local derivative render.",
        f"Source: {args.provenance_name}",
    ]
    if args.model_page:
        lines.append(f"Model page: {args.model_page}")
    lines.extend(f"Credit: {credit}" for credit in args.credit)
    lines.append(f"Rights: {args.rights_note}")
    (args.output_dir / "CREDITS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _reset_rig(armature: Any, mesh: Any) -> None:
    armature.location = (0.0, 0.0, 0.0)
    armature.rotation_mode = "XYZ"
    armature.rotation_euler = (0.0, 0.0, math.radians(-11.0))
    for pose_bone in armature.pose.bones:
        pose_bone.matrix_basis.identity()
    right_arm = _bone(armature, "腕.R", "右腕")
    left_arm = _bone(armature, "腕.L", "左腕")
    _align_bone(armature, right_arm, (-0.13, -0.20, -1.0))
    _align_bone(armature, left_arm, (0.20, -0.10, -1.0))
    shape_keys = mesh.data.shape_keys
    if shape_keys is not None:
        if shape_keys.animation_data is not None:
            for driver in shape_keys.animation_data.drivers:
                driver.mute = True
        for key in shape_keys.key_blocks:
            key.value = 0.0


def _set_rotation(pose_bone: Any, degrees: tuple[float, float, float]) -> None:
    pose_bone.rotation_mode = "XYZ"
    pose_bone.rotation_euler = tuple(math.radians(value) for value in degrees)


def apply_pose(armature: Any, mesh: Any, pose: dict[str, Any]) -> None:
    import bpy
    from mathutils import Vector

    _reset_rig(armature, mesh)
    armature.location = (pose["root_x"], 0.0, pose["root_z"])
    armature.rotation_euler.z = math.radians(pose["root_yaw"])
    center_bone = _bone(armature, "センター")
    center_rest_basis = armature.data.bones[center_bone.name].matrix_local.to_3x3()
    center_bone.location = center_rest_basis.inverted() @ Vector(
        pose["center_location"]
    )
    _set_rotation(
        _bone(armature, "下半身"),
        (pose["lower_x"], 0.0, pose["lower_z"]),
    )
    _set_rotation(_bone(armature, "足.R", "右足"), pose["right_leg"])
    _set_rotation(_bone(armature, "足.L", "左足"), pose["left_leg"])
    _set_rotation(_bone(armature, "ひざ.R", "右ひざ"), pose["right_knee"])
    _set_rotation(_bone(armature, "ひざ.L", "左ひざ"), pose["left_knee"])
    right_foot = _bone(armature, "足ＩＫ.R", "足IK.R", "右足ＩＫ", "右足IK")
    left_foot = _bone(armature, "足ＩＫ.L", "足IK.L", "左足ＩＫ", "左足IK")
    right_foot.location = pose["right_foot_location"]
    left_foot.location = pose["left_foot_location"]
    _set_rotation(right_foot, pose["right_foot_rotation"])
    _set_rotation(left_foot, pose["left_foot_rotation"])
    right_arm = _bone(armature, "腕.R", "右腕")
    left_arm = _bone(armature, "腕.L", "左腕")
    _align_bone(armature, right_arm, pose["right_arm_target"])
    _align_bone(armature, left_arm, pose["left_arm_target"])
    upper1 = _bone(armature, "上半身")
    upper2 = _optional_bone(armature, "上半身2")
    head = _bone(armature, "頭")
    if upper2 is None:
        _set_rotation(
            upper1,
            (
                pose["upper1_x"] + pose["upper_x"],
                pose["upper_y"],
                pose["upper_z"],
            ),
        )
    else:
        _set_rotation(upper1, (pose["upper1_x"], 0.0, 0.0))
        _set_rotation(
            upper2,
            (pose["upper_x"], pose["upper_y"], pose["upper_z"]),
        )
    _set_rotation(head, (pose["head_x"], pose["head_y"], pose["head_z"]))
    bpy.context.view_layer.update()
    right_forearm_raise = pose["right_forearm_raise"]
    if right_forearm_raise > 0.0:
        right_elbow = _bone(armature, "ひじ.R", "右ひじ")
        current = (right_elbow.tail - right_elbow.head).normalized()
        raised = Vector((0.75, -0.35, 0.50)).normalized()
        target = current.lerp(raised, min(1.0, right_forearm_raise)).normalized()
        _align_posed_bone(right_elbow, tuple(target))
    left_forearm_raise = pose["left_forearm_raise"]
    if left_forearm_raise > 0.0:
        left_elbow = _bone(armature, "ひじ.L", "左ひじ")
        current = (left_elbow.tail - left_elbow.head).normalized()
        raised = Vector((-0.75, -0.35, 0.50)).normalized()
        target = current.lerp(raised, min(1.0, left_forearm_raise)).normalized()
        _align_posed_bone(left_elbow, tuple(target))

    # Author a restrained deterministic follow-through. These are model-safe
    # optional roots: other compatible PMX models may omit them without losing
    # the core body performance.
    coat_sway = pose["coat_sway"]
    braid_sway = pose["braid_sway"]
    for bone_name, rotation in (
        ("コート前1.R", (0.0, coat_sway, coat_sway * 0.35)),
        ("コート前1.L", (0.0, -coat_sway, -coat_sway * 0.35)),
        ("おさげ1.R", (0.0, braid_sway, braid_sway * 0.40)),
        ("おさげ1.L", (0.0, -braid_sway, -braid_sway * 0.40)),
    ):
        optional = _optional_bone(armature, bone_name)
        if optional is not None:
            _set_rotation(optional, rotation)

    if mesh.data.shape_keys is None:
        return
    keys = mesh.data.shape_keys.key_blocks
    for semantic_name, value in pose["morphs"].items():
        actual_name = MORPH_NAMES[semantic_name]
        if actual_name in keys:
            keys[actual_name].value = min(1.0, max(0.0, value))


def _add_ground_reference(
    bpy: Any,
    scene: Any,
    center: Any,
    width: float,
    depth: float,
    height: float,
    z_min: float,
    y_max: float,
) -> None:
    """Add a subtle fixed alpha ellipse so contact and flight read without a floor."""
    segments = 40
    radius_x = max(width * 0.38, height * 0.15)
    radius_z = height * 0.012
    ground_y = y_max + depth * 0.12
    ground_z = z_min - radius_z * 1.05
    vertices = [(center.x, ground_y, ground_z)]
    vertices.extend(
        (
            center.x + radius_x * math.cos(2.0 * math.pi * index / segments),
            ground_y,
            ground_z + radius_z * math.sin(2.0 * math.pi * index / segments),
        )
        for index in range(segments)
    )
    faces = [
        (0, index + 1, (index + 1) % segments + 1)
        for index in range(segments)
    ]
    shadow_mesh = bpy.data.meshes.new("CodexPetGroundCueMesh")
    shadow_mesh.from_pydata(vertices, [], faces)
    shadow_mesh.update()
    shadow = bpy.data.objects.new("CodexPetGroundCue", shadow_mesh)
    scene.collection.objects.link(shadow)

    material = bpy.data.materials.new("CodexPetGroundCueMaterial")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    transparent = nodes.new("ShaderNodeBsdfTransparent")
    dark = nodes.new("ShaderNodeBsdfPrincipled")
    dark.inputs["Base Color"].default_value = (0.04, 0.055, 0.075, 1.0)
    dark.inputs["Roughness"].default_value = 1.0
    mixed = nodes.new("ShaderNodeMixShader")
    mixed.inputs[0].default_value = 0.28
    links.new(transparent.outputs[0], mixed.inputs[1])
    links.new(dark.outputs[0], mixed.inputs[2])
    links.new(mixed.outputs[0], output.inputs[0])
    try:
        material.surface_render_method = "DITHERED"
    except (AttributeError, TypeError):
        try:
            material.blend_method = "BLEND"
        except AttributeError:
            pass
    shadow.data.materials.append(material)


def _configure_scene(bpy: Any, armature: Any, mesh: Any) -> Any:
    from mathutils import Vector

    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = FRAME_W
    scene.render.resolution_y = FRAME_H
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 20
    scene.render.filter_size = 1.25
    scene.world.color = (0.08, 0.08, 0.08)

    _reset_rig(armature, mesh)
    bpy.context.view_layer.update()
    evaluated = mesh.evaluated_get(bpy.context.evaluated_depsgraph_get())
    corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    x_min, x_max = min(point.x for point in corners), max(point.x for point in corners)
    y_min, y_max = min(point.y for point in corners), max(point.y for point in corners)
    z_min, z_max = min(point.z for point in corners), max(point.z for point in corners)
    center = Vector(((x_min + x_max) / 2, (y_min + y_max) / 2, (z_min + z_max) / 2))
    width, depth, height = x_max - x_min, y_max - y_min, z_max - z_min
    _add_ground_reference(
        bpy, scene, center, width, depth, height, z_min, y_max
    )

    camera_data = bpy.data.cameras.new("CodexPetCamera")
    camera = bpy.data.objects.new("CodexPetCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.data.type = "PERSP"
    camera.data.lens = 70.0
    camera.data.sensor_fit = "VERTICAL"
    camera.data.sensor_height = 32.0
    camera_distance = height * 3.05
    camera.location = Vector(
        (
            center.x - width * 0.12,
            center.y - camera_distance,
            center.z + height * 0.03,
        )
    )
    _look_at(camera, center)
    scene.camera = camera

    light_data = bpy.data.lights.new("CodexPetKey", "AREA")
    light_data.energy = 700
    light_data.shape = "DISK"
    light_data.size = max(width, height) * 1.5
    light = bpy.data.objects.new("CodexPetKey", light_data)
    scene.collection.objects.link(light)
    light.location = Vector((center.x + width * 0.3, center.y - depth - 3.0, center.z + height * 0.4))
    _look_at(light, center)
    return scene


def main() -> None:
    args = parse_args(blender_script_args(sys.argv))
    if not args.pmx.is_file():
        raise SystemExit("PMX input file was not found")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    frame_specs, action_ranges = CONVERTER.build_frame_contract(args.motion_profile)
    frame_context: dict[str, tuple[int, int]] = {}
    for _, first, count in action_ranges:
        for local_index, (name, _, _) in enumerate(frame_specs[first : first + count]):
            frame_context[name] = (local_index, count)
    selected = None
    if args.only:
        selected = {name.strip().upper() for name in args.only.split(",") if name.strip()}
        unknown = selected.difference(frame_context)
        if unknown:
            raise SystemExit("unknown frame name(s): " + ", ".join(sorted(unknown)))

    import bpy

    armature, mesh = _import_model(bpy, args)
    if not args.keep_mask:
        _remove_mask_materials(args, mesh)
    scene = _configure_scene(bpy, armature, mesh)
    rendered = 0
    for name, _, _ in frame_specs:
        if selected is not None and name not in selected:
            continue
        frame_index, frame_count = frame_context[name]
        apply_pose(armature, mesh, pose_for_frame(name, frame_index, frame_count))
        bpy.context.view_layer.update()
        scene.render.filepath = str(args.output_dir / CONVERTER.frame_filename(name))
        bpy.ops.render.render(write_still=True)
        rendered_image = bpy.data.images.load(scene.render.filepath, check_existing=False)
        try:
            if not _has_safe_padding(rendered_image.pixels, FRAME_W, FRAME_H):
                raise RuntimeError(
                    f"rendered frame lacks transparent edge padding: {name}"
                )
        finally:
            bpy.data.images.remove(rendered_image)
        rendered += 1

    _write_credits(args)
    (args.output_dir / "motion_manifest.json").write_text(
        json.dumps(CONVERTER.motion_manifest(args.motion_profile), indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"rendered {rendered} MMD frame(s) to {args.output_dir}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as error:
        print(f"MMD render failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
