import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = ROOT / "vendor" / "jc4880p443c_i_w_bsp"
COMPONENTS = VENDOR_ROOT / "components"
BOARD_ROOT = VENDOR_ROOT / "boards" / "guition-jc4880p443"
SOURCE_MANIFEST = VENDOR_ROOT / "SOURCE_MANIFEST.tsv"
ARCHIVE_SHA256 = (
    "7cea2154667033a639b62a42d1952066ca55c78e187846351f5facb0c3f5232f"
)
APACHE_LICENSE_SHA256 = (
    "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"
)
MIT_LICENSE_SHA256 = (
    "0a5a839033bfe18fe75d32b50d9d028912cf876f69ef59c2791aeb2971335d05"
)
COMMON_PREFIX = (
    "JC4880P443C_I_W/1-Demo/idf_examples/ESP-IDF_5.5.4/common_components/"
)
XIAOZHI_PREFIX = (
    "JC4880P443C_I_W/1-Demo/idf_examples/ESP-IDF_5.5.4/"
    "xiaozhi-esp32-main/"
)
NORMALIZED_PATHS = {
    "boards/guition-jc4880p443/README.md",
    "boards/guition-jc4880p443/jc4880p443.cc",
    "components/bsp_extra/include/bsp_board_extra.h",
    "components/espressif__esp32_p4_function_ev_board/API.md",
    "components/espressif__esp32_p4_function_ev_board/Kconfig",
    "components/espressif__esp32_p4_function_ev_board/esp32_p4_function_ev_board.c",
    "components/espressif__esp32_p4_function_ev_board/idf_component.yml",
    "components/espressif__esp_lcd_st7701/esp_lcd_st7701_mipi.c",
}


