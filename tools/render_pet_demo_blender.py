#!/usr/bin/env python3
"""Render a rights-safe procedural 3D pet into the legacy 73-frame source contract.

Run this script through Blender, for example:

    /Applications/Blender.app/Contents/MacOS/Blender --background \
      --python tools/render_pet_demo_blender.py -- \
      --output-dir /tmp/codex-pet-model-frames

The demo model is generated from Blender primitives and does not contain or
load third-party character assets. It is a pipeline proof, not final artwork.
"""

from __future__ import annotations

import argparse
import importlib.util
import math
import sys
from pathlib import Path


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
ROOT_PIVOT_Z = 1.8

FRAME_CONTEXT: dict[str, tuple[int, int]] = {}
for _, first, count in ACTION_RANGES:
    for local_index, (name, _, _) in enumerate(FRAME_SPECS[first : first + count]):
        FRAME_CONTEXT[name] = (local_index, count)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--only",
        help="comma-separated exact frame names for a quick smoke render",
    )
    return parser.parse_args(argv)


def blender_script_args(argv: list[str]) -> list[str]:
    if "--" not in argv:
        return []
    return argv[argv.index("--") + 1 :]


def smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def pose_for_frame(name: str, frame_index: int, frame_count: int) -> dict[str, float]:
    phase = 2.0 * math.pi * frame_index / max(frame_count, 1)
    progress = frame_index / max(frame_count - 1, 1)
    pose = {
        "body_x": 0.0,
        "body_z": 0.0,
        "body_roll": 0.0,
        "body_scale_z": 1.0,
        "left_arm": -0.12,
        "right_arm": 0.12,
        "pupil_x": 0.0,
        "pupil_z": 0.0,
        "eye_open": 1.0,
    }

    if name.startswith("IDLE_"):
        pose["body_z"] = 0.045 * math.sin(phase)
        pose["eye_open"] = 0.12 if frame_index == 2 else 1.0
    elif name.startswith("RUNNING_RIGHT_"):
        pose["body_x"] = 0.09 * math.sin(phase)
        pose["body_z"] = 0.08 * abs(math.sin(phase))
        pose["body_roll"] = -0.16 + 0.05 * math.sin(phase)
        pose["left_arm"] = -0.35 * math.sin(phase)
        pose["right_arm"] = 0.35 * math.sin(phase)
        pose["pupil_x"] = 0.07
    elif name.startswith("RUNNING_LEFT_"):
        pose["body_x"] = 0.09 * math.sin(phase)
        pose["body_z"] = 0.08 * abs(math.sin(phase))
        pose["body_roll"] = 0.16 - 0.05 * math.sin(phase)
        pose["left_arm"] = -0.35 * math.sin(phase)
        pose["right_arm"] = 0.35 * math.sin(phase)
        pose["pupil_x"] = -0.07
    elif name.startswith("WAVING_"):
        pose["right_arm"] = 0.8 + 0.35 * math.sin(phase)
        pose["body_roll"] = -0.04
    elif name.startswith("JUMPING_"):
        pose["body_z"] = 0.48 * math.sin(math.pi * progress)
        pose["body_scale_z"] = 0.92 + 0.16 * math.sin(math.pi * progress)
        pose["left_arm"] = -0.65
        pose["right_arm"] = 0.65
    elif name.startswith("FAILED_"):
        pose["body_z"] = -0.22 * progress
        pose["body_roll"] = 0.42 * progress
        pose["eye_open"] = max(0.16, 1.0 - 0.9 * progress)
        pose["pupil_z"] = -0.05
    elif name.startswith("WAITING_"):
        pose["body_roll"] = 0.06 * math.sin(phase)
        pose["pupil_x"] = 0.07 * math.sin(phase)
        pose["pupil_z"] = -0.03
    elif name.startswith("RUNNING_"):
        pose["body_z"] = 0.09 * abs(math.sin(phase))
        pose["body_roll"] = 0.05 * math.sin(phase)
        pose["left_arm"] = -0.4 * math.sin(phase)
        pose["right_arm"] = 0.4 * math.sin(phase)
    elif name.startswith("REVIEW_"):
        pose["body_roll"] = 0.08 * math.sin(phase)
        pose["pupil_x"] = 0.04 * math.sin(phase)
        pose["pupil_z"] = 0.06
        pose["right_arm"] = 0.42
    elif name.startswith("LOOK_"):
        direction_index, transition_index = divmod(frame_index, 4)
        eased = smoothstep(transition_index / 3.0)
        if direction_index == 0:  # up
            pose["pupil_z"] = 0.075 * eased
        elif direction_index == 1:  # screen right
            pose["pupil_x"] = 0.095 * eased
            pose["body_roll"] = -0.035 * eased
        elif direction_index == 2:  # down
            pose["pupil_z"] = -0.075 * eased
        else:  # screen left
            pose["pupil_x"] = -0.095 * eased
            pose["body_roll"] = 0.035 * eased

    return pose


