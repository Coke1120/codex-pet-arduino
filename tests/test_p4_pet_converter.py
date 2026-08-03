import importlib.util
import unittest
from pathlib import Path


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
        self.assertEqual(converter.FRAME_W, 396)
        self.assertEqual(converter.FRAME_H, 612)
        self.assertEqual(
            [name for name, _, _ in converter.FRAME_SPECS],
            [
                "IDLE_0",
                "IDLE_1",
                "RUNNING_0",
                "RUNNING_1",
                "WAITING_0",
                "WAITING_1",
                "REVIEW_0",
                "REVIEW_1",
            ],
        )

    def test_crop_contains_measured_character_bounds(self):
        self.assertLessEqual(converter.CROP_X, 36)
        self.assertLessEqual(converter.CROP_Y, 5)
        self.assertGreaterEqual(converter.CROP_X + converter.CROP_W - 1, 155)
        self.assertGreaterEqual(converter.CROP_Y + converter.CROP_H - 1, 202)


if __name__ == "__main__":
    unittest.main()
