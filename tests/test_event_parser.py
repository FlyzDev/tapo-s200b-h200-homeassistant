import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER_PATH = (
    ROOT
    / "custom_components"
    / "tapo_s200b_cloud"
    / "event_parser.py"
)

spec = importlib.util.spec_from_file_location("tapo_event_parser", PARSER_PATH)
parser = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(parser)


class EventParserTests(unittest.TestCase):
    def setUp(self):
        self.button = {
            "thingName": "REDACTED_THING_ID",
            "model": "S200B",
        }

    def test_single_click(self):
        event = {
            "logId": "101",
            "name": "singleClick",
            "timestamp": 123,
            "params": {},
        }
        value = parser.normalize_event(event, self.button)
        self.assertEqual("single_click", value["action"])
        self.assertEqual(1, value["click_count"])
        self.assertEqual(101, value["log_id"])

    def test_double_click(self):
        event = {
            "logId": 102,
            "name": "doubleClick",
            "timestamp": 124,
        }
        value = parser.normalize_event(event, self.button)
        self.assertEqual("double_click", value["action"])
        self.assertEqual(2, value["click_count"])

    def test_clockwise_rotation(self):
        event = {
            "logId": 103,
            "name": "rotation",
            "params": {"rotate_deg": 15},
        }
        value = parser.normalize_event(event, self.button)
        self.assertEqual("rotate_clockwise", value["action"])
        self.assertEqual("clockwise", value["direction"])
        self.assertEqual(15, value["degrees"])

    def test_anti_clockwise_rotation(self):
        event = {
            "logId": 104,
            "name": "rotation",
            "params": {"rotate_deg": "-30"},
        }
        value = parser.normalize_event(event, self.button)
        self.assertEqual("rotate_anti_clockwise", value["action"])
        self.assertEqual(-30, value["degrees"])

    def test_unknown_is_not_dropped(self):
        event = {"logId": 105, "name": "futureEvent"}
        value = parser.normalize_event(event, self.button)
        self.assertEqual("unknown", value["action"])
        self.assertEqual("futureEvent", value["native_name"])

    def test_invalid_log_id_is_rejected(self):
        self.assertIsNone(
            parser.normalize_event(
                {"logId": "not-an-int", "name": "singleClick"},
                self.button,
            )
        )


if __name__ == "__main__":
    unittest.main()
