#!/usr/bin/env python3
"""Generate private raw or JPEG+alpha frames for the ESP32-P4 Codex Pet target.

The input can be either the legacy Codex v2 8x11 atlas or a directory containing
one RGBA image per authored motion frame. The default smooth profile and legacy
compatibility playback contract use 152 slots; legacy 73-frame sources are
resampled through the asset table so the image bytes remain stored only once.
Dynamic manifest-v2 sources may instead define 1-65535 frames. The output is a C
translation unit kept local/gitignored unless redistribution rights for the
source artwork are explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

CELL_W = 192
CELL_H = 208
CROP_X = 20
CROP_Y = 2
CROP_W = 152
CROP_H = 204
FRAME_W = CROP_W
FRAME_H = CROP_H
FRAME_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")

# Codex Pet v2 atlas contract. Rows 9-10 form one clockwise 16-frame action.
ACTION_SPECS = (
    ("IDLE", ((0, 6),)),
    ("RUNNING_RIGHT", ((1, 8),)),
    ("RUNNING_LEFT", ((2, 8),)),
    ("WAVING", ((3, 4),)),
    ("JUMPING", ((4, 5),)),
    ("FAILED", ((5, 8),)),
    ("WAITING", ((6, 6),)),
    ("RUNNING", ((7, 6),)),
    ("REVIEW", ((8, 6),)),
    ("LOOK", ((9, 8), (10, 8))),
)
ACTION_ORDER = tuple(action for action, _ in ACTION_SPECS)
SMOOTH_ACTION_COUNTS = {
    "IDLE": 12,
    "RUNNING_RIGHT": 8,
    "RUNNING_LEFT": 8,
    "WAVING": 8,
    "JUMPING": 30,
    "FAILED": 18,
    "WAITING": 14,
    "RUNNING": 24,
    "REVIEW": 14,
    "LOOK": 16,
}
SMOOTH_FIRMWARE_DURATIONS = {
    "IDLE": [120] * 10,
    "BLINK": [45] * 10 + [70, 90],
    "RUN": [90] * 8,
    "WAVE": [180, 180, 180, 180, 180, 260, 220, 300],
    "JUMP": [33] * 29 + [180],
    "FAILED": [50] * 17 + [300],
    "WAITING": [65] * 13 + [180],
    "RUNNING": [30] * 24,
    "REVIEW": [65] * 13 + [180],
    "EXCITED": [33] * 29 + [150],
}
COMPAT_FIRMWARE_DURATIONS = {
    "IDLE": [700, 500, 450, 500],
    "BLINK": [120, 120, 120, 120, 70, 90],
    "RUN": [220, 170, 190, 220, 170, 190, 220, 190],
    "WAVE": [90, 90, 90, 180],
    "JUMP": [100, 90, 140, 100, 200],
    "FAILED": [110, 110, 120, 160, 130, 220, 180, 420],
    "WAITING": [520, 300, 160, 620, 180, 300],
    "RUNNING": [240, 180, 240, 240, 180, 240],
    "REVIEW": [420, 300, 300, 620, 300, 400],
    "EXCITED": [95, 95, 95, 95, 180],
}
LOOK_DIRECTIONS = (
    "000",
    "022.5",
    "045",
    "067.5",
    "090",
    "112.5",
    "135",
    "157.5",
    "180",
    "202.5",
    "225",
    "247.5",
    "270",
    "292.5",
    "315",
    "337.5",
)

MOTION_ENUMS = {
    action: f"PET_MOTION_{action}" for action in ACTION_ORDER
}
TIMING_ORDER = (
    "IDLE",
    "BLINK",
    "RUN",
    "WAVE",
    "JUMP",
    "FAILED",
    "WAITING",
    "RUNNING",
    "REVIEW",
    "LOOK",
    "EXCITED",
    "SLEEPY",
    "HOLD",
)
LEGACY_TIMING_DEFAULTS = {
    "LOOK": [65, 65, 85, 650],
    "SLEEPY": [240, 260, 300, 420, 700],
    "HOLD": [850],
}


def build_frame_contract(profile: str = "smooth") -> tuple[
    tuple[tuple[str, int, int], ...], tuple[tuple[str, int, int], ...]
]:
    if profile == "smooth":
        frames: list[tuple[str, int, int]] = []
        ranges: list[tuple[str, int, int]] = []
        for action in ACTION_ORDER:
            first = len(frames)
            count = SMOOTH_ACTION_COUNTS[action]
            for index in range(count):
                if action == "LOOK":
                    suffix = LOOK_DIRECTIONS[index].replace(".", "_")
                else:
                    suffix = str(index)
                frames.append((f"{action}_{suffix}", -1, -1))
            ranges.append((action, first, count))
        return tuple(frames), tuple(ranges)
    if profile != "compat":
        raise ValueError(f"unknown motion profile: {profile}")

    frames: list[tuple[str, int, int]] = []
    ranges: list[tuple[str, int, int]] = []
    look_index = 0
    for action, rows in ACTION_SPECS:
        first = len(frames)
        for row, count in rows:
            for column in range(count):
                if action == "LOOK":
                    suffix = LOOK_DIRECTIONS[look_index].replace(".", "_")
                    look_index += 1
                else:
                    suffix = str(column)
                frames.append((f"{action}_{suffix}", row, column))
        ranges.append((action, first, len(frames) - first))
    if look_index != len(LOOK_DIRECTIONS):
        raise RuntimeError("look direction count does not match the atlas rows")
    return tuple(frames), tuple(ranges)


FRAME_SPECS, ACTION_RANGES = build_frame_contract("smooth")
ATLAS_FRAME_SPECS, ATLAS_ACTION_RANGES = build_frame_contract("compat")


def motion_manifest(profile: str) -> dict[str, Any]:
    frames, ranges = build_frame_contract(profile)
    durations = (
        SMOOTH_FIRMWARE_DURATIONS
        if profile == "smooth"
        else COMPAT_FIRMWARE_DURATIONS
    )
    return {
        "version": 1,
        "profile": profile,
        "width": FRAME_W,
        "height": FRAME_H,
        "idle_loop_count": len(durations["IDLE"]),
        "frames": [name for name, _, _ in frames],
        "actions": [
            {"name": action, "first": first, "count": count}
            for action, first, count in ranges
        ],
        "firmware_durations_ms": {
            name: list(values) for name, values in durations.items()
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--spritesheet", type=Path)
    source.add_argument(
        "--frames-dir",
        type=Path,
        help="directory containing one 152x204 RGBA PNG for every frame",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("esp32-p4/main/pet_generated.c"),
    )
    parser.add_argument(
        "--motion-profile",
        choices=("auto", "compat", "smooth"),
        default="auto",
        help="frame contract for --frames-dir; auto reads motion_manifest.json",
    )
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument(
        "--encoding",
        choices=("raw", "jpeg-alpha-rle"),
        default="raw",
        help="stored frame encoding (default: raw RGB565A8)",
    )
    parser.add_argument(
        "--jpeg-qscale",
        type=int,
        choices=range(1, 32),
        default=2,
        metavar="1-31",
        help="ffmpeg MJPEG qscale; lower is higher quality (default: 2)",
    )
    parser.add_argument(
        "--alpha-bits",
        type=int,
        choices=(4, 8),
        default=8,
        help="alpha precision before RLE (default: exact 8-bit)",
    )
    return parser.parse_args()


def decode_rgba(ffmpeg: str, source: Path, row: int, column: int) -> bytes:
    x = column * CELL_W + CROP_X
    y = row * CELL_H + CROP_Y
    vf = f"crop={CROP_W}:{CROP_H}:{x}:{y},format=rgba"
    result = subprocess.run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            vf,
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    expected = FRAME_W * FRAME_H * 4
    if len(result.stdout) != expected:
        raise RuntimeError(f"decoded {len(result.stdout)} bytes; expected {expected}")
    return result.stdout


def frame_filename(name: str) -> str:
    return f"{name.lower()}.png"


def frame_path(frames_dir: Path, name: str) -> Path:
    root = frames_dir.resolve()
    candidate = (root / frame_filename(name)).resolve()
    if candidate.parent != root:
        raise ValueError(f"frame path escapes frames directory: {candidate}")
    if not candidate.is_file():
        raise FileNotFoundError(f"frame not found: {candidate}")
    return candidate


def decode_rgba_frame(ffmpeg: str, source: Path) -> bytes:
    result = subprocess.run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-vf",
            "format=rgba",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    expected = FRAME_W * FRAME_H * 4
    if len(result.stdout) != expected:
        raise RuntimeError(
            f"decoded {len(result.stdout)} bytes from {source}; expected {expected} "
            f"for an exact {FRAME_W}x{FRAME_H} frame"
        )
    return result.stdout


def rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def rgb565a8_map(rgba: bytes) -> bytes:
    # LVGL RGB565A8 stores all RGB565 pixels first, followed by a full alpha map.
    colours = bytearray()
    alpha = bytearray()
    for offset in range(0, len(rgba), 4):
        r, g, b, a = rgba[offset : offset + 4]
        value = rgb565(r, g, b)
        colours.extend((value & 0xFF, value >> 8))
        alpha.append(a)
    return bytes(colours + alpha)


def alpha_rle_encode(rgba: bytes, bits: int = 8) -> bytes:
    """Encode RGBA alpha as [run:uint8, value:uint8] pairs."""
    if bits not in (4, 8):
        raise ValueError("alpha bits must be 4 or 8")
    if len(rgba) % 4:
        raise ValueError("RGBA payload length must be divisible by 4")
    alpha = rgba[3::4]
    if bits == 4:
        alpha = bytes(min(15, (value + 8) // 17) * 17 for value in alpha)
    encoded = bytearray()
    if not alpha:
        return bytes(encoded)
    value = alpha[0]
    run = 0
    for current in alpha:
        if current == value and run < 255:
            run += 1
            continue
        encoded.extend((run, value))
        value = current
        run = 1
    encoded.extend((run, value))
    return bytes(encoded)


def encode_padded_jpeg(
    ffmpeg: str,
    rgba: bytes,
    qscale: int = 2,
) -> bytes:
    """Encode a 152x204 RGBA frame in a black-padded 160x208 baseline JPEG."""
    expected = FRAME_W * FRAME_H * 4
    if len(rgba) != expected:
        raise ValueError(f"RGBA payload is {len(rgba)} bytes; expected {expected}")
    if not 1 <= qscale <= 31:
        raise ValueError("JPEG qscale must be in the range 1-31")
    result = subprocess.run(
        [
            ffmpeg,
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "-s:v",
            f"{FRAME_W}x{FRAME_H}",
            "-i",
            "-",
            "-vf",
            "pad=160:208:4:2:color=black,format=yuvj420p",
            "-frames:v",
            "1",
            "-c:v",
            "mjpeg",
            "-q:v",
            str(qscale),
            "-pix_fmt",
            "yuvj420p",
            "-f",
            "image2pipe",
            "-",
        ],
        input=rgba,
        check=True,
        capture_output=True,
    )
    if not result.stdout.startswith(b"\xff\xd8") or not result.stdout.endswith(b"\xff\xd9"):
        raise RuntimeError("ffmpeg did not return a complete JPEG image")
    return result.stdout


def format_bytes(values: bytes) -> list[str]:
    return [
        "    " + ", ".join(f"0x{value:02X}" for value in values[i : i + 24]) + ","
        for i in range(0, len(values), 24)
    ]


def _duration_counts(manifest: dict[str, Any]) -> dict[str, int]:
    counts = {item["name"]: item["count"] for item in manifest["actions"]}
    return {
        "IDLE": manifest["idle_loop_count"],
        "BLINK": counts["IDLE"],
        "RUN": counts["RUNNING_RIGHT"],
        "WAVE": counts["WAVING"],
        "JUMP": counts["JUMPING"],
        "FAILED": counts["FAILED"],
        "WAITING": counts["WAITING"],
        "RUNNING": counts["RUNNING"],
        "REVIEW": counts["REVIEW"],
        "LOOK": counts["LOOK"] // 4,
        "EXCITED": counts["JUMPING"],
        "SLEEPY": min(5, counts["FAILED"]),
        "HOLD": 1,
    }


def timing_durations(manifest: dict[str, Any]) -> dict[str, list[int]]:
    """Return validated timings, filling v1's three legacy implicit tracks."""
    _validate_motion_manifest(manifest)
    durations = {
        name: list(values)
        for name, values in manifest["firmware_durations_ms"].items()
    }
    if manifest["version"] == 1:
        counts = _duration_counts(manifest)
        for name, defaults in LEGACY_TIMING_DEFAULTS.items():
            durations.setdefault(name, _legacy_default_timing(defaults, counts[name]))
    return durations


