import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P4 = ROOT / "esp32-p4"


class P4WirelessConfigurationTests(unittest.TestCase):
    def test_hosted_sdio_and_host_only_nimble_are_enabled(self):
        defaults = (P4 / "sdkconfig.defaults").read_text(encoding="utf-8")
        required = {
            "CONFIG_ESP_WIFI_REMOTE_ENABLED": "y",
            "CONFIG_ESP_WIFI_REMOTE_LIBRARY_HOSTED": "y",
            "CONFIG_SLAVE_IDF_TARGET_ESP32C6": "y",
            "CONFIG_ESP_HOSTED_CP_TARGET_ESP32C6": "y",
            "CONFIG_ESP_HOSTED_SDIO_HOST_INTERFACE": "y",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_CLK_SLOT_1": "18",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_CMD_SLOT_1": "19",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D0_SLOT_1": "14",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D1_4BIT_BUS_SLOT_1": "15",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D2_4BIT_BUS_SLOT_1": "16",
            "CONFIG_ESP_HOSTED_PRIV_SDIO_PIN_D3_4BIT_BUS_SLOT_1": "17",
            "CONFIG_ESP_HOSTED_SDIO_GPIO_RESET_SLAVE": "54",
            "CONFIG_BT_ENABLED": "y",
            "CONFIG_BT_CONTROLLER_DISABLED": "y",
            "CONFIG_BT_NIMBLE_ENABLED": "y",
            "CONFIG_ESP_HOSTED_ENABLE_BT_NIMBLE": "y",
            "CONFIG_ESP_HOSTED_NIMBLE_HCI_VHCI": "y",
        }
        actual = dict(re.findall(r"^(CONFIG_[A-Z0-9_]+)=(.+)$", defaults, re.M))
        for key, expected in required.items():
            with self.subTest(key=key):
                self.assertEqual(actual.get(key), expected)

    def test_manifest_pins_compatible_radio_components(self):
        manifest = (P4 / "main" / "idf_component.yml").read_text(encoding="utf-8")
        self.assertIn('espressif/esp_wifi_remote: "1.6.3"', manifest)
        self.assertIn('espressif/esp_hosted: ">=2.11,<3.0"', manifest)

        lock = (P4 / "dependencies.lock").read_text(encoding="utf-8")
        self.assertRegex(lock, r"(?ms)^  espressif/esp_hosted:.*?^    version: 2\.12\.12$")

    def test_hosted_initialization_waits_for_app_startup(self):
        cmake = (P4 / "main" / "CMakeLists.txt").read_text(encoding="utf-8")
        source = (P4 / "main" / "pet_wireless.c").read_text(encoding="utf-8")
        app = (P4 / "main" / "codex_pet_main.c").read_text(encoding="utf-8")
        kconfig = (P4 / "main" / "Kconfig.projbuild").read_text(encoding="utf-8")
        task = re.search(
            r"static void wireless_task\([^)]*\)\n\{(?P<body>.*?)\n\}", source, re.S
        )
        self.assertIsNotNone(task)
        self.assertIn(
            "idf_component_set_property(espressif__esp_hosted WHOLE_ARCHIVE FALSE)",
            cmake,
        )
        self.assertRegex(
            kconfig,
            r"(?ms)^config CODEX_PET_C6_WIRELESS$.*?^\s+default n$",
        )
        self.assertRegex(
            app,
            r"(?ms)^#ifdef CONFIG_CODEX_PET_C6_WIRELESS$.*?"
            r"wireless_result = pet_wireless_start\(\);.*?^#endif$",
        )
        body = task.group("body")
        self.assertLess(
            body.index("esp_hosted_init()"),
            body.index("esp_hosted_connect_to_slave()"),
        )
        for stage in ("esp_hosted_init", "connect_to_slave", "initialize_wifi"):
            self.assertIn('printf("Wireless stage: {}'.format(stage), body)

    def test_factory_uses_flash_with_exact_512k_tail_margin(self):
        partition = (P4 / "partitions.csv").read_text(encoding="utf-8")
        match = re.search(
            r"^factory,\s+app,\s+factory,\s+(0x[0-9A-Fa-f]+),\s+(0x[0-9A-Fa-f]+),",
            partition,
            re.M,
        )
        self.assertIsNotNone(match)
        offset, size = (int(value, 16) for value in match.groups())
        flash_size = 16 * 1024 * 1024
        self.assertEqual(offset, 0x10000)
        self.assertEqual(size, 0xF70000)
        self.assertEqual(flash_size - offset - size, 512 * 1024)

    def test_public_snapshot_never_exposes_a_password(self):
        header = (P4 / "main" / "pet_wireless.h").read_text(encoding="utf-8")
        snapshot = re.search(
            r"typedef struct \{(?P<body>.*?)\} pet_wireless_snapshot_t;", header, re.S
        )
        self.assertIsNotNone(snapshot)
        self.assertNotIn("password", snapshot.group("body").lower())
        self.assertIn('#define PET_WIRELESS_DEVICE_NAME "Codex Pet"', header)

    def test_credentials_are_ram_only_and_sensitive_copies_are_zeroed(self):
        source = (P4 / "main" / "pet_wireless.c").read_text(encoding="utf-8")
        self.assertIn("esp_wifi_set_storage(WIFI_STORAGE_RAM)", source)
        self.assertNotIn("WIFI_STORAGE_FLASH", source)
        self.assertIn("secure_zero(&configuration, sizeof(configuration))", source)
        self.assertIn("secure_zero(request, sizeof(*request))", source)

    def test_wifi_operations_have_deadlines_and_ble_is_nonconnectable(self):
        source = (P4 / "main" / "pet_wireless.c").read_text(encoding="utf-8")
        self.assertIn("PET_WIRELESS_SCAN_TIMEOUT_US", source)
        self.assertIn("PET_WIRELESS_CONNECT_TIMEOUT_US", source)
        self.assertIn("check_wifi_operation_timeout();", source)
        self.assertIn("esp_wifi_scan_stop()", source)
        self.assertIn("result == ESP_ERR_WIFI_NOT_CONNECT", source)
        self.assertIn("BLE_GAP_CONN_MODE_NON", source)
        self.assertNotIn("BLE_GAP_CONN_MODE_UND", source)
        self.assertEqual(
            source.count("s_snapshot.backend = PET_WIRELESS_BACKEND_READY;"), 1
        )
        self.assertRegex(
            source,
            r"(?s)if \(result != ESP_OK\) \{.*?"
            r"s_snapshot\.backend = PET_WIRELESS_BACKEND_ERROR;.*?"
            r"\} else \{.*?s_snapshot\.backend = PET_WIRELESS_BACKEND_READY;",
        )

    def test_lvgl_facing_calls_only_enqueue_radio_work(self):
        source = (P4 / "main" / "pet_wireless.c").read_text(encoding="utf-8")
        for function in (
            "pet_wireless_wifi_set_enabled",
            "pet_wireless_wifi_scan",
            "pet_wireless_wifi_forget",
        ):
            match = re.search(rf"{function}\([^)]*\)\n\{{(?P<body>.*?)\n\}}", source, re.S)
            self.assertIsNotNone(match)
            self.assertIn("enqueue(", match.group("body"))

        connect = re.search(
            r"pet_wireless_wifi_connect\([^)]*\)\n\{(?P<body>.*?)\n\}", source, re.S
        )
        self.assertIsNotNone(connect)
        self.assertIn("enqueue(COMMAND_WIFI_CONNECT", connect.group("body"))
        self.assertNotIn("esp_wifi_", connect.group("body"))

        scan = re.search(
            r"pet_wireless_wifi_scan\([^)]*\)\n\{(?P<body>.*?)\n\}", source, re.S
        )
        self.assertIsNotNone(scan)
        self.assertIn("s_wifi_toggle_pending", scan.group("body"))
        self.assertIn("PET_WIRELESS_WIFI_CONNECTING", scan.group("body"))

        ble_enable = re.search(
            r"pet_wireless_ble_set_enabled\([^)]*\)\n\{(?P<body>.*?)\n\}", source, re.S
        )
        self.assertIsNotNone(ble_enable)
        self.assertIn("s_ble_command_pending", ble_enable.group("body"))
        self.assertIn("enqueue_ble(", ble_enable.group("body"))
        self.assertIn("BLE_COMMAND_ENABLE", ble_enable.group("body"))
        self.assertIn("BLE_COMMAND_DISABLE", ble_enable.group("body"))
        self.assertIn("portMAX_DELAY", ble_enable.group("body"))

    def test_ble_settings_toggle_controls_the_full_radio_lifecycle(self):
        wireless = (P4 / "main" / "pet_wireless.c").read_text(encoding="utf-8")
        ui = (P4 / "main" / "codex_pet_main.c").read_text(encoding="utf-8")
        lifecycle = (P4 / "main" / "pet_wireless_ble_lifecycle.c").read_text(
            encoding="utf-8"
        )

        stop_worker = re.search(
            r"static void ble_host_stop_task\([^)]*\)\n\{(?P<body>.*?)\n\}",
            wireless,
            re.S,
        )
        self.assertIsNotNone(stop_worker)
        self.assertIn("nimble_port_stop()", stop_worker.group("body"))
        stop_wrapper = re.search(
            r"static int32_t ble_host_stop\([^)]*\)\n\{(?P<body>.*?)\n\}",
            wireless,
            re.S,
        )
        self.assertIsNotNone(stop_wrapper)
        self.assertNotIn("nimble_port_stop()", stop_wrapper.group("body"))
        self.assertIn("s_ble_stop_completed", stop_wrapper.group("body"))
        self.assertIn("s_ble_port_stop_completed", stop_wrapper.group("body"))
        self.assertIn("PET_WIRELESS_BLE_STOP_TIMEOUT_MS", stop_wrapper.group("body"))
        self.assertIn("xTaskCreatePinnedToCore(", stop_wrapper.group("body"))
        self.assertIn("nimble_port_deinit()", wireless)
        self.assertIn("esp_hosted_bt_controller_disable()", wireless)
        self.assertIn("esp_hosted_bt_controller_deinit(release_memory)", wireless)
        self.assertIn("ops->controller_deinit(context, false)", lifecycle)
        self.assertIn("xTaskCreatePinnedToCore(", wireless)
        self.assertIn("s_ble_host_stop_requested", wireless)
        self.assertIn("s_ble_host_stop_error_latched", wireless)
        self.assertIn("PET_WIRELESS_BLE_SYNC_TIMEOUT_US", wireless)
        self.assertIn("ble_manager_task", wireless)
        self.assertIn("pet_wireless_ble_set_enabled(enabled)", ui)
        self.assertIn('snapshot.ble_enabled_requested ? "Disable" : "Retry"', ui)
        self.assertNotIn("pet_wireless_ble_set_advertising", wireless)


if __name__ == "__main__":
    unittest.main()
