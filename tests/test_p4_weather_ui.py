#!/usr/bin/env python3
"""Regression checks for panel-safe weather and clock icon wiring."""

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "esp32-p4" / "main" / "codex_pet_main.c").read_text(
    encoding="utf-8"
)


class P4WeatherUiTests(unittest.TestCase):
    def test_weather_icons_cover_every_protocol_condition(self):
        body = re.search(
            r"static void render_weather_icon\(.*?\n\}", SOURCE, re.S
        )
        self.assertIsNotNone(body)
        for condition in (
            "CLEAR",
            "PARTLY_CLOUDY",
            "CLOUDY",
            "FOG",
            "RAIN",
            "SNOW",
            "THUNDER",
        ):
            self.assertIn("PET_WEATHER_{}".format(condition), body.group(0))

    def test_main_and_today_weather_icons_refresh_from_the_same_condition(self):
        self.assertRegex(
            SOURCE,
            r"render_weather_icon\(ui\.top_weather_icon,\s*"
            r"TOP_WEATHER_ICON_SIZE,\s*weather->condition\)",
        )
        self.assertRegex(
            SOURCE,
            r"render_weather_icon\(ui\.today_weather_icon,\s*"
            r"TODAY_WEATHER_ICON_SIZE,\s*weather->condition\)",
        )

    def test_today_clock_is_drawn_without_unsupported_unicode_emoji(self):
        self.assertIn("create_clock_icon(ui.today_panel", SOURCE)
        self.assertNotIn("☀", SOURCE)
        self.assertNotIn("🌧", SOURCE)
        self.assertNotIn("⛈", SOURCE)


if __name__ == "__main__":
    unittest.main()
