"""Language catalogs and receiver state presentation."""

import json
from pathlib import Path
from string import Formatter
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]

from companion.i18n import ENGLISH, LANGUAGE_CHOICES, translate
from companion.navigation import Navigator


class LanguageTests(unittest.TestCase):
    def test_german_default_and_safe_formatted_translation(self):
        self.assertEqual(LANGUAGE_CHOICES, [("de", "Deutsch"), ("en", "English")])
        self.assertEqual(translate("Nicht verfügbar"), "Nicht verfügbar")
        self.assertEqual(translate("Nicht verfügbar", "en"), "Unavailable")
        self.assertEqual(translate("Nicht verfügbar", "fr"), "Nicht verfügbar")
        self.assertEqual(translate("{name} (Ersatz: Regular)", "en", name="My {font}"),
                         "My {font} (fallback: Regular)")
        for source, english in ENGLISH.items():
            with self.subTest(message=source):
                fields = lambda text: {key for _, key, _, _ in Formatter().parse(text) if key is not None}
                self.assertEqual(fields(source), fields(english))

    def test_ha_languages_have_the_same_complete_keys(self):
        def flatten(value, prefix=""):
            result = {}
            for key, item in value.items():
                path = prefix + "." + key
                if isinstance(item, dict):
                    result.update(flatten(item, path))
                else:
                    self.assertIsInstance(item, str)
                    self.assertTrue(item.strip())
                    result[path] = item
            return result

        catalogs = [flatten(json.loads((ROOT / "custom_components/enigmaha_companion/translations" /
                                       (language + ".json")).read_text(encoding="utf-8")))
                    for language in ("de", "en")]
        self.assertEqual(catalogs[0].keys(), catalogs[1].keys())
        self.assertNotEqual(catalogs[0][".config.step.user.description"],
                            catalogs[1][".config.step.user.description"])

    def test_navigation_translates_states_and_preserves_user_labels_and_measurements(self):
        menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        menu["root"]["children"] = [
            {"type": "entity", "id": "entry" + str(i), "label": "Eigener Name " + str(i),
             "entity_id": entity_id, "actions": []}
            for i, entity_id in enumerate(("light.on", "switch.off", "sensor.missing", "sensor.unavailable",
                                            "sensor.unknown", "sensor.temperature", "binary_sensor.door"))]
        states = {"light.on": {"state": "on"}, "switch.off": {"state": "off"},
                  "sensor.unavailable": {"state": "unavailable"}, "sensor.unknown": {"state": "unknown"},
                  "sensor.temperature": {"state": "22.5", "unit_of_measurement": "°C"},
                  "binary_sensor.door": {"state": "on"}}
        for language, expected in (
                ("de", ["Ein", "Aus", "Nicht vorhanden", "Nicht verfügbar", "Unbekannt", "22.5 °C", "on"]),
                ("en", ["On", "Off", "Not found", "Unavailable", "Unknown", "22.5 °C", "on"])):
            with self.subTest(language=language):
                navigator = Navigator(menu, language=language)
                rows = navigator.rows(states)
                self.assertEqual([value for _, value in rows], expected)
                self.assertEqual([label for label, _ in rows], [node["label"] for node in menu["root"]["children"]])


if __name__ == "__main__":
    unittest.main()
