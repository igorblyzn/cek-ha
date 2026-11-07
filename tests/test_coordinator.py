"""Parser regression tests runnable without a Home Assistant installation."""

import importlib.util
from datetime import date
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import patch


def load_coordinator():
    """Load the real parser with only its Home Assistant imports stubbed."""
    root = Path(__file__).resolve().parents[1] / "custom_components/cek_power_outage"
    package = ModuleType("cek_parser_tests")
    package.__path__ = [str(root)]

    class Coordinator:
        def __class_getitem__(cls, _):
            return cls

    modules = {"cek_parser_tests": package}
    for name in (
        "homeassistant", "homeassistant.core", "homeassistant.helpers",
        "homeassistant.helpers.update_coordinator", "homeassistant.util",
        "homeassistant.util.dt",
    ):
        modules[name] = ModuleType(name)
    modules["homeassistant.core"].HomeAssistant = object
    helper = modules["homeassistant.helpers.update_coordinator"]
    helper.DataUpdateCoordinator = Coordinator
    helper.UpdateFailed = RuntimeError
    with patch.dict(sys.modules, modules):
        spec = importlib.util.spec_from_file_location(
            "cek_parser_tests.coordinator", root / "coordinator.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module.CEKDataUpdateCoordinator


Parser = load_coordinator()
TODAY = date(2026, 11, 7)
# Structure published by CEK on 7 November: main announcement has no 📢,
# midnight is written 00:00, and an unrelated city announcement follows.
LIVE_FORMAT = """
<p>Створено: 20 квітня 2017</p>
<p>Шановні споживачі!</p>
<p>Повідомляємо, що за розпорядженням диспетчерського центру НЕК
"Укренерго", 07 ЛИСТОПАДА з 00:00 до 24:00 застосовуватимуться відключення
наступних черг:<br />🔹 Черга 1.1<br />03:00-10:00<br />13:30-20:30</p>
<p>🔹 Черга 6.1<br />03:00-06:30<br />10:00-13:30<br />20:30-00:00</p>
<p>🔹 Черга 6.2<br />10:00-17:00<br />22:00-00:00</p>
<p>📢 Шановні мешканці м. ПАВЛОГРАД‼️</p>
<p>ГПВ на 07 ЛИСТОПАДА для споживачів міста за окремим графіком:</p>
<p>📌 1 черга:<br />✔️ 02:00 - 07:00;<br />✔️ 22:00 - 24:00.</p>
"""


class ScheduleTests(unittest.TestCase):
    def parse(self, html, queue="6.2"):
        text = Parser._extract_text_from_html(html)
        blocks = Parser._parse_announcements(text, queue)
        return Parser._build_days(blocks, TODAY)

    def test_live_format_without_marker(self):
        days = self.parse(LIVE_FORMAT)
        self.assertEqual(len(days), 1)
        self.assertEqual(days[0]["date"], "2026-11-07")
        self.assertEqual(days[0]["schedule"], ["10:00 до 17:00", "22:00 до 24:00"])
        self.assertEqual(days[0]["outage_hours"], 9.0)

    def test_still_accepts_marker(self):
        html = LIVE_FORMAT.replace("Повідомляємо", "📢 Повідомляємо")
        self.assertEqual(self.parse(html), self.parse(LIVE_FORMAT))

    def test_old_and_new_format_combinations(self):
        for marker in ("📢 ", ""):
            for queue_header in ("6.2 черга:", "Черга 6.2", "🔹 Черга 6.2", "📌 6.2"):
                for separator in ("до", "по", "-", "–", "—"):
                    for midnight in ("24:00", "00:00"):
                        with self.subTest(
                            marker=marker, queue=queue_header,
                            separator=separator, midnight=midnight,
                        ):
                            html = f"""
                            <p>Створено: 20 квітня 2017</p>
                            <p>{marker}Повідомляємо, що 07 листопада
                            застосовуватимуться відключення наступних черг:</p>
                            <p>{queue_header}<br />з 06:00 {separator} 09:30<br />
                            з 22:00 {separator} {midnight}</p>
                            <p>📌 6.1<br />з 12:00 до 18:00</p>
                            """
                            days = self.parse(html)
                            self.assertEqual(len(days), 1)
                            self.assertEqual(days[0]["date"], "2026-11-07")
                            self.assertEqual(days[0]["schedule"], [
                                "06:00 до 09:30", "22:00 до 24:00",
                            ])
                            self.assertEqual(days[0]["outage_hours"], 5.5)

    def test_legacy_inline_queue_and_full_day_update(self):
        for marker in ("📢 ", ""):
            with self.subTest(marker=marker):
                html = f"""
                <p>{marker}Повідомляємо про зміни в ГПВ на 07 листопада:</p>
                <p>📌 6.2<br />✔️ з 00:00 по 02:00<br />✔️ з 16:30 по 20:00</p>
                <p>📌 6.1<br />✔️ з 12:00 по 18:00</p>
                <p>{marker}Повідомляємо, що 07 листопада
                застосовуватимуться відключення наступних черг:</p>
                <p>6.2 черга: з 06:00 до 09:30, з 16:30 до 20:00, з 23:30 до 24:00</p>
                """
                days = self.parse(html)
                self.assertEqual(len(days), 1)
                self.assertEqual(days[0]["schedule"], ["00:00 до 02:00", "16:30 до 20:00"])
                self.assertTrue(days[0]["has_update"])

    def test_multiple_days_without_markers(self):
        html = """
        <p>Повідомляємо, що 08 ЛИСТОПАДА застосовуватимуться відключення:</p>
        <p>6.2 черга: 06:00 до 09:30</p>
        """ + LIVE_FORMAT
        days = self.parse(html)
        self.assertEqual([day["date"] for day in days], ["2026-11-07", "2026-11-08"])
        self.assertEqual(days[0]["schedule"], ["10:00 до 17:00", "22:00 до 24:00"])
        self.assertEqual(days[1]["schedule"], ["06:00 до 09:30"])

    def test_next_queue_does_not_leak(self):
        self.assertEqual(self.parse(LIVE_FORMAT, "6.1")[0]["schedule"], [
            "03:00 до 06:30", "10:00 до 13:30", "20:30 до 24:00",
        ])

    def test_windowed_update_and_multiple_days(self):
        html = """
        <p>📢 Повідомляємо про зміни в ГПВ 07 ЛИСТОПАДА з 15:00 до 24:00</p>
        <p>📌 6.2<br />✔️ з 18:00 по 00:00</p>
        <p>📢 08 ЛИСТОПАДА застосовуватимуться відключення:</p>
        <p>6.2 черга: 06:00–09:30</p>
        """ + LIVE_FORMAT
        days = self.parse(html)
        self.assertEqual([day["date"] for day in days], ["2026-11-07", "2026-11-08"])
        self.assertEqual(days[0]["schedule"], ["10:00 до 15:00", "18:00 до 24:00"])
        self.assertTrue(days[0]["has_update"])
        self.assertEqual(days[1]["schedule"], ["06:00 до 09:30"])

    def test_midnight_at_start_is_unchanged(self):
        self.assertEqual(Parser._parse_ranges("00:00-03:00, 22:00-24:00"), [
            (0, 180), (1320, 1440),
        ])


if __name__ == "__main__":
    unittest.main()
