import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "esp32-p4"
MAIN_SOURCE = P4 / "main" / "codex_pet_main.c"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"static void {name}\([^)]*\)\n\{{(?P<body>.*?)\n\}}",
        source,
        re.S,
    )
    if match is None:
        raise AssertionError(f"Unable to find {name}")
    return match.group("body")


class P4SlidePerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MAIN_SOURCE.read_text(encoding="utf-8")

    def test_pet_alignment_is_configured_once_outside_the_slide_hot_path(self):
        create_ui = function_body(self.source, "create_ui")
        render_pet = function_body(self.source, "set_pet_render_top_locked")

        self.assertIn("lv_obj_set_align(ui.image, LV_ALIGN_TOP_MID);", create_ui)
        self.assertIn("lv_obj_set_y(ui.image,", render_pet)
        self.assertNotIn("lv_obj_align", render_pet)

    def test_slide_setters_skip_duplicate_logical_progress(self):
        for function, field in (
            ("set_panel_progress_locked", "panel_progress"),
            ("set_settings_progress_locked", "settings_progress"),
            ("set_usage_progress_locked", "usage_progress"),
        ):
            with self.subTest(function=function):
                body = function_body(self.source, function)
                self.assertIn(f"if (progress == ui.{field}) return;", body)

    def test_today_touch_flags_only_change_when_crossing_the_threshold(self):
        body = function_body(self.source, "set_panel_progress_locked")

        self.assertIn("pet_was_hidden", body)
        self.assertIn("pet_should_hide", body)
        self.assertIn("if (pet_was_hidden != pet_should_hide)", body)

    def test_buffering_stays_on_the_proven_partial_double_buffer_path(self):
        defaults = (P4 / "sdkconfig.defaults").read_text(encoding="utf-8")

        self.assertIn("CONFIG_BSP_JC4880P443C_LVGL_BUFFER_SIZE=76800", defaults)
        self.assertIn("CONFIG_BSP_JC4880P443C_LVGL_DOUBLE_BUFFER=y", defaults)
        self.assertNotIn("CONFIG_LVGL_PORT_ENABLE_PPA=y", defaults)


if __name__ == "__main__":
    unittest.main()
