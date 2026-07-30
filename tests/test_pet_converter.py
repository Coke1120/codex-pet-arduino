import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "convert_codex_pet.py"
SPEC = importlib.util.spec_from_file_location("convert_codex_pet", MODULE_PATH)
assert SPEC and SPEC.loader
converter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(converter)


class PetConverterTests(unittest.TestCase):
    def test_rle_round_trip_and_max_run_split(self):
        pixels = [0] * 35 + [7] * 2 + [3] * 32 + [1]
        encoded = converter.encode_rle(pixels)

        decoded = []
        for byte in encoded:
            count = (byte >> 3) + 1
            colour = byte & 0x07
            decoded.extend([colour] * count)

        self.assertEqual(decoded, pixels)
        self.assertTrue(all(1 <= (byte >> 3) + 1 <= 32 for byte in encoded))

    def test_transparent_palette_slot_is_reserved(self):
        self.assertEqual(converter.PALETTE[0], (0, 0, 0))
        self.assertEqual(len(converter.PALETTE), 8)
        self.assertGreaterEqual(converter.nearest_colour(240, 240, 240), 1)

    def test_frame_mapping_matches_firmware_protocol(self):
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


if __name__ == "__main__":
    unittest.main()
