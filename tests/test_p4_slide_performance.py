import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "esp32-p4"
MAIN_SOURCE = P4 / "main" / "codex_pet_main.c"
DEMO_SOURCE = P4 / "main" / "pet_demo.c"


def function_body(source: str, name: str) -> str:
    match = re.search(
        rf"static [^\n]*\b{name}\([^)]*\)\n\{{(?P<body>.*?)\n\}}",
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
        cls.demo_source = DEMO_SOURCE.read_text(encoding="utf-8")

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

    def test_slide_progress_drives_eased_directional_gaze(self):
        panel = function_body(self.source, "set_panel_progress_locked")
        settings = function_body(self.source, "set_settings_progress_locked")
        usage = function_body(self.source, "set_usage_progress_locked")
        left = function_body(self.source, "set_left_gaze_progress_locked")
        gaze = function_body(self.source, "set_gaze_progress_locked")
        gaze_classifier = function_body(self.source, "action_is_gaze")
        update = function_body(self.source, "update_animation")

        self.assertIn("set_gaze_progress_locked(ACTION_LOOK_UP, progress);", panel)
        self.assertIn("set_gaze_progress_locked(ACTION_LOOK_RIGHT, progress);", settings)
        self.assertIn("set_gaze_progress_locked(ACTION_LOOK_DOWN, progress);", usage)
        self.assertIn("set_gaze_progress_locked(ACTION_LOOK_LEFT, progress);", left)
        self.assertIn("ui.active_action != action || ui.action_frame != frame", gaze)
        self.assertIn("lv_timer_pause(ui.animation_timer);", gaze)
        self.assertIn(
            "contextual == ui.active_action && action_is_gaze(contextual)", update
        )
        for action in (
            "ACTION_LOOK_UP",
            "ACTION_LOOK_RIGHT",
            "ACTION_LOOK_DOWN",
            "ACTION_LOOK_LEFT",
        ):
            self.assertIn(action, gaze_classifier)

    def test_home_right_drag_drives_left_gaze_and_eases_back_to_lifecycle(self):
        navigation = function_body(self.source, "page_navigation_event")
        return_animation = function_body(self.source, "animate_left_gaze_home_locked")
        today_panel = function_body(self.source, "panel_drag_event")
        tap = function_body(self.source, "tap_pet")

        self.assertIn("bool left_gaze_drag", navigation)
        self.assertIn("delta_x > 0", navigation)
        self.assertIn("pet_cardinal_gaze_progress_from_drag", navigation)
        self.assertIn("animate_left_gaze_home_locked();", navigation)
        self.assertIn(
            "ui.gesture_start_gaze_progress = ui.left_gaze_progress;", navigation
        )
        self.assertIn("ui.gesture_start_gaze_progress +", navigation)
        self.assertIn("ui.left_gaze_progress, 0", return_animation)
        self.assertIn("PAGE_ANIMATION_MS", return_animation)
        self.assertIn("lv_anim_path_ease_out", return_animation)
        for handler in (today_panel, tap):
            self.assertIn("lv_anim_delete(&ui, left_gaze_progress_animation);", handler)
            self.assertIn("set_left_gaze_progress_locked(0);", handler)

    def test_slide_gaze_can_override_running_waiting_and_review_bases(self):
        gaze = function_body(self.source, "set_gaze_progress_locked")

        self.assertNotIn("ui.base_action != ACTION_IDLE", gaze)
        self.assertIn("ui.active_action != ui.base_action", gaze)
        self.assertIn("pet_action_can_interrupt", gaze)
        for lifecycle, action in (
            ("PET_LIFECYCLE_RUNNING", "ACTION_RUNNING"),
            ("PET_LIFECYCLE_WAITING", "ACTION_WAITING"),
            ("PET_LIFECYCLE_REVIEW", "ACTION_REVIEW"),
        ):
            self.assertIn(f"case {lifecycle}: return {action};", self.source)

    def test_closing_slide_restores_current_lifecycle_and_resumes_timer(self):
        gaze = function_body(self.source, "set_gaze_progress_locked")
        activate = function_body(self.source, "set_active_action_locked")
        cleanup = gaze.index("if (progress == 0)")
        priority_gate = gaze.index("ui.active_action != ui.base_action")

        self.assertLess(cleanup, priority_gate)
        self.assertIn("ui.active_action == action", gaze)
        self.assertIn("set_active_action_locked(ui.base_action);", gaze)
        self.assertIn("lv_timer_resume(ui.animation_timer);", activate)
        self.assertIn("lv_timer_reset(ui.animation_timer);", activate)

    def test_lifecycle_cadence_uses_dense_frames_with_status_specific_holds(self):
        self.assertIn("PET_TIMING_RUNNING", self.source)
        self.assertIn("PET_TIMING_WAITING", self.source)
        self.assertIn("PET_TIMING_REVIEW", self.source)
        self.assertIn(".idle_loop_count = 10", self.demo_source)
        self.assertIn("[0 ... 23] = 30", self.demo_source)
        self.assertIn("[0 ... 12] = 65, [13] = 180", self.demo_source)
        self.assertIn(
            "180, 180, 180, 180, 180, 260, 220, 300", self.demo_source
        )

    def test_asset_bundle_is_dynamic_and_compressed_frames_use_double_buffering(self):
        validate = function_body(self.source, "validate_asset_bundle")
        decode = function_body(self.source, "decode_compressed_frame")
        show = function_body(self.source, "show_frame_locked")

        self.assertNotIn("PET_FRAME_COUNT", self.source)
        self.assertIn("PET_ASSET_BUNDLE.frame_count", validate)
        self.assertIn("look->frame_count % 4U", validate)
        self.assertIn("jpeg_decoder_get_info", validate)
        self.assertIn("JPEG_DEC_RGB_ELEMENT_ORDER_BGR", decode)
        self.assertIn("asset_decoder.active_buffer ^ 1U", decode)
        self.assertIn("destination + PET_FRAME_COLOUR_BYTES", decode)
        self.assertIn("decode_compressed_frame(index)", show)
        self.assertIn("Keeping previous pet image", show)

    def test_buffering_stays_on_the_proven_partial_double_buffer_path(self):
        defaults = (P4 / "sdkconfig.defaults").read_text(encoding="utf-8")

        self.assertIn("CONFIG_BSP_JC4880P443C_LVGL_BUFFER_SIZE=76800", defaults)
        self.assertIn("CONFIG_BSP_JC4880P443C_LVGL_DOUBLE_BUFFER=y", defaults)
        self.assertNotIn("CONFIG_LVGL_PORT_ENABLE_PPA=y", defaults)


if __name__ == "__main__":
    unittest.main()