def root_transform(pose: dict[str, float]) -> tuple[float, float, float]:
    angle = pose["body_roll"]
    return (
        pose["body_x"] - ROOT_PIVOT_Z * math.sin(angle),
        0.0,
        pose["body_z"] + ROOT_PIVOT_Z * (1.0 - math.cos(angle)),
    )


def _smooth(obj: object) -> None:
    for polygon in obj.data.polygons:
        polygon.use_smooth = True


def _material(bpy: object, name: str, colour: tuple[float, float, float, float]) -> object:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    shader = material.node_tree.nodes.get("Principled BSDF")
    shader.inputs["Base Color"].default_value = colour
    shader.inputs["Roughness"].default_value = 0.62
    return material


def _sphere(
    bpy: object,
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: object,
    parent: object,
) -> object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20)
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = location
    obj.scale = scale
    obj.data.materials.append(material)
    _smooth(obj)
    return obj


def _cube(
    bpy: object,
    name: str,
    location: tuple[float, float, float],
    scale: tuple[float, float, float],
    material: object,
    parent: object,
) -> object:
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = name
    obj.parent = parent
    obj.location = location
    obj.scale = scale
    obj.data.materials.append(material)
    bevel = obj.modifiers.new("Soft edges", "BEVEL")
    bevel.width = 0.08
    bevel.segments = 3
    return obj