def _legacy_default_timing(values: list[int], target_count: int) -> list[int]:
    if target_count <= len(values):
        return values[:target_count]
    return [
        values[round(index * (len(values) - 1) / (target_count - 1))]
        for index in range(target_count)
    ]


def _validate_motion_manifest(manifest: dict[str, Any]) -> None:
    version = manifest.get("version")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("motion manifest version must be 1 or 2")
    if (manifest.get("width"), manifest.get("height")) != (FRAME_W, FRAME_H):
        raise ValueError(f"motion manifest frames must be {FRAME_W}x{FRAME_H}")
    frames = manifest.get("frames")
    actions = manifest.get("actions")
    durations = manifest.get("firmware_durations_ms")
    if not isinstance(frames, list) or not frames or len(frames) > 65535:
        raise ValueError("motion manifest must contain 1-65535 frame names")
    if not all(
        isinstance(name, str) and FRAME_NAME_RE.fullmatch(name) for name in frames
    ):
        raise ValueError(
            "motion manifest frame names must be safe strings matching "
            "[A-Za-z0-9][A-Za-z0-9_.-]*"
        )
    if len(frames) != len(set(frames)):
        raise ValueError("motion manifest source frame names must be unique")
    frame_filenames = [frame_filename(name) for name in frames]
    if len(frame_filenames) != len(set(frame_filenames)):
        raise ValueError("motion manifest frame names must map to unique PNG filenames")
    if (
        not isinstance(actions, list)
        or not all(isinstance(item, dict) for item in actions)
        or [item.get("name") for item in actions] != list(ACTION_ORDER)
    ):
        raise ValueError("motion manifest actions must follow the firmware action order")
    expected_first = 0
    counts: dict[str, int] = {}
    for item in actions:
        name = item["name"]
        first = item.get("first")
        count = item.get("count")
        if (
            first != expected_first
            or type(first) is not int
            or type(count) is not int
            or not 1 <= count <= 65535
        ):
            raise ValueError(f"invalid motion action range for {name}")
        counts[name] = count
        expected_first += count
    if expected_first != len(frames):
        raise ValueError("motion manifest action ranges do not cover the frame list")
    if counts["LOOK"] % 4:
        raise ValueError("motion manifest LOOK frame count must be divisible by 4")
    idle_loop_count = manifest.get("idle_loop_count")
    if type(idle_loop_count) is not int or not 1 <= idle_loop_count <= counts["IDLE"]:
        raise ValueError("motion manifest idle_loop_count is invalid")
    if not isinstance(durations, dict):
        raise ValueError("motion manifest firmware_durations_ms is required")
    if counts["RUNNING_LEFT"] != counts["RUNNING_RIGHT"]:
        raise ValueError("directional running actions must have equal frame counts")
    expected_duration_counts = _duration_counts(manifest)
    for name, count in expected_duration_counts.items():
        values = durations.get(name)
        if version == 1 and name in LEGACY_TIMING_DEFAULTS and values is None:
            values = _legacy_default_timing(LEGACY_TIMING_DEFAULTS[name], count)
        if (
            not isinstance(values, list)
            or len(values) != count
            or not all(type(value) is int and 1 <= value <= 65535 for value in values)
        ):
            raise ValueError(f"motion manifest duration count is invalid for {name}")


