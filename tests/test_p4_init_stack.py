#!/usr/bin/env python3
"""Static regression checks for ESP32-P4 main initialization stack safety."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "esp32-p4"
SOURCE = (P4 / "main" / "codex_pet_main.c").read_text(encoding="utf-8")
CMAKE = (P4 / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
DEFAULTS = (P4 / "sdkconfig.defaults").read_text(encoding="utf-8")


def function_body(source: str, name: str) -> str:
    """Return a C function body using balanced braces, independent of layout."""
    match = re.search(rf"\b{name}\s*\([^;]*?\)\s*\{{", source, re.S)
    if match is None:
        raise AssertionError(f"function {name} not found")

    depth = 1
    index = match.end()
    while index < len(source) and depth:
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
        index += 1
    if depth:
        raise AssertionError(f"function {name} has unbalanced braces")
    return source[match.end() : index - 1]


class P4InitStackTests(unittest.TestCase):
    def test_main_task_stack_default_and_compile_time_floor_are_7680(self):
        config = dict(re.findall(r"^(CONFIG_[A-Z0-9_]+)=(.+)$", DEFAULTS, re.M))
        self.assertEqual(config.get("CONFIG_ESP_MAIN_TASK_STACK_SIZE"), "7680")
        self.assertRegex(
            SOURCE,
            r"#define\s+CODEX_PET_MAIN_TASK_STACK_MIN_BYTES\s+7680\b",
        )
        self.assertRegex(
            SOURCE,
            r"(?s)#if\s+CONFIG_ESP_MAIN_TASK_STACK_SIZE\s*<\s*"
            r"CODEX_PET_MAIN_TASK_STACK_MIN_BYTES\s*"
            r"#error\s+\"CONFIG_ESP_MAIN_TASK_STACK_SIZE must be at least 7680 bytes\"\s*"
            r"#endif",
        )

    def test_app_main_directly_owns_the_initialization_sequence(self):
        body = function_body(SOURCE, "app_main")
        sequence = (
            "bsp_display_start()",
            "bsp_display_brightness_set(80)",
            "create_ui()",
            "pet_wireless_start()",
            'xTaskCreate(serial_task, "codex_pet_serial"',
            'printf("Codex Pet ESP32-P4 ready\\n")',
        )
        positions = [body.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("xTaskCreate(init_task", SOURCE)
        self.assertNotRegex(SOURCE, r"static\s+void\s+init_task\s*\(")

    def test_serial_task_must_exist_before_readiness_is_reported(self):
        body = function_body(SOURCE, "app_main")
        serial_create = body.index('xTaskCreate(serial_task, "codex_pet_serial"')
        serial_failure = body.index('log_main_init_failure("serial task creation")')
        readiness = body.index('printf("Codex Pet ESP32-P4 ready\\n")')
        self.assertLess(serial_create, serial_failure)
        self.assertLess(serial_failure, readiness)

    def test_explicit_failures_log_stage_and_stack_before_returning(self):
        body = function_body(SOURCE, "app_main")
        for stage in (
            "display initialization",
            "display brightness",
            "LVGL lock",
            "serial task creation",
        ):
            with self.subTest(stage=stage):
                self.assertRegex(
                    body,
                    rf'log_main_init_failure\(\s*"{re.escape(stage)}"\s*\)\s*;\s*return\s*;',
                )

        failure_helper = function_body(SOURCE, "log_main_init_failure")
        self.assertLess(
            failure_helper.index("Initialization failed at stage"),
            failure_helper.index("log_main_init_stack_high_water(stage)"),
        )

    def test_brightness_failure_reports_the_esp_idf_error(self):
        body = function_body(SOURCE, "app_main")
        failure = re.search(
            r"if\s*\(brightness_result\s*!=\s*ESP_OK\)\s*\{(?P<body>.*?)\n\s*\}",
            body,
            re.S,
        )
        self.assertIsNotNone(failure)
        failure_body = failure.group("body")
        self.assertIn("esp_err_to_name(brightness_result)", failure_body)
        self.assertIn("(unsigned int)brightness_result", failure_body)
        self.assertIn('log_main_init_failure("display brightness")', failure_body)

    def test_stack_and_internal_heap_are_logged_in_bytes_at_stage_boundaries(self):
        helper = function_body(SOURCE, "log_main_init_stack_high_water")
        main = function_body(SOURCE, "app_main")
        self.assertIn("uxTaskGetStackHighWaterMark(NULL)", helper)
        self.assertIn("sizeof(StackType_t)", helper)
        self.assertIn("heap_caps_get_free_size(MALLOC_CAP_INTERNAL)", helper)
        self.assertIn("stack bytes free", helper)
        self.assertIn("internal heap bytes free", helper)
        for stage in ("entry", "display/BSP", "UI", "wireless", "final"):
            with self.subTest(stage=stage):
                self.assertIn(f'log_main_init_stack_high_water("{stage}")', main)

    def test_stack_diagnostics_are_component_local(self):
        self.assertRegex(
            CMAKE,
            r"(?s)target_compile_options\s*\(\s*\$\{COMPONENT_LIB\}\s+PRIVATE"
            r"(?:(?!\)).)*-fstack-usage"
            r"(?:(?!\)).)*-Werror=frame-larger-than=768\s*\)",
        )

    def test_readiness_distinguishes_base_services_from_optional_wireless(self):
        main = function_body(SOURCE, "app_main")
        readiness = main.index('printf("Codex Pet ESP32-P4 ready\\n")')
        self.assertLess(
            main.index('xTaskCreate(serial_task, "codex_pet_serial"'), readiness
        )
        self.assertGreater(main.index("Display/serial: ready\\n"), readiness)
        self.assertIn("Wireless: startup requested; readiness pending\\n", main)
        self.assertIn("Wireless: unavailable (startup result %d)\\n", main)
        self.assertIn("Wireless: disabled at build time\\n", main)
        self.assertNotIn("Wireless: ready", main)

    def test_protocol_and_wireless_guards_are_preserved(self):
        main = function_body(SOURCE, "app_main")
        self.assertIn("Codex Pet ESP32-P4 ready\\n", main)
        self.assertIn("Board: JC4880P443C-I-W\\n", main)
        self.assertIn(
            "Protocol: v2 lifecycle clock weather today-v1 usage-v1 quota-v1 "
            "codexbar-v1 wireless settings-v1\\n",
            main,
        )
        self.assertIn(
            "Commands: idle running waiting review ping status capabilities clock "
            "weather usage quota\\n",
            main,
        )
        self.assertRegex(
            main,
            r"(?ms)^#ifdef CONFIG_CODEX_PET_C6_WIRELESS$.*?"
            r"wireless_result\s*=\s*pet_wireless_start\(\);.*?^#endif$",
        )


if __name__ == "__main__":
    unittest.main()
