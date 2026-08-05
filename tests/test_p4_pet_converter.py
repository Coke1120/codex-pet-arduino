import importlib.util
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "convert_codex_pet_p4.py"
SPEC = importlib.util.spec_from_file_location("convert_codex_pet_p4", MODULE_PATH)
assert SPEC and SPEC.loader
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)

RENDERER_PATH = ROOT / "tools" / "render_pet_demo_blender.py"
RENDERER_SPEC = importlib.util.spec_from_file_location(
    "render_pet_demo_blender", RENDERER_PATH
)
assert RENDERER_SPEC and RENDERER_SPEC.loader
renderer = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(renderer)

MMD_RENDERER_PATH = ROOT / "tools" / "render_mmd_pet_blender.py"
MMD_RENDERER_SPEC = importlib.util.spec_from_file_location(
    "render_mmd_pet_blender", MMD_RENDERER_PATH
)
assert MMD_RENDERER_SPEC and MMD_RENDERER_SPEC.loader
mmd_renderer = importlib.util.module_from_spec(MMD_RENDERER_SPEC)
MMD_RENDERER_SPEC.loader.exec_module(mmd_renderer)


class P4PetConverterTests(unittest.TestCase):
    @staticmethod
    def dynamic_manifest(counts, version=2):
        frames = []
        actions = []
        first = 0
        for action in converter.ACTION_ORDER:
            count = counts[action]
            actions.append({"name": action, "first": first, "count": count})
            frames.extend(f"{action}_{index}" for index in range(count))
            first += count
        idle_loop_count = min(10, counts["IDLE"])
        duration_counts = {
            "IDLE": idle_loop_count,
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
        return {
            "version": version,
            "profile": "custom",
            "width": converter.FRAME_W,
            "height": converter.FRAME_H,
            "idle_loop_count": idle_loop_count,
            "frames": frames,
            "actions": actions,
            "firmware_durations_ms": {
                name: [100] * count for name, count in duration_counts.items()
            },
        }

    def test_rgb565_primary_colours(self):
        self.assertEqual(converter.rgb565(255, 0, 0), 0xF800)
        self.assertEqual(converter.rgb565(0, 255, 0), 0x07E0)
        self.assertEqual(converter.rgb565(0, 0, 255), 0x001F)

    def test_rgb565a8_planes_are_contiguous(self):
        rgba = bytes((255, 0, 0, 0x11, 0, 255, 0, 0xEE))
        self.assertEqual(
            converter.rgb565a8_map(rgba),
            bytes((0x00, 0xF8, 0xE0, 0x07, 0x11, 0xEE)),
        )

    def test_alpha_rle_round_trip_preserves_exact_8_bit_alpha(self):
        alpha = bytes([0] * 300 + [17, 17, 255, 128, 128, 128])
        rgba = b"".join(bytes((1, 2, 3, value)) for value in alpha)

        encoded = converter.alpha_rle_encode(rgba)
        decoded = bytes(
            value
            for run, value in zip(encoded[0::2], encoded[1::2])
            for _ in range(run)
        )

        self.assertEqual(decoded, alpha)
        self.assertEqual(sum(encoded[0::2]), len(alpha))
        self.assertEqual(encoded[:4], bytes((255, 0, 45, 0)))

    def test_four_bit_alpha_rle_quantizes_to_nibble_expansion(self):
        rgba = bytes((0, 0, 0, 0, 0, 0, 0, 8, 0, 0, 0, 255))
        encoded = converter.alpha_rle_encode(rgba, bits=4)
        self.assertEqual(encoded, bytes((2, 0, 1, 255)))

    def test_frame_contract_matches_firmware(self):
        self.assertEqual(converter.FRAME_W, 152)
        self.assertEqual(converter.FRAME_H, 204)
        self.assertEqual(
            converter.ACTION_RANGES,
            (
                ("IDLE", 0, 12),
                ("RUNNING_RIGHT", 12, 8),
                ("RUNNING_LEFT", 20, 8),
                ("WAVING", 28, 8),
                ("JUMPING", 36, 30),
                ("FAILED", 66, 18),
                ("WAITING", 84, 14),
                ("RUNNING", 98, 24),
                ("REVIEW", 122, 14),
                ("LOOK", 136, 16),
            ),
        )
        self.assertEqual(len(converter.FRAME_SPECS), 152)
        self.assertEqual(len(converter.ATLAS_FRAME_SPECS), 73)

    def test_full_smooth_payload_has_partition_margin_before_link(self):
        payload_bytes = (
            converter.FRAME_W
            * converter.FRAME_H
            * 3  # LVGL RGB565A8: two colour bytes plus one alpha byte.
            * len(converter.FRAME_SPECS)
        )
        # The 16 MiB board reserves its final 512 KiB while allowing the
        # smooth motion pack and wireless stack to share the factory image.
        partition_bytes = 0xF70000
        required_margin_bytes = 512 * 1024
        conservative_non_asset_budget = 0xC0000

        self.assertEqual(payload_bytes, 14_139_648)
        self.assertLessEqual(
            payload_bytes + conservative_non_asset_budget,
            partition_bytes - required_margin_bytes,
        )

    def test_v2_row_names_and_counts_are_stable(self):
        self.assertEqual(
            converter.ACTION_SPECS,
            (
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
            ),
        )

    def test_smooth_manifest_matches_fixed_playback_contract(self):
        manifest = converter.motion_manifest("smooth")

        self.assertEqual(manifest["profile"], "smooth")
        self.assertEqual(manifest["width"], 152)
        self.assertEqual(manifest["height"], 204)
        self.assertEqual(manifest["idle_loop_count"], 10)
        self.assertEqual(len(manifest["frames"]), 152)
        self.assertEqual(
            tuple(
                (item["name"], item["first"], item["count"])
                for item in manifest["actions"]
            ),
            converter.ACTION_RANGES,
        )
        self.assertEqual(manifest["firmware_durations_ms"]["RUN"], [90] * 8)
        self.assertEqual(
            manifest["firmware_durations_ms"]["WAVE"],
            [180, 180, 180, 180, 180, 260, 220, 300],
        )
        self.assertEqual(manifest["firmware_durations_ms"]["RUNNING"], [30] * 24)
        self.assertEqual(
            manifest["firmware_durations_ms"]["JUMP"],
            [33] * 29 + [180],
        )
        converter._validate_motion_manifest(manifest)

    def test_version_two_manifest_accepts_720_dynamic_frames(self):
        counts = {
            "IDLE": 60,
            "RUNNING_RIGHT": 60,
            "RUNNING_LEFT": 60,
            "WAVING": 60,
            "JUMPING": 100,
            "FAILED": 80,
            "WAITING": 70,
            "RUNNING": 80,
            "REVIEW": 70,
            "LOOK": 80,
        }
        manifest = self.dynamic_manifest(counts)

        converter._validate_motion_manifest(manifest)
        frames, ranges = converter._contract_from_manifest(manifest)

        self.assertEqual(len(frames), 720)
        self.assertEqual(ranges[-1], ("LOOK", 640, 80))
        self.assertEqual(len(converter.timing_durations(manifest)["LOOK"]), 20)

    def test_manifest_rejects_frame_count_above_uint16(self):
        manifest = converter.motion_manifest("smooth")
        manifest["version"] = 2
        manifest["frames"] = [f"FRAME_{index}" for index in range(65536)]
        with self.assertRaisesRegex(ValueError, "1-65535"):
            converter._validate_motion_manifest(manifest)

    def test_manifest_rejects_boolean_version(self):
        manifest = converter.motion_manifest("smooth")
        manifest["version"] = True

        with self.assertRaisesRegex(ValueError, "version must be 1 or 2"):
            converter._validate_motion_manifest(manifest)

    def test_manifest_rejects_boolean_duration(self):
        manifest = converter.motion_manifest("smooth")
        manifest["firmware_durations_ms"]["IDLE"][0] = True

        with self.assertRaisesRegex(ValueError, "duration count is invalid for IDLE"):
            converter._validate_motion_manifest(manifest)

    def test_manifest_rejects_traversal_frame_name(self):
        manifest = converter.motion_manifest("smooth")
        manifest["frames"][0] = "../outside"

        with self.assertRaisesRegex(ValueError, "safe strings"):
            converter._validate_motion_manifest(manifest)

    def test_manifest_rejects_non_string_and_unhashable_frame_names(self):
        for invalid_name in (123, ["IDLE_0"], {"name": "IDLE_0"}):
            with self.subTest(invalid_name=invalid_name):
                manifest = converter.motion_manifest("smooth")
                manifest["frames"][0] = invalid_name

                with self.assertRaisesRegex(ValueError, "safe strings"):
                    converter._validate_motion_manifest(manifest)

    def test_manifest_rejects_case_folded_png_filename_collision(self):
        manifest = converter.motion_manifest("smooth")
        manifest["frames"][1] = "idle_0"

        with self.assertRaisesRegex(ValueError, "unique PNG filenames"):
            converter._validate_motion_manifest(manifest)

    def test_look_frame_count_must_be_divisible_by_four(self):
        counts = {name: 1 for name in converter.ACTION_ORDER}
        counts["LOOK"] = 5
        manifest = self.dynamic_manifest(counts)
        with self.assertRaisesRegex(ValueError, "LOOK frame count"):
            converter._validate_motion_manifest(manifest)

    def test_version_one_synthesizes_legacy_implicit_timing_tracks(self):
        manifest = converter.motion_manifest("smooth")
        timings = converter.timing_durations(manifest)
        self.assertEqual(timings["LOOK"], [65, 65, 85, 650])
        self.assertEqual(timings["SLEEPY"], [240, 260, 300, 420, 700])
        self.assertEqual(timings["HOLD"], [850])

    def test_version_one_resamples_implicit_look_timing_for_dynamic_count(self):
        counts = {name: 2 for name in converter.ACTION_ORDER}
        counts["LOOK"] = 32
        manifest = self.dynamic_manifest(counts, version=1)
        for name in converter.LEGACY_TIMING_DEFAULTS:
            manifest["firmware_durations_ms"].pop(name)

        timings = converter.timing_durations(manifest)

        self.assertEqual(len(timings["LOOK"]), 8)
        self.assertEqual(timings["LOOK"][0], 65)
        self.assertEqual(timings["LOOK"][-1], 650)
        self.assertEqual(timings["SLEEPY"], [240, 260])

    def test_smooth_playback_mapping_is_identity(self):
        self.assertEqual(
            converter.build_playback_mapping(converter.ACTION_RANGES),
            tuple(range(152)),
        )

    def test_legacy_atlas_mapping_fills_smooth_contract_without_copying_bytes(self):
        mapping = converter.build_playback_mapping(converter.ATLAS_ACTION_RANGES)

        self.assertEqual(len(mapping), 152)
        self.assertTrue(all(0 <= source_index < 73 for source_index in mapping))
        for action, target_first, target_count in converter.ACTION_RANGES:
            source_first, source_count = next(
                (first, count)
                for name, first, count in converter.ATLAS_ACTION_RANGES
                if name == action
            )
            target_slice = mapping[target_first : target_first + target_count]
            self.assertEqual(target_slice[0], source_first)
            self.assertEqual(target_slice[-1], source_first + source_count - 1)

        # Compatibility expands only the descriptor pointer table: each of the
        # 73 decoded images remains represented by one stored source index.
        self.assertEqual(set(mapping), set(range(73)))

    def test_auto_motion_contract_reads_renderer_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            frames_dir = Path(directory)
            manifest = converter.motion_manifest("smooth")
            (frames_dir / "motion_manifest.json").write_text(
                converter.json.dumps(manifest), encoding="utf-8"
            )
            args = SimpleNamespace(
                spritesheet=None,
                frames_dir=frames_dir,
                motion_profile="auto",
            )

            frames, ranges, loaded = converter.load_motion_contract(args)

        self.assertEqual(frames, converter.FRAME_SPECS)
        self.assertEqual(ranges, converter.ACTION_RANGES)
        self.assertEqual(loaded, manifest)

    def test_lifecycle_animation_uses_generated_timing_tracks(self):
        source = (ROOT / "esp32-p4" / "main" / "codex_pet_main.c").read_text(
            encoding="utf-8"
        )
        expected = {
            "ACTION_IDLE": ("PET_MOTION_IDLE", "PET_TIMING_IDLE"),
            "ACTION_BLINK": ("PET_MOTION_IDLE", "PET_TIMING_BLINK"),
            "ACTION_RUN_RIGHT": ("PET_MOTION_RUNNING_RIGHT", "PET_TIMING_RUN"),
            "ACTION_WAVE": ("PET_MOTION_WAVING", "PET_TIMING_WAVE"),
            "ACTION_EXCITED": ("PET_MOTION_JUMPING", "PET_TIMING_EXCITED"),
            "ACTION_RUNNING": ("PET_MOTION_RUNNING", "PET_TIMING_RUNNING"),
            "ACTION_WAITING": ("PET_MOTION_WAITING", "PET_TIMING_WAITING"),
            "ACTION_REVIEW": ("PET_MOTION_REVIEW", "PET_TIMING_REVIEW"),
            "ACTION_FAILED": ("PET_MOTION_FAILED", "PET_TIMING_FAILED"),
        }
        for action, (motion, timing) in expected.items():
            with self.subTest(action=action):
                self.assertRegex(
                    source,
                    rf'\[{action}\] = \{{"[^"]+", {motion}, {timing},',
                )
        self.assertIn("PET_ASSET_BUNDLE.timings", source)
        self.assertIn("PET_ASSET_BUNDLE.idle_loop_count", source)

    def test_firmware_maps_four_eased_gaze_clips(self):
        source = (ROOT / "esp32-p4" / "main" / "codex_pet_main.c").read_text(
            encoding="utf-8"
        )
        self.assertIn("ACTION_LOOK_DOWN", source)
        for action, segment_index in (
            ("ACTION_LOOK_UP", 0),
            ("ACTION_LOOK_RIGHT", 1),
            ("ACTION_LOOK_DOWN", 2),
            ("ACTION_LOOK_LEFT", 3),
        ):
            with self.subTest(action=action):
                pattern = rf'\[{action}\] = \{{"[^"]+", PET_MOTION_LOOK, PET_TIMING_LOOK, {segment_index}, 4, 0,'
                self.assertRegex(source, pattern)

    def test_look_direction_order_is_clockwise(self):
        self.assertEqual(
            converter.LOOK_DIRECTIONS,
            (
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
            ),
        )
        self.assertEqual(
            converter.FRAME_SPECS[136:],
            tuple(
                (f"LOOK_{direction.replace('.', '_')}", -1, -1)
                for index, direction in enumerate(converter.LOOK_DIRECTIONS)
            ),
        )
        self.assertEqual(
            converter.ATLAS_FRAME_SPECS[57:],
            tuple(
                (f"LOOK_{direction.replace('.', '_')}", 9 + index // 8, index % 8)
                for index, direction in enumerate(converter.LOOK_DIRECTIONS)
            ),
        )

    def test_header_exposes_dynamic_asset_bundle_contract(self):
        header = (ROOT / "esp32-p4" / "main" / "pet_generated.h").read_text(
            encoding="utf-8"
        )
        defines = {
            name: int(value)
            for name, value in re.findall(r"^#define (PET_FRAME_\w+) (\d+)$", header, re.M)
        }
        self.assertEqual(defines["PET_FRAME_W"], converter.FRAME_W)
        self.assertEqual(defines["PET_FRAME_H"], converter.FRAME_H)
        self.assertEqual(defines["PET_FRAME_SCALE"], 768)
        self.assertIn("PET_FRAME_STORAGE_RAW_RGB565A8", header)
        self.assertIn("PET_FRAME_STORAGE_JPEG_ALPHA_RLE", header)
        self.assertIn("uint16_t frame_count;", header)
        self.assertIn("const pet_motion_range_t *motions;", header)
        self.assertIn("const pet_timing_track_t *timings;", header)
        self.assertIn("extern const pet_asset_bundle_t PET_ASSET_BUNDLE;", header)

    @mock.patch.object(converter.subprocess, "run")
    def test_decode_filter_crops_without_pre_scaling(self, run):
        run.return_value = SimpleNamespace(
            stdout=bytes(converter.FRAME_W * converter.FRAME_H * 4)
        )

        converter.decode_rgba("ffmpeg", Path("pet.webp"), row=10, column=7)

        command = run.call_args.args[0]
        vf = command[command.index("-vf") + 1]
        self.assertEqual(vf, "crop=152:204:1364:2082,format=rgba")
        self.assertNotIn("scale=", vf)

    def test_crop_contains_measured_character_bounds(self):
        self.assertEqual(
            (converter.CROP_X, converter.CROP_Y, converter.CROP_W, converter.CROP_H),
            (20, 2, 152, 204),
        )

    def test_frame_directory_names_cover_the_firmware_contract(self):
        names = [converter.frame_filename(name) for name, _, _ in converter.FRAME_SPECS]
        self.assertEqual(len(names), 152)
        self.assertEqual(len(set(names)), 152)
        self.assertEqual(names[0], "idle_0.png")
        self.assertEqual(names[-1], "look_337_5.png")

    @mock.patch.object(converter.subprocess, "run")
    def test_frame_decoder_preserves_exact_render_dimensions(self, run):
        run.return_value = SimpleNamespace(
            stdout=bytes(converter.FRAME_W * converter.FRAME_H * 4)
        )

        converter.decode_rgba_frame("ffmpeg", Path("idle_0.png"))

        command = run.call_args.args[0]
        self.assertEqual(command[command.index("-vf") + 1], "format=rgba")
        self.assertNotIn("scale=", " ".join(command))

    @mock.patch.object(converter.subprocess, "run")
    def test_jpeg_encoder_pads_to_decoder_dimensions_and_uses_yuvj420p(self, run):
        run.return_value = SimpleNamespace(stdout=b"\xff\xd8jpeg\xff\xd9")
        rgba = bytes(converter.FRAME_W * converter.FRAME_H * 4)

        result = converter.encode_padded_jpeg("ffmpeg", rgba, qscale=3)

        self.assertEqual(result, b"\xff\xd8jpeg\xff\xd9")
        command = run.call_args.args[0]
        self.assertEqual(run.call_args.kwargs["input"], rgba)
        self.assertEqual(
            command[command.index("-vf") + 1],
            "pad=160:208:4:2:color=black,format=yuvj420p",
        )
        self.assertEqual(command[command.index("-s:v") + 1], "152x204")
        self.assertEqual(command[command.index("-q:v") + 1], "3")
        self.assertEqual(command[command.index("-pix_fmt", 10) + 1], "yuvj420p")

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg is not installed")
    def test_real_ffmpeg_jpeg_q2_round_trip_and_exact_alpha_rle(self):
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg is not None
        rgba = bytes(
            component
            for y in range(converter.FRAME_H)
            for x in range(converter.FRAME_W)
            for component in (
                24 + x,
                18 + y,
                30 + (x + y) // 2,
                (x * 17 + y * 29) % 256,
            )
        )

        jpeg = converter.encode_padded_jpeg(ffmpeg, rgba, qscale=2)
        decoded = subprocess.run(
            [
                ffmpeg,
                "-loglevel",
                "error",
                "-i",
                "-",
                "-frames:v",
                "1",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            input=jpeg,
            check=True,
            capture_output=True,
        ).stdout

        self.assertEqual(len(decoded), 160 * 208 * 3)
        cropped = bytearray()
        for y in range(converter.FRAME_H):
            row_start = ((y + 2) * 160 + 4) * 3
            cropped.extend(decoded[row_start : row_start + converter.FRAME_W * 3])
        expected_rgb = bytes(
            component
            for offset in range(0, len(rgba), 4)
            for component in rgba[offset : offset + 3]
        )
        absolute_error = [
            abs(actual - expected)
            for actual, expected in zip(cropped, expected_rgb)
        ]
        self.assertLess(sum(absolute_error) / len(absolute_error), 3.0)
        self.assertLess(max(absolute_error), 25)

        alpha_rle = converter.alpha_rle_encode(rgba)
        decoded_alpha = bytes(
            value
            for run, value in zip(alpha_rle[0::2], alpha_rle[1::2])
            for _ in range(run)
        )
        self.assertEqual(decoded_alpha, rgba[3::4])

    def test_generated_bundle_metadata_preserves_dynamic_playback_order(self):
        counts = {name: 1 for name in converter.ACTION_ORDER}
        counts["LOOK"] = 4
        manifest = self.dynamic_manifest(counts)
        _, ranges = converter._contract_from_manifest(manifest)
        rgba = bytes(converter.FRAME_W * converter.FRAME_H * 4)
        frames = [(name, rgba) for name in manifest["frames"]]

        raw_source, stored_bytes, playback_count = converter.build_c_source(
            frames, ranges, manifest
        )

        self.assertEqual(raw_source.splitlines()[0], "// CODEX_PET_GENERATED_ABI: 2")
        self.assertEqual(playback_count, 13)
        self.assertEqual(stored_bytes, converter.FRAME_W * converter.FRAME_H * 3)
        self.assertIn(".storage = PET_FRAME_STORAGE_RAW_RGB565A8", raw_source)
        self.assertIn(".frame_count = 13", raw_source)
        self.assertIn(
            "[PET_MOTION_LOOK] = {.first_frame = 9, .frame_count = 4}",
            raw_source,
        )
        self.assertIn("[PET_TIMING_LOOK]", raw_source)
        self.assertEqual(raw_source.count("static const lv_image_dsc_t"), 1)
        self.assertEqual(raw_source.count("    {.raw = &"), 13)

    def test_compat_bundle_uses_legacy_sources_with_smooth_ranges_and_timings(self):
        manifest = converter.motion_manifest("compat")
        _, ranges = converter._contract_from_manifest(manifest)
        rgba = bytes(converter.FRAME_W * converter.FRAME_H * 4)
        frames = [(name, rgba) for name in manifest["frames"]]

        source, _, playback_count = converter.build_c_source(
            frames,
            ranges,
            manifest,
            compat_playback=True,
        )

        self.assertEqual(source.splitlines()[0], "// CODEX_PET_GENERATED_ABI: 2")
        self.assertEqual(playback_count, 152)
        self.assertIn(".frame_count = 152", source)
        self.assertIn(".idle_loop_count = 10", source)
        self.assertIn(
            "[PET_MOTION_JUMPING] = {.first_frame = 36, .frame_count = 30}",
            source,
        )
        self.assertIn(
            "[PET_TIMING_JUMP] = {.durations_ms = pet_timing_jump_durations_ms, .count = 30}",
            source,
        )
        self.assertEqual(source.count("    {.raw = &"), 152)

    @mock.patch.object(converter, "encode_padded_jpeg", return_value=b"\xff\xd8x\xff\xd9")
    def test_generated_compressed_bundle_uses_jpeg_alpha_rle_assets(self, encode):
        counts = {name: 1 for name in converter.ACTION_ORDER}
        counts["LOOK"] = 4
        manifest = self.dynamic_manifest(counts)
        _, ranges = converter._contract_from_manifest(manifest)
        rgba = bytes(converter.FRAME_W * converter.FRAME_H * 4)
        frames = [(name, rgba) for name in manifest["frames"]]

        source, stored_bytes, playback_count = converter.build_c_source(
            frames,
            ranges,
            manifest,
            encoding="jpeg-alpha-rle",
            jpeg_qscale=4,
        )

        self.assertEqual(source.splitlines()[0], "// CODEX_PET_GENERATED_ABI: 2")
        self.assertEqual(playback_count, 13)
        self.assertEqual(stored_bytes, len(b"\xff\xd8x\xff\xd9") + 244)
        self.assertIn(".storage = PET_FRAME_STORAGE_JPEG_ALPHA_RLE", source)
        self.assertIn(".jpeg_size = sizeof(", source)
        self.assertIn(".alpha_rle_size = sizeof(", source)
        self.assertEqual(source.count("_jpeg[] ="), 1)
        self.assertEqual(source.count("_alpha_rle[] ="), 1)
        self.assertEqual(encode.call_count, 13)

    def test_frame_path_rejects_incomplete_render_sets(self):
        with tempfile.TemporaryDirectory() as directory:
            frames = Path(directory)
            with self.assertRaisesRegex(FileNotFoundError, "idle_0.png"):
                converter.frame_path(frames, "IDLE_0")

    def test_frame_path_rejects_symlink_escaping_frames_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            frames = root / "frames"
            frames.mkdir()
            outside = root / "outside.png"
            outside.write_bytes(b"not an image")
            (frames / "idle_0.png").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "escapes frames directory"):
                converter.frame_path(frames, "IDLE_0")

    def test_demo_renderer_varies_actions_without_third_party_assets(self):
        idle = renderer.pose_for_frame("IDLE_0", 0, 6)
        blink = renderer.pose_for_frame("IDLE_2", 2, 6)
        jump = renderer.pose_for_frame("JUMPING_2", 2, 5)
        failed = renderer.pose_for_frame("FAILED_7", 7, 8)

        self.assertEqual(idle["eye_open"], 1.0)
        self.assertLess(blink["eye_open"], idle["eye_open"])
        self.assertGreater(jump["body_z"], 0.4)
        self.assertLessEqual(abs(failed["body_roll"]), 0.42)
        self.assertLess(renderer.root_transform(failed)[0], 0.0)

    def test_demo_renderer_uses_four_eased_cardinal_gaze_clips(self):
        clips = (
            (0, "pupil_z", 0.075),
            (4, "pupil_x", 0.095),
            (8, "pupil_z", -0.075),
            (12, "pupil_x", -0.095),
        )
        for first, axis, endpoint in clips:
            with self.subTest(first=first, axis=axis):
                poses = [
                    renderer.pose_for_frame(f"LOOK_{index}", index, 16)
                    for index in range(first, first + 4)
                ]
                self.assertEqual(poses[0]["pupil_x"], 0.0)
                self.assertEqual(poses[0]["pupil_z"], 0.0)
                orthogonal_axis = "pupil_z" if axis == "pupil_x" else "pupil_x"
                self.assertTrue(
                    all(pose[orthogonal_axis] == 0.0 for pose in poses)
                )
                values = [pose[axis] for pose in poses]
                if endpoint > 0.0:
                    self.assertEqual(values, sorted(values))
                else:
                    self.assertEqual(values, sorted(values, reverse=True))
                self.assertAlmostEqual(values[-1], endpoint)

    def test_mmd_renderer_uses_status_semantics_and_four_eased_gaze_clips(self):
        idle = mmd_renderer.pose_for_frame("IDLE_0", 0, 12)
        running_frames = [
            mmd_renderer.pose_for_frame(f"RUNNING_{index}", index, 24)
            for index in range(24)
        ]
        running = running_frames[4]
        waiting_frames = [
            mmd_renderer.pose_for_frame(f"WAITING_{index}", index, 14)
            for index in range(14)
        ]
        waiting = waiting_frames[7]
        review_frames = [
            mmd_renderer.pose_for_frame(f"REVIEW_{index}", index, 14)
            for index in range(14)
        ]
        review = review_frames[0]
        failed_frames = [
            mmd_renderer.pose_for_frame(f"FAILED_{index}", index, 18)
            for index in range(18)
        ]
        failed_peak = failed_frames[7]
        failed_end = failed_frames[-1]

        self.assertNotEqual(idle["root_x"], 0.0)
        self.assertGreater(idle["right_forearm_raise"], 0.5)
        self.assertGreaterEqual(
            running["lower_x"] + running["upper1_x"] + running["upper_x"],
            10.0,
        )
        self.assertLess(running["center_location"][1], -0.025)
        self.assertGreater(running["left_forearm_raise"], idle["left_forearm_raise"])
        self.assertNotIn("concerned", waiting["morphs"])
        self.assertIn("smile_mouth", waiting["morphs"])
        self.assertIn("serious", review["morphs"])
        self.assertGreater(review["right_forearm_raise"], 0.95)
        self.assertGreater(review["upper_x"], 5.0)
        self.assertIn("surprised", failed_peak["morphs"])
        self.assertNotIn("failed", failed_end["morphs"])
        self.assertNotIn("mouth_down", failed_end["morphs"])
        self.assertGreater(waiting["root_yaw"], 25.0)
        self.assertLess(review["root_yaw"], -25.0)
        self.assertGreater(failed_peak["root_yaw"], 20.0)

        running_right = mmd_renderer.pose_for_frame("RUNNING_RIGHT_3", 3, 8)
        running_left = mmd_renderer.pose_for_frame("RUNNING_LEFT_3", 3, 8)
        self.assertLessEqual(running_right["root_yaw"], -55.0)
        self.assertGreaterEqual(running_left["root_yaw"], 55.0)
        for directional_pose in (running_right, running_left):
            self.assertGreaterEqual(directional_pose["lower_x"], 4.5)
            self.assertGreaterEqual(directional_pose["upper1_x"], 3.0)
            self.assertGreaterEqual(directional_pose["upper_x"], 2.0)
            self.assertGreaterEqual(
                directional_pose["lower_x"]
                + directional_pose["upper1_x"]
                + directional_pose["upper_x"],
                10.0,
            )
            self.assertLessEqual(directional_pose["center_location"][1], -0.055)
            self.assertLessEqual(directional_pose["head_x"], -3.0)
            self.assertGreaterEqual(directional_pose["head_x"], -4.0)
            self.assertLessEqual(abs(directional_pose["lower_z"]), 8.0)
            self.assertGreaterEqual(directional_pose["right_forearm_raise"], 0.38)
            self.assertGreaterEqual(directional_pose["left_forearm_raise"], 0.38)
            self.assertGreaterEqual(abs(directional_pose["right_arm_target"][0]), 0.33)
            self.assertGreaterEqual(abs(directional_pose["left_arm_target"][0]), 0.33)

        # Lower-body silhouettes are deliberately status-specific rather than
        # reusing one parallel, locked-knee stance for every action.
        self.assertNotEqual(idle["right_knee"], idle["left_knee"])
        self.assertNotEqual(
            idle["right_foot_rotation"], idle["left_foot_rotation"]
        )
        self.assertGreater(max(pose["right_foot_location"][2] for pose in running_frames), 0.07)
        self.assertGreater(max(pose["left_foot_location"][2] for pose in running_frames), 0.07)
        self.assertLess(
            min(pose["center_location"][2] for pose in running_frames),
            -0.08,
        )
        self.assertGreater(max(pose["root_z"] for pose in running_frames), 0.05)
        self.assertEqual(
            [running_frames[index]["right_foot_location"] for index in (0, 2, 4)],
            [running_frames[0]["right_foot_location"]] * 3,
        )
        self.assertEqual(
            [running_frames[index]["left_foot_location"] for index in (12, 14, 16)],
            [running_frames[12]["left_foot_location"]] * 3,
        )
        for flight_index in (8, 20):
            self.assertLess(
                running_frames[flight_index]["right_foot_location"][0],
                -0.08,
            )
            self.assertGreater(
                running_frames[flight_index]["left_foot_location"][0],
                0.08,
            )
            self.assertGreater(
                min(
                    running_frames[flight_index][side][2]
                    for side in ("right_foot_location", "left_foot_location")
                ),
                0.10,
            )
            self.assertGreater(
                max(
                    running_frames[flight_index][side][2]
                    for side in ("right_foot_location", "left_foot_location")
                ),
                0.14,
            )
        for side in ("right_knee", "left_knee"):
            knee_values = [pose[side][0] for pose in running_frames]
            self.assertGreaterEqual(min(knee_values), 15.0)
            self.assertLessEqual(min(knee_values), 22.0)
            self.assertGreater(max(knee_values), 50.0)
        self.assertGreater(max(pose["right_foot_location"][2] for pose in waiting_frames), 0.05)
        self.assertGreater(
            max(pose["right_knee"][0] for pose in waiting_frames)
            - min(pose["right_knee"][0] for pose in waiting_frames),
            8.0,
        )
        self.assertGreater(
            abs(review["right_foot_location"][0] - review["left_foot_location"][0]),
            0.08,
        )
        self.assertGreater(max(pose["left_foot_location"][2] for pose in review_frames), 0.025)
        self.assertGreater(
            max(pose["left_knee"][0] for pose in review_frames)
            - min(pose["left_knee"][0] for pose in review_frames),
            8.0,
        )
        self.assertGreater(
            abs(failed_peak["root_x"] - failed_end["root_x"]),
            0.06,
        )

        jump = [
            mmd_renderer.pose_for_frame(f"JUMPING_{index}", index, 30)
            for index in range(30)
        ]
        self.assertLess(jump[0]["center_location"][2], -0.03)
        self.assertLess(min(pose["center_location"][2] for pose in jump), -0.25)
        for control in (
            "center_location",
            "right_knee",
            "left_knee",
            "right_foot_location",
            "left_foot_location",
            "right_arm_target",
            "left_arm_target",
        ):
            self.assertEqual(jump[5][control], jump[6][control])
        self.assertLessEqual(jump[11]["root_z"], 0.02)
        self.assertLess(jump[11]["right_knee"][0], 8.0)
        self.assertEqual(jump[11]["right_foot_location"][2], 0.0)
        self.assertGreater(jump[18]["root_z"], 0.22)
        self.assertEqual(jump[-1]["center_location"], (0.0, 0.0, 0.0))
        self.assertGreater(jump[5]["right_knee"][0], 70.0)
        self.assertLess(min(pose["right_knee"][0] for pose in jump), 10.0)
        self.assertGreater(jump[26]["right_knee"][0], 80.0)
        self.assertGreater(jump[18]["right_foot_location"][2], 0.35)
        self.assertEqual(jump[-1]["right_knee"], idle["right_knee"])
        self.assertLess(jump[18]["root_yaw"], -25.0)
        self.assertNotEqual(
            jump[26]["right_arm_target"], jump[5]["right_arm_target"]
        )
        for control in (
            "center_location",
            "right_knee",
            "left_knee",
            "right_foot_location",
            "left_foot_location",
            "right_arm_target",
            "left_arm_target",
        ):
            self.assertEqual(jump[26][control], jump[27][control])

        # The first gaze frame is exactly the approved idle key so opening a
        # slide never snaps the body, feet, hand, or expression.
        look_neutral = mmd_renderer.pose_for_frame("LOOK_000", 0, 16)
        self.assertEqual(look_neutral, idle)

        look_up = mmd_renderer.pose_for_frame("LOOK_067_5", 3, 16)
        look_right = mmd_renderer.pose_for_frame("LOOK_157_5", 7, 16)
        look_down = mmd_renderer.pose_for_frame("LOOK_247_5", 11, 16)
        look_left = mmd_renderer.pose_for_frame("LOOK_337_5", 15, 16)
        self.assertLess(look_up["head_x"], 0.0)
        self.assertLess(look_right["head_y"], 0.0)
        self.assertGreater(look_down["head_x"], 0.0)
        self.assertGreater(look_left["head_y"], 0.0)
        self.assertLess(look_right["head_y"], -20.0)
        self.assertGreater(look_left["head_y"], 20.0)
        self.assertIn("pupil_up", look_up["morphs"])
        self.assertIn("pupil_right", look_right["morphs"])
        self.assertIn("pupil_down", look_down["morphs"])
        self.assertIn("pupil_left", look_left["morphs"])

    def test_cmake_allows_an_explicit_external_candidate_asset(self):
        cmake = (ROOT / "esp32-p4" / "main" / "CMakeLists.txt").read_text(
            encoding="utf-8"
        )
        fixture = cmake.index("CODEX_PET_SIZE_FIXTURE")
        override = cmake.index("DEFINED CODEX_PET_ASSET_SOURCE")
        local_asset = cmake.index('EXISTS "${CMAKE_CURRENT_LIST_DIR}/pet_generated.c"')
        self.assertLess(fixture, override)
        self.assertLess(override, local_asset)
        self.assertIn("CODEX_PET_ASSET_SOURCE must be an absolute path", cmake)


if __name__ == "__main__":
    unittest.main()