def _contract_from_manifest(
    manifest: dict[str, Any],
) -> tuple[tuple[tuple[str, int, int], ...], tuple[tuple[str, int, int], ...]]:
    _validate_motion_manifest(manifest)
    frames = tuple((name, -1, -1) for name in manifest["frames"])
    ranges = tuple(
        (item["name"], item["first"], item["count"])
        for item in manifest["actions"]
    )
    return frames, ranges


def load_motion_contract(args: argparse.Namespace) -> tuple[
    tuple[tuple[str, int, int], ...],
    tuple[tuple[str, int, int], ...],
    dict[str, Any],
]:
    if args.spritesheet is not None:
        manifest = motion_manifest("compat")
    else:
        manifest_path = args.frames_dir / "motion_manifest.json"
        if args.motion_profile == "auto" and manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            profile = "compat" if args.motion_profile == "auto" else args.motion_profile
            manifest = motion_manifest(profile)
    frames, ranges = _contract_from_manifest(manifest)
    return frames, ranges, manifest


def build_playback_mapping(
    source_ranges: tuple[tuple[str, int, int], ...],
    target_ranges: tuple[tuple[str, int, int], ...] = ACTION_RANGES,
) -> tuple[int, ...]:
    source_by_action = {
        action: (first, count) for action, first, count in source_ranges
    }
    mapping: list[int] = []
    for action, _, target_count in target_ranges:
        source_first, source_count = source_by_action[action]
        for target_index in range(target_count):
            if target_count == 1:
                source_index = 0
            else:
                source_index = round(
                    target_index * (source_count - 1) / (target_count - 1)
                )
            mapping.append(source_first + source_index)
    expected = sum(count for _, _, count in target_ranges)
    if len(mapping) != expected:
        raise RuntimeError("playback mapping does not fill the target frame contract")
    return tuple(mapping)


