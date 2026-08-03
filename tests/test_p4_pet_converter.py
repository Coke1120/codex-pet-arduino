import importlib.util
import re
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


class P4PetConverterTests(unittest.TestCase):
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

    def test_frame_contract_matches_firmware(self):
        self.assertEqual(converter.FRAME_W, 152)
        self.assertEqual(converter.FRAME_H, 204)
        self.assertEqual(
            converter.ACTION_RANGES,
            (
                ("IDLE", 0, 6),
                ("RUNNING_RIGHT", 6, 8),
                ("RUNNING_LEFT", 14, 8),
                ("WAVING", 22, 4),
                ("JUMPING", 26, 5),
                ("FAILED", 31, 8),
                ("WAITING", 39, 6),
                ("RUNNING", 45, 6),
                ("REVIEW", 51, 6),
                ("LOOK", 57, 16),
            ),
        )
        self.assertEqual(len(converter.FRAME_SPECS), 73)

    def test_full_v2_payload_has_partition_margin_before_link(self):
        payload_bytes = (
            converter.FRAME_W
            * converter.FRAME_H
            * 3  # LVGL RGB565A8: two colour bytes plus one alpha byte.
            * len(converter.FRAME_SPECS)
        )
        # The 16 MiB board reserves its final 512 KiB while allowing the
        # full v2 atlas and wireless stack to share the factory image.
        partition_bytes = 0xF70000
        required_margin_bytes = 512 * 1024
        conservative_non_asset_budget = 0xC0000

        self.assertEqual(payload_bytes, 6_790_752)
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

    def test_lifecycle_animation_preserves_v1_per_frame_cadence(self):
        source = (ROOT / "esp32-p4" / "main" / "codex_pet_main.c").read_text(
            encoding="utf-8"
        )
        defines = {
            name: int(value)
            for name, value in re.findall(
                r"^#define (PET_(?:IDLE|RUNNING|WAITING|REVIEW)_FRAME_MS) (\d+)U$",
                source,
                re.M,
            )
        }
        self.assertEqual(
            defines,
            {
                "PET_IDLE_FRAME_MS": 650,
                "PET_RUNNING_FRAME_MS": 280,
                "PET_WAITING_FRAME_MS": 520,
                "PET_REVIEW_FRAME_MS": 420,
            },
        )

        expected_arrays = {
            "idle_durations": ("PET_IDLE_FRAME_MS",) * 6,
            "run_durations": ("PET_RUNNING_FRAME_MS",) * 8,
            "waiting_durations": ("PET_WAITING_FRAME_MS",) * 6,
            "running_durations": ("PET_RUNNING_FRAME_MS",) * 6,
            "review_durations": ("PET_REVIEW_FRAME_MS",) * 6,
        }
        for array_name, expected in expected_arrays.items():
            with self.subTest(array_name=array_name):
                match = re.search(
                    rf"static const uint16_t {array_name}\[\] = \{{([^}}]+)\}};",
                    source,
                    re.S,
                )
                self.assertIsNotNone(match)
                values = tuple(
                    value.strip() for value in match.group(1).split(",") if value.strip()
                )
                self.assertEqual(values, expected)

        blink = re.search(
            r"static const uint16_t blink_durations\[\] = \{([^}]+)\};", source
        )
        self.assertIsNotNone(blink)
        self.assertEqual(
            tuple(int(value.strip()) for value in blink.group(1).split(",")),
            (280, 110, 110, 140, 140, 320),
        )

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
            converter.FRAME_SPECS[57:],
            tuple(
                (f"LOOK_{direction.replace('.', '_')}", 9 + index // 8, index % 8)
                for index, direction in enumerate(converter.LOOK_DIRECTIONS)
            ),
        )

    def test_header_range_macros_match_converter_contract(self):
        header = (ROOT / "esp32-p4" / "main" / "pet_generated.h").read_text(
            encoding="utf-8"
        )
        defines = {
            name: int(value)
            for name, value in re.findall(r"^#define (PET_FRAME_\w+) (\d+)$", header, re.M)
        }
        for action, first, count in converter.ACTION_RANGES:
            self.assertEqual(defines[f"PET_FRAME_{action}_FIRST"], first)
            self.assertEqual(defines[f"PET_FRAME_{action}_COUNT"], count)
        self.assertEqual(defines["PET_FRAME_W"], converter.FRAME_W)
        self.assertEqual(defines["PET_FRAME_H"], converter.FRAME_H)
        self.assertEqual(defines["PET_FRAME_SCALE"], 768)
        self.assertEqual(defines["PET_FRAME_COUNT"], len(converter.FRAME_SPECS))

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


if __name__ == "__main__":
    unittest.main()