class VendorBspTests(unittest.TestCase):
    def _read_source_manifest(self):
        records = {}
        archive_paths = set()
        for line_number, line in enumerate(
            SOURCE_MANIFEST.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line or line.startswith("#"):
                continue
            fields = line.split("\t")
            self.assertEqual(len(fields), 4, msg=f"manifest line {line_number}")
            vendored_hash, archive_hash, vendored_path, archive_path = fields
            self.assertNotIn(vendored_path, records)
            self.assertNotIn(archive_path, archive_paths)
            for digest in (vendored_hash, archive_hash):
                self.assertEqual(len(digest), 64)
                int(digest, 16)
            records[vendored_path] = (
                vendored_hash,
                archive_hash,
                archive_path,
            )
            archive_paths.add(archive_path)
        return records

    def test_snapshot_manifest_and_component_versions(self) -> None:
        readme = (VENDOR_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn(ARCHIVE_SHA256, readme)
        manifest_header = SOURCE_MANIFEST.read_text(encoding="utf-8").splitlines()
        self.assertIn(f"# archive_sha256={ARCHIVE_SHA256}", manifest_header)

        expected_versions = {
            "bsp_extra": "version: 0.0.2",
            "espressif__esp32_p4_function_ev_board": "version: 5.2.3",
            "espressif__esp_lcd_st7701": "version: 1.1.3",
        }
        for component, version in expected_versions.items():
            with self.subTest(component=component):
                metadata = (COMPONENTS / component / "idf_component.yml").read_text(
                    encoding="utf-8"
                )
                self.assertIn(version, metadata)

    def test_model_specific_board_contract_is_preserved(self) -> None:
        config = (BOARD_ROOT / "config.h").read_text(encoding="utf-8")
        implementation = (BOARD_ROOT / "jc4880p443.cc").read_text(encoding="utf-8")
        metadata = (BOARD_ROOT / "config.json").read_text(encoding="utf-8")

        for expected in (
            "#define LCD_H_RES                  (480)",
            "#define LCD_V_RES                  (800)",
            "#define PIN_NUM_LCD_RST            GPIO_NUM_5",
            "#define PIN_NUM_BK_LIGHT           GPIO_NUM_23",
            "#define LCD_TOUCH_RST       GPIO_NUM_22",
            "#define LCD_TOUCH_INT       GPIO_NUM_21",
            "#define LCD_MIPI_DSI_LANE_NUM          (2)",
        ):
            self.assertIn(expected, config)
        for expected in (
            '#include "esp_lcd_st7701.h"',
            ".lane_bit_rate_mbps = 500,",
            ".h_size = 480,",
            ".v_size = 800,",
            "esp_lcd_new_panel_st7701",
        ):
            self.assertIn(expected, implementation)
        self.assertIn('"name": "guition-jc4880p443"', metadata)

    def test_imported_licenses_are_preserved(self) -> None:
        apache_licenses = (
            COMPONENTS / "bsp_extra" / "LICENSE",
            COMPONENTS / "espressif__esp32_p4_function_ev_board" / "LICENSE",
            COMPONENTS / "espressif__esp_lcd_st7701" / "license.txt",
        )
        for path in apache_licenses:
            with self.subTest(path=path):
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                    APACHE_LICENSE_SHA256,
                )

        mit_license = VENDOR_ROOT / "licenses" / "xiaozhi-esp32-main-LICENSE"
        self.assertEqual(
            hashlib.sha256(mit_license.read_bytes()).hexdigest(),
            MIT_LICENSE_SHA256,
        )
        cc0_example = (
            COMPONENTS
            / "espressif__esp_lcd_st7701"
            / "external_examples"
            / "620bb409"
            / "rgb_avoid_tearing"
            / "main"
            / "example_rgb_avoid_tearing.c"
        )
        self.assertIn("SPDX-License-Identifier: CC0-1.0", cc0_example.read_text())

    def test_source_manifest_authenticates_every_imported_file(self) -> None:
        records = self._read_source_manifest()
        imported_files = {
            path.relative_to(VENDOR_ROOT).as_posix()
            for path in VENDOR_ROOT.rglob("*")
            if path.is_file()
            and path.relative_to(VENDOR_ROOT).as_posix()
            not in {"README.md", "SOURCE_MANIFEST.tsv"}
        }
        self.assertEqual(len(records), 65)
        self.assertEqual(set(records), imported_files)

        normalized_paths = set()
        for vendored_path, record in records.items():
            vendored_hash, archive_hash, archive_path = record
            with self.subTest(vendored_path=vendored_path):
                path = VENDOR_ROOT / vendored_path
                self.assertEqual(
                    hashlib.sha256(path.read_bytes()).hexdigest(), vendored_hash
                )
                if vendored_path.startswith("components/"):
                    expected_archive_path = COMMON_PREFIX + vendored_path.removeprefix(
                        "components/"
                    )
                elif vendored_path.startswith("boards/"):
                    expected_archive_path = (
                        XIAOZHI_PREFIX
                        + "main/boards/"
                        + vendored_path.removeprefix("boards/")
                    )
                else:
                    self.assertEqual(
                        vendored_path, "licenses/xiaozhi-esp32-main-LICENSE"
                    )
                    expected_archive_path = XIAOZHI_PREFIX + "LICENSE"
                self.assertEqual(archive_path, expected_archive_path)
                if vendored_hash != archive_hash:
                    normalized_paths.add(vendored_path)
        self.assertEqual(normalized_paths, NORMALIZED_PATHS)

    def test_snapshot_excludes_full_vendor_bundle_and_prebuilt_tools(self) -> None:
        files = [path for path in VENDOR_ROOT.rglob("*") if path.is_file()]
        self.assertEqual(len(files), 67)
        blocked_suffixes = {
            ".7z",
            ".app",
            ".avi",
            ".bin",
            ".dll",
            ".dmg",
            ".dylib",
            ".elf",
            ".exe",
            ".iso",
            ".mp4",
            ".msi",
            ".o",
            ".rar",
            ".so",
            ".tar",
            ".xz",
            ".zip",
        }
        blocked_magic = (
            b"MZ",
            b"\x7fELF",
            b"PK\x03\x04",
            b"Rar!",
            b"\xca\xfe\xba\xbe",
            b"\xcf\xfa\xed\xfe",
            b"\xfe\xed\xfa\xcf",
        )
        for path in files:
            with self.subTest(path=path):
                self.assertNotIn(path.suffix.lower(), blocked_suffixes)
                self.assertLess(path.stat().st_size, 10 * 1024 * 1024)
                prefix = path.read_bytes()[:12]
                self.assertFalse(any(prefix.startswith(magic) for magic in blocked_magic))
                if prefix.startswith(b"RIFF"):
                    self.assertNotEqual(prefix[8:12], b"AVI ")


if __name__ == "__main__":
    unittest.main()