def build_demo_scene(bpy: object) -> dict[str, object]:
    bpy.ops.wm.read_factory_settings(use_empty=True)
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

    dark = _material(bpy, "Pet navy", (0.025, 0.055, 0.09, 1.0))
    light = _material(bpy, "Pet face", (0.78, 0.9, 0.94, 1.0))
    white = _material(bpy, "Eye white", (0.96, 0.99, 1.0, 1.0))
    black = _material(bpy, "Pupil", (0.005, 0.008, 0.012, 1.0))
    cyan = _material(bpy, "Codex cyan", (0.04, 0.72, 0.78, 1.0))

    root = bpy.data.objects.new("Pet root", None)
    scene.collection.objects.link(root)
    body = _sphere(bpy, "Body", (0.0, 0.0, 1.45), (0.82, 0.5, 1.0), dark, root)
    _sphere(bpy, "Belly", (0.0, -0.43, 1.35), (0.5, 0.12, 0.65), light, root)
    head = _sphere(bpy, "Head", (0.0, -0.02, 2.58), (0.78, 0.52, 0.67), dark, root)
    _sphere(bpy, "Face", (0.0, -0.48, 2.57), (0.58, 0.11, 0.45), light, root)
    left_eye = _sphere(bpy, "Left eye", (-0.25, -0.58, 2.7), (0.16, 0.07, 0.2), white, root)
    right_eye = _sphere(bpy, "Right eye", (0.25, -0.58, 2.7), (0.16, 0.07, 0.2), white, root)
    left_pupil = _sphere(bpy, "Left pupil", (-0.25, -0.65, 2.7), (0.065, 0.035, 0.09), black, root)
    right_pupil = _sphere(bpy, "Right pupil", (0.25, -0.65, 2.7), (0.065, 0.035, 0.09), black, root)
    _cube(bpy, "Mouth", (0.0, -0.61, 2.4), (0.16, 0.035, 0.035), cyan, root)
    left_arm = _sphere(bpy, "Left arm", (-0.84, -0.02, 1.58), (0.23, 0.14, 0.62), dark, root)
    right_arm = _sphere(bpy, "Right arm", (0.84, -0.02, 1.58), (0.23, 0.14, 0.62), dark, root)
    _sphere(bpy, "Left foot", (-0.34, -0.1, 0.45), (0.34, 0.32, 0.2), cyan, root)
    _sphere(bpy, "Right foot", (0.34, -0.1, 0.45), (0.34, 0.32, 0.2), cyan, root)
    _sphere(bpy, "Signal", (0.0, -0.04, 3.32), (0.13, 0.08, 0.13), cyan, root)

    bpy.ops.object.light_add(type="AREA", location=(-3.5, -4.5, 6.0))
    key = bpy.context.object
    key.data.energy = 850
    key.data.shape = "DISK"
    key.data.size = 5.0
    bpy.ops.object.light_add(type="AREA", location=(4.0, 1.0, 3.5))
    fill = bpy.context.object
    fill.data.energy = 450
    fill.data.size = 4.0

    bpy.ops.object.camera_add(location=(0.0, -9.0, 2.0))
    camera = bpy.context.object
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 4.55
    from mathutils import Vector

    camera.rotation_euler = (Vector((0.0, 0.0, 1.85)) - camera.location).to_track_quat(
        "-Z", "Y"
    ).to_euler()
    scene.camera = camera

    return {
        "scene": scene,
        "root": root,
        "body": body,
        "head": head,
        "left_eye": left_eye,
        "right_eye": right_eye,
        "left_pupil": left_pupil,
        "right_pupil": right_pupil,
        "left_arm": left_arm,
        "right_arm": right_arm,
    }


def apply_pose(rig: dict[str, object], pose: dict[str, float]) -> None:
    root = rig["root"]
    root.location = root_transform(pose)
    root.rotation_euler = (0.0, pose["body_roll"], 0.0)
    rig["body"].scale = (0.82, 0.5, pose["body_scale_z"])
    rig["head"].scale = (0.78, 0.52, 0.67 / pose["body_scale_z"])
    rig["left_arm"].rotation_euler = (0.0, pose["left_arm"], 0.0)
    rig["right_arm"].rotation_euler = (0.0, pose["right_arm"], 0.0)
    for base_x, eye_name, pupil_name in (
        (-0.25, "left_eye", "left_pupil"),
        (0.25, "right_eye", "right_pupil"),
    ):
        eye = rig[eye_name]
        pupil = rig[pupil_name]
        eye.scale = (0.16, 0.07, 0.2 * pose["eye_open"])
        pupil.location = (
            base_x + pose["pupil_x"],
            -0.65,
            2.7 + pose["pupil_z"],
        )
        pupil.scale = (0.065, 0.035, 0.09 * pose["eye_open"])


def main() -> None:
    args = parse_args(blender_script_args(sys.argv))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected = None
    if args.only:
        selected = {name.strip().upper() for name in args.only.split(",") if name.strip()}
        unknown = selected.difference(FRAME_CONTEXT)
        if unknown:
            raise SystemExit("unknown frame name(s): " + ", ".join(sorted(unknown)))

    import bpy

    rig = build_demo_scene(bpy)
    rendered = 0
    for name, _, _ in FRAME_SPECS:
        if selected is not None and name not in selected:
            continue
        frame_index, frame_count = FRAME_CONTEXT[name]
        apply_pose(rig, pose_for_frame(name, frame_index, frame_count))
        bpy.context.view_layer.update()
        rig["scene"].render.filepath = str(
            args.output_dir / CONVERTER.frame_filename(name)
        )
        bpy.ops.render.render(write_still=True)
        rendered += 1
    print(f"rendered {rendered} rights-safe frame(s) to {args.output_dir}")


if __name__ == "__main__":
    main()
