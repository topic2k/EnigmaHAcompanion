import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]

from enigmaha_protocol import ActionError, ProtocolError, prepare_action, validate_menu
from companion.navigation import Navigator


class MenuTests(unittest.TestCase):
    def setUp(self):
        self.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.states = json.loads((ROOT / "protocol/states.example.json").read_text(encoding="utf-8"))["states"]
        self.light = self.menu["root"]["children"][0]["children"][0]
        self.command = {"schema_version": 1, "revision": 1, "entry_id": "ceiling", "action": "toggle"}

    def plan(self, command=None, permitted=True):
        return prepare_action(self.menu, command or self.command,
                              lambda entity: self.states.get(entity, {}).get("state"),
                              lambda entity: permitted)

    def test_valid_document_is_detached(self):
        result = validate_menu(self.menu)
        self.light["label"] = "Changed"
        self.assertEqual(result["root"]["children"][0]["children"][0]["label"], "Deckenlicht")

    def test_rejects_unknown_versions_fields_and_boolean_integers(self):
        for key, value in [("schema_version", 2), ("schema_version", True), ("revision", True), ("extra", 0)]:
            with self.subTest(key=key, value=value):
                document = copy.deepcopy(self.menu)
                document[key] = value
                with self.assertRaises(ProtocolError):
                    validate_menu(document)

    def test_duplicate_ids_rejected_even_across_menus(self):
        self.menu["root"]["children"][1]["children"][0]["id"] = "ceiling"
        with self.assertRaises(ProtocolError):
            validate_menu(self.menu)

    def test_read_only_domain_cannot_gain_action(self):
        self.light["entity_id"] = "sensor.temperature"
        with self.assertRaises(ProtocolError):
            validate_menu(self.menu)

    def test_invalid_entity_and_display(self):
        for entity in ["all", "light.x,light.y", "light.foo\n"]:
            self.light["entity_id"] = entity
            with self.assertRaises(ProtocolError):
                validate_menu(self.menu)
        self.light["entity_id"] = "light.valid"
        self.menu["display"]["font_size"] = 500
        with self.assertRaises(ProtocolError):
            validate_menu(self.menu)

    def test_depth_and_total_limits(self):
        node = self.menu["root"]
        for number in range(9):
            child = {"id": "n" + str(number), "type": "menu", "label": "Sub", "children": []}
            node["children"] = [child]
            node = child
        with self.assertRaises(ProtocolError):
            validate_menu(self.menu)
        self.menu["root"]["children"] = [dict(self.light, id="entry" + str(i)) for i in range(500)]
        with self.assertRaises(ProtocolError):
            validate_menu(self.menu)

    def test_service_plan_uses_configured_entity(self):
        self.assertEqual(self.plan(), {"domain": "light", "service": "toggle", "data": {"entity_id": "light.wohnzimmer"}})

    def test_injected_target_is_rejected(self):
        self.command["entity_id"] = "light.secret"
        with self.assertRaises(ActionError) as caught:
            self.plan()
        self.assertEqual(caught.exception.status, 400)

    def test_permission_is_enforced(self):
        with self.assertRaises(ActionError) as caught:
            self.plan(permitted=False)
        self.assertEqual(caught.exception.code, "forbidden")

    def test_stale_revision_read_only_and_missing_entry(self):
        cases = [(dict(self.command, revision=2), "stale_menu"),
                 (dict(self.command, entry_id="temperature"), "action_not_allowed"),
                 (dict(self.command, entry_id="absent"), "entry_not_found")]
        for command, code in cases:
            with self.subTest(code=code), self.assertRaises(ActionError) as caught:
                self.plan(command)
            self.assertEqual(caught.exception.code, code)

    def test_unavailable_or_missing_entity_cannot_switch(self):
        for state in ["unknown", "unavailable", "unexpected"]:
            self.states["light.wohnzimmer"]["state"] = state
            with self.assertRaises(ActionError):
                self.plan()
        del self.states["light.wohnzimmer"]
        with self.assertRaises(ActionError):
            self.plan()

    def test_navigation_restores_parent_selection(self):
        nav = Navigator(self.menu)
        nav.activate(self.states)
        nav.move(2)
        nav.activate(self.states)
        self.assertEqual(nav.breadcrumb, "Home Assistant / Wohnzimmer / Fenster")
        self.assertTrue(nav.back())
        self.assertEqual(nav.selection["id"], "windows")
        self.assertTrue(nav.back())
        self.assertFalse(nav.back())

    def test_empty_menu_and_wraparound(self):
        nav = Navigator(self.menu)
        nav.move(-1)
        self.assertEqual(nav.selection["id"], "hall")
        self.menu["root"]["children"] = []
        nav = Navigator(self.menu)
        nav.move(1)
        self.assertIsNone(nav.activate({}))
        self.assertEqual(nav.rows({}), [])

    def test_navigation_never_executes_sensor_or_missing_state(self):
        nav = Navigator(self.menu)
        nav.activate(self.states)
        self.assertEqual(nav.activate(self.states), self.command)
        self.assertIsNone(nav.activate({}))
        nav.move(1)
        self.assertIsNone(nav.activate(self.states))
        self.assertEqual(nav.rows(self.states)[1], ("Temperatur", "22.4 °C"))

    def test_display_override_does_not_mutate_menu(self):
        nav = Navigator(self.menu, {"font_size": 36})
        self.assertEqual(nav.display["font_size"], 36)
        self.assertEqual(self.menu["display"]["font_size"], 28)
        with self.assertRaises(ProtocolError):
            Navigator(self.menu, {"unknown": 1})


if __name__ == "__main__":
    unittest.main()
