"""Native OpenATV binding stability and authenticated background switching."""

import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from test_receiver_plugin import PLUGIN, Pending, ROOT

HOTKEYS = sys.modules[PLUGIN.__package__ + ".hotkeys"]


class Registry:
    def __init__(self):
        self.items = []

    def getPlugins(self, where):
        return self.items

    def addPlugin(self, descriptor):
        self.items.append(descriptor)

    def removePlugin(self, descriptor):
        self.items.remove(descriptor)


def button_functions(registry):
    # ButtonSetup's persisted plugin-path/ordinal identifiers and name filter.
    paths, names, result = {}, set(), {}
    for descriptor in sorted(registry.items, key=lambda item: item.name):
        if descriptor.name in names:
            continue
        path = descriptor.path[descriptor.path.rfind("Plugins"):].replace("\\", "/")
        paths[path] = paths.get(path, 0) + 1
        result[path + "/" + str(paths[path])] = descriptor
        names.add(descriptor.name)
    return result


class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.config = dict(PLUGIN.DEFAULTS, url="http://ha.test:8123", token="dummy", language="de")
        self.pending, self.dialogs = [], []
        self.registry = Registry()
        self.session = types.SimpleNamespace(open=lambda *args, **kwargs: self.dialogs.append((args, kwargs)))
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.cache = HOTKEYS.HotkeyCache(str(Path(directory.name) / "hotkeys.json"))
        self.manager = HOTKEYS.Hotkeys(self.session, self.registry, cache=self.cache)
        self.addCleanup(self.manager.stop)
        self.client = Mock()
        self.client.get_menu.side_effect = lambda: copy.deepcopy(self.menu)

        def defer(work):
            pending = Pending(work)
            self.pending.append(pending)
            return pending

        for name, value in (("load_settings", lambda: dict(self.config)),
                            ("deferToThread", defer)):
            patcher = patch.object(HOTKEYS, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.object(self.manager, "client", return_value=self.client)
        patcher.start()
        self.addCleanup(patcher.stop)

    def refresh(self):
        self.manager.refresh()
        self.pending.pop().fire()

    def action(self):
        self.refresh()
        return next(item for item in self.registry.items if "Deckenlicht" in item.name).fnc

    def test_lists_only_switchable_entries_with_full_menu_paths_and_duplicate_entities(self):
        repeated = copy.deepcopy(self.menu["root"]["children"][0]["children"][0])
        repeated["id"] = "repeated"
        self.menu["root"]["children"][1]["children"].append(repeated)
        self.refresh()
        self.assertEqual(len(button_functions(self.registry)), 3)
        self.assertEqual({item.name for item in self.registry.items}, {
            "EnigmaHA: Home Assistant > Wohnzimmer > Deckenlicht – Umschalten",
            "EnigmaHA: Home Assistant > Flur > Flurlicht – Umschalten",
            "EnigmaHA: Home Assistant > Flur > Deckenlicht – Umschalten"})
        self.assertTrue(all(item.where == 25 and item.internal and not item.needsRestart
                            for item in self.registry.items))
        self.assertFalse(self.pending)

    def test_saved_native_binding_survives_rename_move_reorder_insert_remove_and_restart(self):
        self.refresh()
        functions = button_functions(self.registry)
        binding = next(key for key, item in functions.items() if "Deckenlicht" in item.name)
        ceiling = self.menu["root"]["children"][0]["children"].pop(0)
        ceiling["label"] = "Neuer Name"
        self.menu["root"]["children"][1]["children"] = [ceiling,
            dict(ceiling, id="aaa", label="AAA", entity_id="light.other")]
        self.menu["root"]["children"].reverse()
        self.menu["revision"] = 8
        self.refresh()
        selected = button_functions(self.registry)[binding]
        self.assertIn("Flur > Neuer Name", selected.name)
        selected.fnc(self.session)
        self.assertFalse(self.client.execute.called)
        self.pending.pop().fire()
        self.client.execute.assert_called_once_with({"schema_version": 1, "revision": 8,
                                                    "entry_id": "ceiling", "action": "toggle"})
        self.manager.stop()
        self.assertFalse(self.registry.items)
        self.manager = HOTKEYS.Hotkeys(self.session, self.registry, cache=self.cache)
        self.addCleanup(self.manager.stop)
        self.assertIn(binding, button_functions(self.registry))
        self.assertFalse(self.pending)

    def test_identical_labels_are_not_dropped_by_native_name_deduplication(self):
        ceiling = self.menu["root"]["children"][0]["children"][0]
        self.menu["root"]["children"][0]["children"].append(dict(ceiling, id="same-label"))
        self.refresh()
        self.assertEqual(len(button_functions(self.registry)), 3)

    def test_nested_input_boolean_and_revoked_login_refresh(self):
        nested = self.menu["root"]["children"][0]["children"][2]
        nested["children"].append({"type": "entity", "id": "helper", "label": "Helfer",
                                   "entity_id": "input_boolean.helper", "actions": ["toggle"]})
        self.refresh()
        names = {item.name for item in self.registry.items}
        self.assertIn("EnigmaHA: Home Assistant > Wohnzimmer > Fenster > Helfer – Umschalten", names)
        bindings = set(button_functions(self.registry))
        self.client.get_menu.side_effect = HOTKEYS.ClientError("unauthorized")
        self.refresh()
        self.assertFalse(self.registry.items)
        self.assertEqual(self.cache.load(self.config)["root"]["children"], [])
        self.client.get_menu.side_effect = lambda: copy.deepcopy(self.menu)
        self.refresh()
        self.assertEqual(set(button_functions(self.registry)), bindings)

    def test_revoked_removed_readonly_or_retargeted_entry_never_sends_a_command(self):
        action = self.action()
        original = copy.deepcopy(self.menu)
        for change in ("remove", "readonly", "retarget", "hidden"):
            with self.subTest(change=change):
                self.menu = copy.deepcopy(original)
                children = self.menu["root"]["children"][0]["children"]
                if change == "remove":
                    children.pop(0)
                elif change == "readonly":
                    children[0]["actions"] = []
                elif change == "retarget":
                    children[0]["entity_id"] = "light.different"
                else:
                    self.menu["root"]["children"] = []
                action(self.session)
                self.pending.pop().fire()
                self.client.execute.assert_not_called()
        self.assertEqual(len(self.dialogs), 4)
        self.refresh()
        self.assertFalse(self.registry.items)

    def test_network_failure_keeps_bindings_and_never_retries_an_uncertain_toggle(self):
        action = self.action()
        bindings = set(button_functions(self.registry))
        self.client.get_menu.side_effect = HOTKEYS.ClientError("connection_failed")
        self.refresh()
        self.assertEqual(set(button_functions(self.registry)), bindings)
        action(self.session)
        self.pending.pop().fire()
        self.client.execute.assert_not_called()
        self.client.get_menu.side_effect = lambda: copy.deepcopy(self.menu)
        self.client.execute.side_effect = HOTKEYS.ClientError("connection_failed")
        action(self.session)
        action(self.session)  # Key repeat while the command is in flight.
        self.assertEqual(len(self.pending), 1)
        self.pending.pop().fire()
        self.assertEqual(self.client.execute.call_count, 1)
        self.assertFalse(self.manager.switching)

    def test_credentials_changed_before_or_during_request_block_old_actions(self):
        action = self.action()
        self.config["token"] = "replacement"
        action(self.session)
        self.assertFalse(self.pending)
        self.client.execute.assert_not_called()
        self.config["token"] = "dummy"
        action(self.session)
        self.config["token"] = "replacement"
        self.pending.pop().fire()
        self.client.execute.assert_not_called()
        self.refresh()
        self.assertTrue(self.registry.items)

    def test_settings_change_and_shutdown_discard_pending_menu_results(self):
        self.manager.refresh()
        self.config["token"] = "replacement"
        self.pending.pop().fire()
        self.assertFalse(self.registry.items)
        self.manager.refresh()
        self.manager.stop()
        self.pending.pop().fire()
        self.assertFalse(self.registry.items)
        self.assertFalse(self.manager.waiters)

    def test_registry_reload_recovers_actions_and_english_labels_keep_ids(self):
        self.refresh()
        bindings = set(button_functions(self.registry))
        self.registry.items.clear()
        self.config["language"] = "en"
        self.refresh()
        self.assertEqual(set(button_functions(self.registry)), bindings)
        self.assertTrue(all(item.name.endswith("Toggle") for item in self.registry.items))

    def test_readonly_update_or_invalid_connection_does_not_break_session_start(self):
        self.config["url"] = ""
        self.manager.refresh()
        self.assertFalse(self.pending)
        self.assertFalse(self.registry.items)
        registry_module = types.SimpleNamespace(plugins=self.registry)
        native = self.native_setup()
        with patch.dict(sys.modules, {"Components.PluginComponent": registry_module,
                                     "Screens": types.SimpleNamespace(ButtonSetup=native)}), \
                patch.object(HOTKEYS, "HotkeyCache", return_value=self.cache), \
                patch.object(PLUGIN, "report_after_restart") as report, \
                patch.object(PLUGIN, "_HOTKEYS", None):
            PLUGIN.session_start(0, session=self.session)
            first = PLUGIN._HOTKEYS
            PLUGIN.session_start(0, session=self.session)
            self.assertTrue(first.closed)
            PLUGIN.session_start(1)
            self.assertIsNone(PLUGIN._HOTKEYS)
            self.assertEqual(report.call_count, 3)

    def native_setup(self):
        registry = self.registry

        class Setup:
            def __init__(self, session, args=None):
                self.session = session
                self.onClose, self.onFirstExecBegin = [], []
                self.ButtonSetupFunctions = list(button_functions(registry))
                self.getFunctions = Mock()

        class Select(dict):
            def __init__(self):
                self["list"] = types.SimpleNamespace(setList=Mock())
                self.getFunctionList = Mock(return_value=["fresh choices"])
                self.selected = ["unsaved selection"]

        return types.SimpleNamespace(ButtonSetup=Setup, ButtonSetupSelect=Select,
                                     getButtonSetupFunctions=lambda: list(button_functions(registry)))

    def test_opening_setup_fetches_once_and_refreshes_an_already_open_chooser(self):
        native = self.native_setup()
        original = native.ButtonSetup.__init__
        self.manager.stop()
        self.manager = HOTKEYS.Hotkeys(self.session, self.registry, native, self.cache)
        self.addCleanup(self.manager.stop)
        self.manager.client = Mock(return_value=self.client)
        self.assertFalse(self.pending)  # No startup request or periodic timer.
        self.assertFalse(hasattr(self.manager, "timer"))
        screen = native.ButtonSetup(self.session)
        self.assertFalse(self.pending)  # No HTTP inside the screen constructor.
        screen.onFirstExecBegin[0]()
        chooser = self.session.current_dialog = native.ButtonSetupSelect()
        self.pending.pop().fire()
        self.assertEqual(len(screen.ButtonSetupFunctions), 2)
        self.assertEqual(chooser.ButtonSetupFunctions, screen.ButtonSetupFunctions)
        chooser["list"].setList.assert_called_once_with(["fresh choices"])
        self.assertEqual(chooser.selected, ["unsaved selection"])
        self.assertFalse(self.pending)
        screen.getFunctions.assert_called_once()
        next_screen = native.ButtonSetup(self.session)
        next_screen.onFirstExecBegin[0]()
        self.pending.pop().fire()
        self.assertEqual(self.client.get_menu.call_count, 2)
        self.manager.stop()
        self.assertIs(native.ButtonSetup.__init__, original)

    def test_closed_setup_does_not_receive_a_late_refresh(self):
        native = self.native_setup()
        manager = HOTKEYS.Hotkeys(self.session, self.registry, native, self.cache)
        self.addCleanup(manager.stop)
        manager.client = Mock(return_value=self.client)
        screen = native.ButtonSetup(self.session)
        screen.onFirstExecBegin[0]()
        for callback in screen.onClose:
            callback()
        self.pending.pop().fire()
        screen.getFunctions.assert_not_called()

    def test_cache_is_private_access_bound_and_rejects_corruption(self):
        self.refresh()
        text = Path(self.cache.path).read_text(encoding="utf-8")
        self.assertNotIn(self.config["token"], text)
        self.assertNotIn(self.config["url"], text)
        self.assertEqual(self.cache.load(self.config), self.menu)
        self.assertIsNone(self.cache.load(dict(self.config, token="other-user")))
        self.assertIsNone(self.cache.load(dict(self.config, url="http://other-ha.test")))
        Path(self.cache.path).write_text('{"schema_version": 1}', encoding="utf-8")
        self.assertIsNone(self.cache.load(self.config))
        Path(self.cache.path).write_text('invalid-json', encoding="utf-8")
        self.assertIsNone(self.cache.load(self.config))

    def test_cache_storage_error_is_reported_without_claiming_a_successful_refresh(self):
        with patch.object(self.cache, "save", side_effect=OSError("full")):
            self.refresh()
        self.assertFalse(self.registry.items)
        self.assertIn("Dateirechte", self.dialogs[-1][0][1])
        self.assertFalse(self.manager.refreshing)

    def test_overlapping_setup_requests_share_the_worker_and_notify_both_screens(self):
        first, second = Mock(), Mock()
        self.manager.refresh(first)
        self.manager.refresh(second)
        self.assertEqual(len(self.pending), 1)
        self.pending.pop().fire()
        first.assert_called_once_with()
        second.assert_called_once_with()
        self.assertEqual(self.client.get_menu.call_count, 1)
        self.assertFalse(self.manager.waiters)