def _c_identifier(name: str) -> str:
    identifier = re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()
    return identifier if not identifier[:1].isdigit() else f"_{identifier}"


def _append_byte_array(lines: list[str], symbol: str, payload: bytes) -> None:
    lines.append(f"static const LV_ATTRIBUTE_MEM_ALIGN uint8_t {symbol}[] = {{")
    lines.extend(format_bytes(payload))
    lines.extend(["};", ""])


def build_c_source(
    rgba_frames: list[tuple[str, bytes]],
    action_ranges: tuple[tuple[str, int, int], ...],
    manifest: dict[str, Any],
    *,
    encoding: str = "raw",
    ffmpeg: str = "ffmpeg",
    jpeg_qscale: int = 2,
    alpha_bits: int = 8,
    compat_playback: bool = False,
) -> tuple[str, int, int]:
    """Build the generated C source and return it with stored/playback byte counts."""
    if encoding not in ("raw", "jpeg-alpha-rle"):
        raise ValueError(f"unknown frame encoding: {encoding}")
    target_ranges = ACTION_RANGES if compat_playback else action_ranges
    bundle_manifest = motion_manifest("smooth") if compat_playback else manifest
    timings = timing_durations(bundle_manifest)
    playback_mapping = build_playback_mapping(action_ranges, target_ranges)
    if len(rgba_frames) != sum(count for _, _, count in action_ranges):
        raise ValueError("decoded frame count does not match the motion ranges")

    lines = [
        "// CODEX_PET_GENERATED_ABI: 2",
        "// Generated by tools/convert_codex_pet_p4.py; do not edit or publish without art rights.",
        '#include "pet_generated.h"',
        "",
    ]
    source_assets: list[str] = []
    deduplicated: dict[bytes, str] = {}
    stored_bytes = 0
    for index, (name, rgba) in enumerate(rgba_frames):
        symbol = f"pet_frame_{index:05d}_{_c_identifier(name)}"
        if encoding == "raw":
            raw = rgb565a8_map(rgba)
            digest = hashlib.sha256(raw).digest()
            existing = deduplicated.get(digest)
            if existing is None:
                map_symbol = f"{symbol}_map"
                _append_byte_array(lines, map_symbol, raw)
                lines.extend(
                    [
                        f"static const lv_image_dsc_t {symbol}_raw = {{",
                        "    .header.magic = LV_IMAGE_HEADER_MAGIC,",
                        "    .header.cf = LV_COLOR_FORMAT_RGB565A8,",
                        "    .header.flags = 0,",
                        f"    .header.w = {FRAME_W},",
                        f"    .header.h = {FRAME_H},",
                        f"    .header.stride = {FRAME_W * 2},",
                        f"    .data_size = sizeof({map_symbol}),",
                        f"    .data = {map_symbol},",
                        "};",
                        "",
                    ]
                )
                existing = symbol
                deduplicated[digest] = existing
                stored_bytes += len(raw)
            source_assets.append(
                f"{{.raw = &{existing}_raw, .jpeg_data = 0, .jpeg_size = 0, "
                ".alpha_rle_data = 0, .alpha_rle_size = 0}"
            )
        else:
            jpeg = encode_padded_jpeg(ffmpeg, rgba, jpeg_qscale)
            alpha = alpha_rle_encode(rgba, alpha_bits)
            digest = hashlib.sha256(jpeg + b"\0" + alpha).digest()
            existing = deduplicated.get(digest)
            if existing is None:
                _append_byte_array(lines, f"{symbol}_jpeg", jpeg)
                _append_byte_array(lines, f"{symbol}_alpha_rle", alpha)
                existing = symbol
                deduplicated[digest] = existing
                stored_bytes += len(jpeg) + len(alpha)
            source_assets.append(
                f"{{.raw = 0, .jpeg_data = {existing}_jpeg, "
                f".jpeg_size = sizeof({existing}_jpeg), "
                f".alpha_rle_data = {existing}_alpha_rle, "
                f".alpha_rle_size = sizeof({existing}_alpha_rle)}}"
            )

    lines.extend(
        [
            "static const pet_frame_asset_t pet_frames[] = {",
            *[f"    {source_assets[index]}," for index in playback_mapping],
            "};",
            "",
            "static const pet_motion_range_t pet_motions[PET_MOTION_COUNT] = {",
            *[
                f"    [{MOTION_ENUMS[action]}] = "
                f"{{.first_frame = {first}, .frame_count = {count}}},"
                for action, first, count in target_ranges
            ],
            "};",
            "",
        ]
    )
    for name in TIMING_ORDER:
        values = timings[name]
        lines.append(
            f"static const uint16_t pet_timing_{name.lower()}_durations_ms[] = "
            "{" + ", ".join(str(value) for value in values) + "};"
        )
    lines.extend(
        [
            "",
            "static const pet_timing_track_t pet_timings[PET_TIMING_COUNT] = {",
            *[
                f"    [PET_TIMING_{name}] = "
                f"{{.durations_ms = pet_timing_{name.lower()}_durations_ms, "
                f".count = {len(timings[name])}}},"
                for name in TIMING_ORDER
            ],
            "};",
            "",
            "const pet_asset_bundle_t PET_ASSET_BUNDLE = {",
            f"    .frame_count = {len(playback_mapping)},",
            f"    .idle_loop_count = {bundle_manifest['idle_loop_count']},",
            "    .storage = "
            + (
                "PET_FRAME_STORAGE_RAW_RGB565A8,"
                if encoding == "raw"
                else "PET_FRAME_STORAGE_JPEG_ALPHA_RLE,"
            ),
            "    .frames = pet_frames,",
            "    .motions = pet_motions,",
            "    .timings = pet_timings,",
            "};",
            "",
        ]
    )
    return "\n".join(lines), stored_bytes, len(playback_mapping)


def main() -> None:
    args = parse_args()
    frame_specs, action_ranges, manifest = load_motion_contract(args)
    if args.spritesheet is not None and not args.spritesheet.is_file():
        raise SystemExit(f"spritesheet not found: {args.spritesheet}")
    if args.frames_dir is not None:
        if not args.frames_dir.is_dir():
            raise SystemExit(f"frames directory not found: {args.frames_dir}")
        missing = []
        for name, _, _ in frame_specs:
            try:
                frame_path(args.frames_dir, name)
            except FileNotFoundError:
                missing.append(frame_filename(name))
        if missing:
            raise SystemExit(
                f"frames directory is missing {len(missing)} required file(s): "
                + ", ".join(missing[:8])
            )
    if shutil.which(args.ffmpeg) is None:
        raise SystemExit(f"ffmpeg executable not found: {args.ffmpeg}")

    rgba_frames: list[tuple[str, bytes]] = []
    for name, row, column in frame_specs:
        if args.spritesheet is not None:
            rgba = decode_rgba(args.ffmpeg, args.spritesheet, row, column)
        else:
            rgba = decode_rgba_frame(
                args.ffmpeg,
                frame_path(args.frames_dir, name),
            )
        rgba_frames.append((name, rgba))

    compat_playback = args.spritesheet is not None or manifest.get("profile") == "compat"
    source, total, playback_count = build_c_source(
        rgba_frames,
        action_ranges,
        manifest,
        encoding=args.encoding,
        ffmpeg=args.ffmpeg,
        jpeg_qscale=args.jpeg_qscale,
        alpha_bits=args.alpha_bits,
        compat_playback=compat_playback,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source, encoding="utf-8")
    print(
        f"wrote {args.output} ({FRAME_W}x{FRAME_H}, "
        f"{playback_count} playback frames, {len(frame_specs)} source frames, "
        f"{total} stored payload bytes, {args.encoding})"
    )


if __name__ == "__main__":
    main()
