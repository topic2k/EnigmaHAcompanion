"""Exercise the packaged Screen with Enigma2/Twisted interface doubles."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from unittest.mock import Mock
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/enigma2/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion"


class Screen(dict):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.onClose, self.onLayoutFinish = [], []
        self.onFirstExecBegin = []
        self.close_result = None

    def close(self, value=None):
        self.close_result = value
        for callback in self.onClose:
            callback()


class Label:
    def __init__(self, text):
        self.text = text

    def setText(self, text):
        self.text = text


class MenuList:
    def __init__(self, rows, **kwargs):
        self.rows, self.index = rows, 0
        self.l = types.SimpleNamespace(setFont=lambda *args: None, setItemHeight=lambda *args: None)

    def setList(self, rows):
        self.rows = rows

    def moveToIndex(self, index):
        self.index = index


class Timer:
    def __init__(self):
        self.callback, self.running = [], False

    def start(self, *args):
        self.running = True

    def stop(self):
        self.running = False


class ConfigText:
    def __init__(self, default=None, **kwargs):
        self.value = default


class ConfigPassword(ConfigText):
    pass


class ConfigInteger(ConfigText):
    pass


class ConfigYesNo:
    def __init__(self, default=False):
        self.value = default


class ConfigSelection:
    def __init__(self, choices, default=None):
        self.choices = choices
        self.value = default


class ConfigListScreen:
    def __init__(self, entries, session=None):
        self["config"] = types.SimpleNamespace(getCurrent=lambda: entries[0], invalidateCurrent=lambda: None)


class Pending:
    def __init__(self, work):
        self.work = work

    def addCallbacks(self, success, failure):
        self.success, self.failure = success, failure

    def fire(self):
        try:
            result = self.work()
        except Exception as error:
            return self.failure(types.SimpleNamespace(value=error))
        return self.success(result)


class PluginDescriptor:
    WHERE_PLUGINMENU, WHERE_EXTENSIONSMENU, WHERE_MENU, WHERE_SESSIONSTART = 1, 2, 3, 4
    WHERE_BUTTONSETUP = 25

    def __init__(self, **kwargs):
        self.name, self.weight, self.path = "Plugin", 0, None
        self.function = kwargs.get("fnc")
        self.__dict__.update(kwargs)

    def updateIcon(self, path):
        self.path = path

    # Match OpenATV's sorting contract, including its reflected comparison.
    def __lt__(self, other):
        return self.weight < other.weight or (self.weight == other.weight and self.name < other.name)

    def __gt__(self, other):
        return other < self

    def __eq__(self, other):
        return self.function == other.function


def load_receiver():
    package = types.ModuleType("eha_receiver_test")
    package.__path__ = [str(BUNDLE)]
    sys.modules[package.__name__] = package
    fake = {}
    for name in ("Components", "Components.ActionMap", "Components.Label", "Components.MenuList",
                 "Components.MultiContent", "Components.ConfigList", "Components.config", "Plugins",
                 "Plugins.Plugin", "Screens", "Screens.Screen", "Screens.MessageBox",
                 "Screens.VirtualKeyBoard", "Screens.ChoiceBox", "enigma", "twisted", "twisted.internet", "twisted.internet.threads",
                 "Tools", "Tools.LoadPixmap"):
        fake[name] = types.ModuleType(name)
    fake["Components.ActionMap"].ActionMap = lambda contexts, actions, priority: types.SimpleNamespace(actions=actions)
    fake["Components.Label"].Label = Label
    fake["Components.MenuList"].MenuList = MenuList
    fake["Components.MultiContent"].MultiContentEntryText = lambda **kwargs: kwargs
    fake["Components.MultiContent"].MultiContentEntryPixmapAlphaBlend = lambda **kwargs: dict(kwargs, kind="pixmap")
    fake["Tools.LoadPixmap"].LoadPixmap = lambda path, **kwargs: {"svg": Path(path).read_text(), **kwargs}
    fake["Components.ConfigList"].ConfigListScreen = ConfigListScreen
    config = fake["Components.config"]
    config.ConfigText, config.ConfigInteger, config.ConfigPassword = ConfigText, ConfigInteger, ConfigPassword
    config.ConfigYesNo = ConfigYesNo
    config.ConfigSelection = ConfigSelection
    config.getConfigListEntry = lambda *args: args
    fake["Plugins.Plugin"].PluginDescriptor = PluginDescriptor
    fake["Screens.Screen"].Screen = Screen
    fake["Screens.MessageBox"].MessageBox = type("MessageBox", (), {"TYPE_ERROR": 0, "TYPE_INFO": 1, "TYPE_YESNO": 2})
    fake["Screens.VirtualKeyBoard"].VirtualKeyBoard = object
    fake["Screens.ChoiceBox"].ChoiceBox = type("ChoiceBox", (), {})
    enigma = fake["enigma"]
    enigma.eListboxPythonMultiContent, enigma.eTimer = object, Timer
    enigma.eSize = lambda width, height: types.SimpleNamespace(width=lambda: width, height=lambda: height)
    enigma.getDesktop = lambda _: types.SimpleNamespace(size=lambda: types.SimpleNamespace(width=lambda: 1280, height=lambda: 720))
    enigma.gFont, enigma.RT_VALIGN_CENTER = lambda *args: args, 1
    enigma.getFontFaces = lambda: ["Regular"]
    fake["twisted.internet.threads"].deferToThread = lambda work: Pending(work)
    spec = importlib.util.spec_from_file_location(package.__name__ + ".plugin", BUNDLE / "plugin.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake):
        spec.loader.exec_module(module)
        bundled = {name: value for name, value in sys.modules.items()
                   if name.startswith(package.__name__ + ".")}
    sys.modules.update(bundled)
    return module


PLUGIN = load_receiver()


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.states = json.loads((ROOT / "protocol/states.example.json").read_text(encoding="utf-8"))["states"]
        self.pending, self.commands, self.dialogs = [], [], []
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        updater = PLUGIN.ReceiverUpdater(str(Path(directory.name) / "update.json"))
        factory = patch.object(PLUGIN, "ReceiverUpdater", return_value=updater)
        factory.start()
        self.addCleanup(factory.stop)
        self.position_path = Path(directory.name) / "position.json"
        self.position = PLUGIN.MenuPosition(str(self.position_path))
        position_factory = patch.object(PLUGIN, "MenuPosition", return_value=self.position)
        position_factory.start()
        self.addCleanup(position_factory.stop)
        # Isolated tests must not inherit the target receiver's installed settings.
        load_settings = PLUGIN.load_settings
        settings = patch.object(PLUGIN, "load_settings", side_effect=lambda *args, **kwargs:
                                load_settings(*args, **kwargs) if args or kwargs else dict(PLUGIN.DEFAULTS, language="de"))
        settings.start()
        self.addCleanup(settings.stop)
        session = types.SimpleNamespace(open=lambda *args, **kwargs: self.dialogs.append((args, kwargs)),
                                      openWithCallback=lambda *args, **kwargs: self.dialogs.append(args if not kwargs else (args, kwargs)))
        self.screen = PLUGIN.CompanionScreen(session)
        self.addCleanup(self.screen.cleanup)
        # Enigma2's skin loader owns Screen.scale and replaces it during layout.
        self.screen.scale = ((1, 1), (1, 1))
        self.screen.config = dict(PLUGIN.DEFAULTS, url="http://ha.test:8123", token="dummy")
        self.screen.client = types.SimpleNamespace(get_menu=lambda: self.menu,
             get_update=lambda: None, get_states=lambda menu: self.states, execute=lambda command: self.commands.append(command))
        identity = patch.object(PLUGIN, "load_receiver_id", return_value="a" * 32)
        identity.start()
        self.addCleanup(identity.stop)
        def defer(work):
            item = Pending(work)
            self.pending.append(item)
            return item
        self.worker = patch.object(PLUGIN, "deferToThread", defer)
        self.worker.start()
        self.addCleanup(self.worker.stop)
        self.screen.refresh()
        self.pending.pop().fire()

    def press(self, key):
        self.screen["actions"].actions[key]()

    def reopen_menu(self, config=None, menu=None):
        with patch.object(PLUGIN, "load_settings", return_value=config or self.screen.config):
            screen = PLUGIN.CompanionScreen(self.screen.session)
        self.addCleanup(screen.cleanup)
        screen.loaded((menu or self.menu, self.states), screen.generation)
        return screen

    def test_menu_position_option_defaults_on_and_saves_without_changing_legacy_settings(self):
        settings = sys.modules[PLUGIN.__package__ + ".settings"]
        legacy = dict(self.screen.config)
        legacy.pop("remember_menu_position")
        path = self.position_path.with_name("settings.json")
        path.write_text(json.dumps(legacy), encoding="utf-8")
        before = path.read_bytes()
        loaded = settings.load_settings(str(path))
        self.assertTrue(loaded["remember_menu_position"])
        self.assertEqual(path.read_bytes(), before)
        setup = PLUGIN.CompanionSetup(self.screen.session, loaded)
        self.assertIsInstance(setup.fields["remember_menu_position"], ConfigYesNo)
        self.assertTrue(setup.fields["remember_menu_position"].value)
        setup.fields["remember_menu_position"].value = False
        setup.cancel()
        self.assertEqual(path.read_bytes(), before)
        with patch.dict(setup.save.__globals__, save_settings=lambda values: settings.save_settings(values, str(path))):
            setup.save()
        self.assertEqual(settings.load_settings(str(path)), dict(legacy, remember_menu_position=False))
        for invalid in (None, 0, 1, "true", [], {}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                settings.validate_settings(dict(legacy, remember_menu_position=invalid))

    def test_menu_position_survives_reopening_and_list_reordering_by_id(self):
        self.press("ok")
        self.press("down")
        self.press("down")
        self.press("ok")
        expected = self.screen.nav.position()
        self.screen.close()
        saved = self.position_path.read_text()
        self.assertNotIn(self.screen.config["token"], saved)
        self.assertNotIn(self.screen.config["url"], saved)
        reordered = json.loads(json.dumps(self.menu))
        reordered["root"]["children"].reverse()
        reopened = self.reopen_menu(menu=reordered)
        self.assertEqual(reopened.nav.position(), expected)
        self.assertEqual(reopened.nav.current["id"], "windows")
        self.assertEqual(self.commands, [])

    def test_menu_position_disabled_starts_at_root_and_keeps_saved_position(self):
        self.press("ok")
        self.press("down")
        self.screen.close()
        before = self.position_path.read_bytes()
        disabled = dict(self.screen.config, remember_menu_position=False)
        reopened = self.reopen_menu(config=disabled)
        self.assertEqual(reopened.nav.stack, [("home", 0)])
        reopened.move(1)
        reopened.close()
        self.assertEqual(self.position_path.read_bytes(), before)

    def test_menu_position_does_not_cross_ha_origins_or_tokens(self):
        self.press("ok")
        self.screen.close()
        for change in ({"url": "https://other.test"}, {"token": "different-token"}):
            with self.subTest(change=change):
                reopened = self.reopen_menu(config=dict(self.screen.config, **change))
                self.assertEqual(reopened.nav.stack, [("home", 0)])

    def test_menu_position_handles_removed_or_invalid_entries_and_storage_failures(self):
        self.press("ok")
        self.press("down")
        self.press("down")
        self.screen.close()
        changed = json.loads(json.dumps(self.menu))
        changed["root"]["children"][0]["children"].pop()
        reopened = self.reopen_menu(menu=changed)
        self.assertEqual(reopened.nav.current["id"], "living-room")
        self.assertEqual(reopened.nav.selection["id"], "ceiling")
        removed = json.loads(json.dumps(self.menu))
        removed["root"]["children"].pop(0)
        reopened = self.reopen_menu(menu=removed)
        self.assertEqual(reopened.nav.stack, [("home", 0)])
        moved = json.loads(json.dumps(self.menu))
        child = moved["root"]["children"][0]["children"].pop()
        moved["root"]["children"][1]["children"].append(child)
        reopened = self.reopen_menu(menu=moved)
        self.assertEqual(reopened.nav.current["id"], "living-room")
        replaced_root = json.loads(json.dumps(self.menu))
        replaced_root["root"]["id"] = "new_root"
        reopened = self.reopen_menu(menu=replaced_root)
        self.assertEqual(reopened.nav.stack, [("new_root", 0)])
        valid = self.position_path.read_text()
        invalid_documents = ["not json", "[]", "x" * 9000]
        for path in ([], [["home"]], [[True, None]], [["home", "bad/id"]], [["home", None]] * 10):
            data = json.loads(valid)
            data["path"] = path
            invalid_documents.append(json.dumps(data))
        for data in invalid_documents:
            with self.subTest(data=data[:40]):
                self.position_path.write_text(data)
                reopened = self.reopen_menu()
                self.assertEqual(reopened.nav.stack, [("home", 0)])
        with patch.object(self.position, "save", side_effect=OSError("readonly")):
            reopened.close()
        self.assertTrue(reopened.closed)

    def test_menu_position_refresh_preserves_current_selection_and_update_guard_does_not_save(self):
        self.press("ok")
        self.screen.close()
        reopened = self.reopen_menu()
        reopened.move(1)
        reopened.loaded((self.menu, self.states), reopened.generation)
        self.assertEqual(reopened.nav.selection["id"], "temperature")
        before = self.position_path.read_bytes()
        reopened.update_installing = True
        reopened.close()
        self.assertFalse(reopened.closed)
        self.assertEqual(self.position_path.read_bytes(), before)

    def test_matching_protocol_with_different_release_stays_connected(self):
        self.screen.client.peer_version = "9.0.0"
        self.screen.loaded((self.menu, self.states), self.screen.generation)
        self.assertTrue(self.screen.online)
        self.assertIn("HA 9.0.0", self.screen["status"].text)
        self.assertIn("Protokoll 1 passt", self.screen["status"].text)
        self.assertEqual(self.dialogs, [])

    def test_protocol_conflict_is_explained_once_and_recovery_clears_notice(self):
        error = PLUGIN.ClientError("protocol_mismatch", peer_version="9.0.0", peer_protocol=2)
        failure = types.SimpleNamespace(value=error)
        self.screen.failed(failure, self.screen.generation)
        self.assertFalse(self.screen.online)
        self.assertIn("Protokolle ungleich", self.screen["status"].text)
        self.assertIn("Reparatur", self.dialogs[-1][1]["title"])
        self.assertEqual(self.dialogs[-1][0][1], PLUGIN.ChoiceBox)
        self.screen.failed(failure, self.screen.generation)
        self.assertEqual(len(self.dialogs), 1)
        self.screen.loaded((self.menu, self.states), self.screen.generation)
        self.assertTrue(self.screen.online)
        self.assertIsNone(self.screen.peer_notice)

    def test_language_setting_defaults_persists_and_rejects_invalid_values(self):
        settings = sys.modules[PLUGIN.__package__ + ".settings"]
        self.assertEqual(settings.validate_settings({})["language"], "de")
        for invalid in (None, True, [], {}, "fr", "EN"):
            with self.subTest(language=invalid), self.assertRaises(ValueError):
                settings.validate_settings({"language": invalid})
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "settings.json")
            values = dict(self.screen.config)
            settings.save_settings(values, path)
            original = Path(path).read_bytes()
            setup = PLUGIN.CompanionSetup(self.screen.session, values)
            self.assertEqual(setup.selection_choices["language"], [("de", "Deutsch"), ("en", "English"), ("auto", "Automatisch")])
            setup.fields["language"].value = "en"
            setup.cancel()
            self.assertEqual(Path(path).read_bytes(), original)
            with patch.dict(setup.save.__globals__, {"save_settings": lambda data: settings.save_settings(data, path)}):
                setup.save()
            saved = settings.load_settings(path)
            self.assertEqual(saved["language"], "en")
            self.assertEqual(saved["url"], values["url"])
            self.assertEqual(saved["token"], values["token"])
            self.assertEqual(setup.close_result, saved)
            reopened = PLUGIN.CompanionSetup(self.screen.session, saved)
            self.assertEqual(reopened["config"].getCurrent()[0], "Language (from next opening)")
            self.assertEqual(reopened.selection_choices["font_family"][0], ("", "Auto (skin/receiver default)"))
            self.assertEqual(reopened.fields["show_in_mainmenu"].descriptions, {False: "No", True: "Yes"})
            self.assertIn("Green: Save", reopened["hint"].text)
            def fail_save(data):
                raise OSError()
            with patch.dict(reopened.save.__globals__, {"save_settings": fail_save}):
                reopened.save()
            self.assertIn("Could not save settings", self.dialogs[-1][0][1])

    def test_new_install_uses_auto_and_existing_settings_keep_their_language(self):
        settings = types.SimpleNamespace(load_settings=PLUGIN.load_settings,
                                         save_settings=PLUGIN.CompanionSetup.save.__globals__["save_settings"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            fresh = settings.load_settings(str(path))
            self.assertEqual(fresh["language"], "auto")
            self.assertFalse(path.exists())
            setup = PLUGIN.CompanionSetup(self.screen.session, fresh)
            self.assertEqual(setup.fields["language"].value, "auto")
            old = dict(self.screen.config)
            old.pop("language")
            for preference in (None, "de", "en", "auto"):
                with self.subTest(preference=preference):
                    stored = dict(old)
                    if preference is not None:
                        stored["language"] = preference
                    path.write_text(json.dumps(stored), encoding="utf-8")
                    original = path.read_bytes()
                    loaded = settings.load_settings(str(path))
                    self.assertEqual(loaded["language"], preference or "de")
                    self.assertEqual(loaded["url"], old["url"])
                    self.assertEqual(loaded["token"], old["token"])
                    self.assertEqual(path.read_bytes(), original)
                    settings.save_settings(loaded, str(path))
                    self.assertEqual(settings.load_settings(str(path)), loaded)

    def test_automatic_language_uses_openatv_and_persists_the_mode(self):
        settings = types.SimpleNamespace(load_settings=PLUGIN.load_settings,
                                         save_settings=PLUGIN.CompanionSetup.save.__globals__["save_settings"])
        native = types.SimpleNamespace(international=types.SimpleNamespace(getLocale=lambda: "en_GB"))
        values = dict(self.screen.config, language="auto")
        with patch.dict(sys.modules, {"Components.International": native}):
            with patch.object(PLUGIN, "load_settings", return_value=values):
                screen = PLUGIN.CompanionScreen(self.screen.session)
            self.addCleanup(screen.cleanup)
            self.assertEqual(screen.appearance.language, "en")
            self.assertEqual(screen.config["language"], "auto")
            self.assertEqual(screen["status"].text, "Preparing connection …")
            screen.loaded((self.menu, self.states), screen.generation)
            self.assertEqual(screen.nav.language, "en")
            setup = PLUGIN.CompanionSetup(self.screen.session, values)
            self.assertEqual(setup.fields["language"].value, "auto")
            self.assertEqual(setup.selection_choices["language"][-1], ("auto", "Automatic"))
            self.assertIn("Green: Save", setup["hint"].text)
            with tempfile.TemporaryDirectory() as directory:
                path = str(Path(directory) / "settings.json")
                with patch.dict(setup.save.__globals__, {"save_settings": lambda data: settings.save_settings(data, path)}):
                    setup.save()
                self.assertEqual(settings.load_settings(path)["language"], "auto")
            native.international.getLocale = lambda: "de_DE"
            reopened = PLUGIN.CompanionSetup(self.screen.session, values)
            self.assertEqual(reopened.fields["language"].value, "auto")
            self.assertIn("Grün: Speichern", reopened["hint"].text)

    def test_english_screen_help_errors_and_state_text(self):
        with patch.object(PLUGIN, "load_settings", return_value=dict(self.screen.config, language="en")):
            screen = PLUGIN.CompanionScreen(self.screen.session)
        self.addCleanup(screen.cleanup)
        self.assertEqual(screen["status"].text, "Preparing connection …")
        self.assertIn("Menu/Blue: Settings", screen["footer"].text)
        screen.loaded((self.menu, self.states), screen.generation)
        self.assertEqual(screen["status"].text, "Connected")
        self.assertEqual(screen.nav.language, "en")
        screen.help()
        self.assertIn("Up/Down: Select entry", self.dialogs[-1][0][1])
        self.assertIn("Ch+ up / − down", self.dialogs[-1][0][1])
        screen.config["reverse_channel_paging"] = True
        screen.help()
        self.assertIn("Ch+ down / − up", self.dialogs[-1][0][1])
        screen.failed(types.SimpleNamespace(value=PLUGIN.ClientError("unauthorized")), screen.generation)
        self.assertEqual(screen["status"].text, "Token rejected. Menu: Settings")
        self.assertIsNone(screen.nav)
        self.assertEqual(screen["heading"].text, "OFFLINE – Home Assistant")

    def test_skin_xml_and_all_required_keys(self):
        ET.fromstring(self.screen.skin)
        keymap = ET.parse(BUNDLE / "keymap.xml")
        mappings = {key.attrib["id"]: key.attrib["mapto"] for key in keymap.findall(".//key")}
        for key in ("KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT", "KEY_MENU", "KEY_OK", "KEY_EXIT",
                    "KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            self.assertIn(mappings[key], self.screen["actions"].actions)

    def test_channel_keys_page_through_list_and_stop_at_boundaries(self):
        mappings = {key.attrib["id"]: key.attrib for key in
                    ET.parse(BUNDLE / "keymap.xml").findall(".//key")}
        for key in ("KEY_CHANNELUP", "KEY_CHANNELDOWN"):
            self.assertEqual(mappings[key]["flags"], "mr")
        for count, reverse in ((count, reverse) for count in (0, 1, 3, 5, 12) for reverse in (False, True)):
            with self.subTest(entries=count, reverse=reverse):
                self.screen.config["reverse_channel_paging"] = reverse
                up, down = ("KEY_CHANNELDOWN", "KEY_CHANNELUP") if reverse else ("KEY_CHANNELUP", "KEY_CHANNELDOWN")
                self.menu["root"]["children"] = [
                    {"id": "item" + str(i), "type": "menu", "label": str(i), "children": []}
                    for i in range(count)]
                self.screen.nav = PLUGIN.Navigator(self.menu)
                self.screen.render()
                self.screen.list_height = self.screen.row_height * 5 + self.screen.row_height // 2
                for key, expected in ((up, 0),
                                      (down, min(5, max(0, count - 1))),
                                      (down, min(10, max(0, count - 1))),
                                      (down, max(0, count - 1)),
                                      (down, max(0, count - 1)),
                                      (up, max(0, count - 6)),
                                      (up, max(0, count - 11)),
                                      (up, 0)):
                    self.press(mappings[key]["mapto"])
                    self.assertEqual(self.screen.nav.stack[-1][1], expected)
                    self.assertEqual(self.screen["list"].index, expected)
                self.assertEqual(self.commands, [])

    def test_recall_only_goes_back_and_exit_or_red_close_from_a_submenu(self):
        mappings = {key.attrib["id"]: key.attrib["mapto"] for key in
                    ET.parse(BUNDLE / "keymap.xml").findall(".//key")}
        self.press(mappings["KEY_BACK"])
        self.assertEqual(len(self.screen.nav.stack), 1)
        self.assertFalse(self.screen.closed)
        self.press("ok")
        self.press("down")
        self.press("down")
        self.press("ok")
        self.assertEqual(len(self.screen.nav.stack), 3)
        self.press(mappings["KEY_BACK"])
        self.assertEqual(len(self.screen.nav.stack), 2)
        self.assertEqual(self.screen.nav.selection["id"], "windows")
        self.press(mappings["KEY_BACK"])
        self.assertEqual(self.screen.nav.selection["id"], "living-room")
        for key in ("KEY_EXIT", "KEY_RED"):
            self.screen.closed = False
            self.press("ok")
            self.press(mappings[key])
            self.assertTrue(self.screen.closed)
            self.screen.nav.back()

    def test_horizontal_keys_page_without_opening_or_toggling_and_ignore_channel_reversal(self):
        mappings = {key.attrib["id"]: key.attrib for key in
                    ET.parse(BUNDLE / "keymap.xml").findall(".//key")}
        for key in ("KEY_LEFT", "KEY_RIGHT"):
            self.assertEqual(mappings[key]["flags"], "mr")
        for count in (0, 1, 3, 12):
            for reverse in (False, True):
                with self.subTest(entries=count, reverse=reverse):
                    self.screen.config["reverse_channel_paging"] = reverse
                    self.menu["root"]["children"] = [
                        {"id": "item" + str(i), "type": "menu", "label": str(i), "children": []}
                        for i in range(count)]
                    self.screen.nav = PLUGIN.Navigator(self.menu)
                    self.screen.render()
                    self.screen.list_height = self.screen.row_height * 5
                    for key, position in (("KEY_LEFT", 0), ("KEY_RIGHT", min(5, max(0, count-1))),
                                          ("KEY_RIGHT", min(10, max(0, count-1))),
                                          ("KEY_RIGHT", max(0, count-1)), ("KEY_LEFT", max(0, count-6))):
                        self.press(mappings[key]["mapto"])
                        self.assertEqual(self.screen.nav.stack, [("home", position)])
        self.assertEqual(self.commands, [])
        self.assertEqual(self.pending, [])

    def test_info_uses_worker_and_preserves_navigation_and_refresh(self):
        data = {"user_name": "Anna {user}\nReceiver", "menus": 2, "submenus": 3,
                "lights": 4, "switches": 5, "sensors": 6, "other_entities": 7}
        self.screen.client.get_info = lambda: data
        self.screen.client.peer_version = "9.0.0"
        self.press("ok")
        stack = list(self.screen.nav.stack)
        status = self.screen["status"].text
        self.press("info")
        self.press("info")
        self.assertEqual(len(self.pending), 1)
        self.assertEqual(self.dialogs, [])
        self.pending.pop().fire()
        text = self.dialogs[-1][0][1]
        for expected in ("Version auf dem Receiver: " + PLUGIN.VERSION, "Version in Home Assistant: 9.0.0", "Anna {user} Receiver",
                         "Menüs: 2", "Untermenüs: 3", "Entitäten: 22"):
            self.assertIn(expected, text)
        self.assertNotIn("Lichter:", text)
        self.assertNotIn("Weitere Entitäten:", text)
        self.assertEqual(self.screen.nav.stack, stack)
        self.assertEqual(self.screen["status"].text, status)
        self.assertTrue(self.screen.timer.running)
        self.assertFalse(self.screen.busy)
        self.assertEqual(self.commands, [])

    def test_info_old_integration_offline_and_request_failure_keep_menu_usable(self):
        self.screen.client.get_info = lambda: None
        self.press("info")
        self.pending.pop().fire()
        self.assertIn("nicht abrufbar", self.dialogs[-1][0][1])
        def fail():
            raise PLUGIN.ClientError("connection_failed")
        self.screen.client.get_info = fail
        self.press("info")
        self.pending.pop().fire()
        self.assertIsNone(self.screen.info_pending)
        self.assertTrue(self.screen.online)
        self.screen.online = False
        self.press("info")
        self.assertEqual(self.pending, [])
        self.assertIn(PLUGIN.VERSION, self.dialogs[-1][0][1])

    def test_info_discards_results_after_close_or_identity_change_and_translates(self):
        self.screen.client.get_info = lambda: None
        self.press("info")
        self.screen.generation += 1
        self.pending.pop().fire()
        self.assertEqual(self.dialogs, [])
        self.press("info")
        self.screen.close()
        self.pending.pop().fire()
        self.assertEqual(self.dialogs, [])
        self.screen.appearance.language = "en"
        self.screen.show_information({"user_name": "Anna", "menus": 1, "submenus": 2,
                                     "lights": 3, "switches": 4, "sensors": 5, "other_entities": 6})
        text = self.dialogs[-1][0][1]
        self.assertIn("Logged-in user: Anna", text)
        self.assertIn("Submenus: 2", text)
        self.assertIn("Entities: 18", text)
        self.assertIn("Version on the receiver: " + PLUGIN.VERSION, text)
        self.assertIn("Version in Home Assistant:", text)

    def test_receiver_font_choices_use_registered_fonts_and_keep_saved_preferences(self):
        with patch.dict(PLUGIN.CompanionSetup.__init__.__globals__,
                        getFontFaces=lambda: ["Regular", "SkinFont", "Italic", "SkinFont"]):
            setup = PLUGIN.CompanionSetup(self.screen.session, dict(self.screen.config, font_family="OldFont", font_size=31))
        self.assertIsInstance(setup.fields["font_family"], ConfigSelection)
        self.assertIsInstance(setup.fields["font_size"], ConfigSelection)
        self.assertNotIsInstance(setup.fields["font_family"], ConfigText)
        self.assertEqual(setup.selection_choices["font_family"], [
            ("", "Auto (Skin-/Receiver-Standard)"), ("Italic", "Italic"), ("Regular", "Regular"),
            ("SkinFont", "SkinFont"), ("OldFont", "OldFont (Ersatz: Regular)")])
        self.assertEqual(setup.fields["font_family"].value, "OldFont")
        self.assertEqual(setup.fields["font_size"].value, "31")
        self.assertEqual([value for value, _ in setup.selection_choices["font_size"]],
                         ["0"] + [str(size) for size in range(16, 65)])

    def test_receiver_font_choice_dialog_cancel_select_save_and_auto(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["save_settings"])
        dialogs = []
        session = types.SimpleNamespace(open=lambda *args, **kwargs: dialogs.append((args, kwargs)),
                                        openWithCallback=lambda *args, **kwargs: dialogs.append((args, kwargs)))
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "config.json")
            settings.save_settings(self.screen.config, path)
            with patch.dict(PLUGIN.CompanionSetup.save.__globals__,
                            save_settings=lambda values: settings.save_settings(values, path)):
                setup = PLUGIN.CompanionSetup(session, settings.load_settings(path))
                for key, value in (("font_family", "Regular"), ("font_size", "64")):
                    field = setup.fields[key]
                    setup["config"].getCurrent = lambda: (key, field)
                    setup.edit()
                    (callback, dialog), options = dialogs[-1]
                    self.assertIs(dialog, PLUGIN.CompanionSetup.edit.__globals__["ChoiceBox"])
                    original = field.value
                    callback(None)
                    self.assertEqual(field.value, original)
                    callback(next(entry for entry in options["list"] if entry[1] == value))
                    self.assertEqual(field.value, value)
                setup.cancel()
                self.assertEqual(settings.load_settings(path)["font_size"], 0)
                setup.save()
                self.assertEqual(settings.load_settings(path)["font_family"], "Regular")
                self.assertEqual(settings.load_settings(path)["font_size"], 64)
                for key in ("font_family", "font_size"):
                    setup.fields[key].value = setup.selection_choices[key][0][0]
                setup.save()
                self.assertEqual(settings.load_settings(path)["font_family"], "")
                self.assertEqual(settings.load_settings(path)["font_size"], 0)

    def test_channel_direction_setting_save_cancel_and_help(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["save_settings"])
        self.assertFalse(settings.validate_settings({})["reverse_channel_paging"])
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "config.json")
            settings.save_settings(self.screen.config, path)
            with patch.dict(PLUGIN.CompanionSetup.save.__globals__,
                            save_settings=lambda values: settings.save_settings(values, path)):
                setup = PLUGIN.CompanionSetup(self.screen.session, settings.load_settings(path))
                self.assertIsInstance(setup.fields["reverse_channel_paging"], ConfigYesNo)
                setup.fields["reverse_channel_paging"].value = True
                setup.cancel()
                self.assertFalse(settings.load_settings(path)["reverse_channel_paging"])
                for reverse in (True, False):
                    setup = PLUGIN.CompanionSetup(self.screen.session, settings.load_settings(path))
                    setup.fields["reverse_channel_paging"].value = reverse
                    setup.save()
                    self.assertEqual(settings.load_settings(path)["reverse_channel_paging"], reverse)
                    self.screen.settings_done(setup.close_result)
                    self.pending.pop().fire()
                    self.press("help")
                    expected = "Ch+ abwärts / − aufwärts" if reverse else "Ch+ aufwärts / − abwärts"
                    self.assertIn(expected, self.dialogs[-1][0][1])
                    self.press("channelPlus" if reverse else "channelMinus")
                    self.assertEqual(self.screen.nav.stack[-1][1], 1)
                    self.press("channelMinus" if reverse else "channelPlus")
                    self.assertEqual(self.screen.nav.stack[-1][1], 0)
        for invalid in ("false", 0, 1, None):
            with self.assertRaises(ValueError):
                settings.validate_settings(dict(self.screen.config, reverse_channel_paging=invalid))

    def test_external_skin_list_geometry_is_used_after_layout(self):
        resized = []
        self.screen["list"].instance = types.SimpleNamespace(size=lambda: types.SimpleNamespace(
            width=lambda: 850, height=lambda: 360), resize=resized.append)
        for callback in self.screen.onLayoutFinish:
            callback()
        self.assertEqual((self.screen.list_width, self.screen.list_height), (850, 360))
        self.assertEqual(self.screen.page_size(), 360 // self.screen.row_height)
        self.assertEqual(resized[-1].height() % self.screen.row_height, 0)
        self.assertLessEqual(resized[-1].height(), 360)
        self.assertEqual(resized[-1].width(), 850)
        self.assertEqual(self.screen.skinName[0], "EnigmaHACompanion")
        for row in self.screen["list"].rows:
            for entry in row[1:]:
                self.assertLessEqual(entry["pos"][0] + entry["size"][0], 850)

    def test_receiver_fonts_ignore_legacy_ha_display_and_apply_local_choices(self):
        fonts, heights = [], []
        self.screen["list"].l.setFont = lambda index, font: fonts.append(font)
        self.screen["list"].l.setItemHeight = heights.append
        self.menu["display"] = {"font_family": "LegacyHAFont", "font_size": 64}
        self.screen.loaded((self.menu, self.states), self.screen.generation)
        self.assertEqual(fonts[-1], ("Regular", 28))
        self.assertEqual(heights[-1], 42)
        # The skin default is already in desktop pixels; it is not scaled again.
        parse = types.SimpleNamespace(parseFont=Mock(return_value=types.SimpleNamespace(
            family="SkinFont", pointSize=37)))
        self.screen["list"].skinAttributes = [("font", "MenuFont")]
        with patch.dict(sys.modules, {"skin": parse}):
            self.screen.layout_finished()
        parse.parseFont.assert_called_once_with("MenuFont", self.screen.scale)
        self.assertEqual(fonts[-1], ("SkinFont", 37))
        self.screen.refresh()
        self.pending.pop().fire()
        self.assertEqual(fonts[-1], ("SkinFont", 37))
        self.screen.config["font_size"] = 32
        self.screen.render()
        self.assertEqual(fonts[-1], ("SkinFont", 32))
        self.assertEqual(heights[-1], 48)
        self.screen.config["font_family"] = "Regular"
        self.screen.render()
        self.assertEqual(fonts[-1], ("Regular", 32))
        self.screen.config["font_size"] = 0
        self.screen.render()
        self.assertEqual(fonts[-1], ("Regular", 37))
        self.assertEqual(self.menu["display"], {"font_family": "LegacyHAFont", "font_size": 64})

    def test_skin_profile_choice_cancel_save_and_next_open(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["save_settings"])
        dialogs = []
        session = types.SimpleNamespace(open=lambda *args, **kwargs: dialogs.append((args, kwargs)),
                                        openWithCallback=lambda *args, **kwargs: dialogs.append((args, kwargs)))
        enigma = types.SimpleNamespace(getFontFaces=lambda: ["Regular"], eLabel=object, eListbox=object)
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {"enigma": enigma}):
            path = str(Path(directory) / "config.json")
            original = dict(self.screen.config)
            settings.save_settings(self.screen.config, path)
            with patch.dict(PLUGIN.CompanionSetup.save.__globals__,
                            save_settings=lambda values: settings.save_settings(values, path)):
                setup = PLUGIN.CompanionSetup(session, settings.load_settings(path))
                field = setup.fields["skin_profile"]
                self.assertIsInstance(field, ConfigSelection)
                self.assertEqual([value for value, _ in field.choices], ["auto", "native", "gradient"])
                setup["config"].getCurrent = lambda: ("Skin-Profil", field)
                setup.edit()
                (callback, _), options = dialogs[-1]
                callback(None)
                self.assertEqual(field.value, "auto")
                callback(next(entry for entry in options["list"] if entry[1] == "gradient"))
                setup.cancel()
                self.assertEqual(settings.load_settings(path)["skin_profile"], "auto")
                setup.save()
                saved = settings.load_settings(path)
                self.assertEqual(saved["skin_profile"], "gradient")
                self.screen.settings_done(saved)
                self.pending.pop().fire()
                self.assertEqual(self.screen.appearance.selection, "auto")
                with patch.object(PLUGIN, "load_settings", side_effect=lambda: settings.load_settings(path)) as load:
                    reopened = PLUGIN.CompanionScreen(session)
                    self.addCleanup(reopened.cleanup)
                    self.assertEqual(reopened.appearance.profile, "gradient")
                    self.assertEqual(reopened.skinName, ["EnigmaHACompanionBuiltin"])
                    reopened.start()
                    load.assert_called_once_with()
                next_setup = PLUGIN.CompanionSetup(session, saved)
                self.assertEqual(next_setup.appearance.profile, "gradient")
                self.assertEqual(next_setup.skinName, ["EnigmaHASetupBuiltin"])
                # Selection does not change connection or local font preferences.
                for name in ("url", "token", "font_family", "font_size"):
                    self.assertEqual(saved[name], original[name])

    def test_skin_profile_validation_and_unreadable_configuration(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["validate_settings"])
        self.assertEqual(settings.validate_settings({})["skin_profile"], "auto")
        for invalid in (None, False, 1, [], {}, "unknown", "GradientFHD"):
            with self.subTest(profile=invalid), self.assertRaises(ValueError):
                settings.validate_settings(dict(self.screen.config, skin_profile=invalid))
        for error in (ValueError("invalid config"), OSError("unreadable config")):
            with patch.object(PLUGIN, "load_settings", side_effect=error):
                screen = PLUGIN.CompanionScreen(self.screen.session)
                self.addCleanup(screen.cleanup)
                self.assertEqual(screen.appearance.selection, "auto")
                screen.start()
                self.assertIn("Konfiguration nicht lesbar", screen["status"].text)
                self.assertIs(self.dialogs[-1][1], PLUGIN.CompanionSetup)

    def test_settings_input_help_uses_desktop_coordinates_above_footer(self):
        setup = PLUGIN.CompanionSetup(self.screen.session, self.screen.config)
        setup["config"].getCurrent = lambda: ("Adresse", setup.fields["url"])
        positions = []
        setup.fields["url"].help_window = types.SimpleNamespace(instance=types.SimpleNamespace(
            size=lambda: types.SimpleNamespace(width=lambda: 520, height=lambda: 120),
            move=positions.append))
        setup.instance = types.SimpleNamespace(
            position=lambda: types.SimpleNamespace(x=lambda: 52, y=lambda: 43),
            size=lambda: types.SimpleNamespace(width=lambda: 1176, height=lambda: 634))
        with patch.dict(sys.modules, {"enigma": types.SimpleNamespace(ePoint=lambda x, y: (x, y))}):
            setup.handleInputHelpers()
        self.assertEqual(positions, [(380, 475)])

    def test_first_run_settings_wait_for_modal_execution(self):
        active = False
        dialogs = []
        def open_dialog(*args):
            if not active:
                raise RuntimeError("Cannot open a modal dialog during layout")
            dialogs.append(args)
        with patch.object(PLUGIN, "load_settings", return_value=dict(PLUGIN.DEFAULTS)):
            screen = PLUGIN.CompanionScreen(types.SimpleNamespace(openWithCallback=open_dialog))
            self.addCleanup(screen.cleanup)
            for callback in screen.onLayoutFinish:
                callback()
            self.assertEqual(dialogs, [])
            active = True
            callbacks, screen.onFirstExecBegin = screen.onFirstExecBegin, []
            for callback in callbacks:
                callback()
            self.assertEqual(len(dialogs), 1)
            self.assertIs(dialogs[0][1], PLUGIN.CompanionSetup)
            screen.settings_done(None)
            for callback in screen.onFirstExecBegin:
                callback()
            self.assertEqual(len(dialogs), 1)

    def test_remote_navigation_and_read_only_sensor(self):
        self.press("open")
        self.assertEqual(self.screen.nav.current["id"], "living-room")
        self.press("down")
        self.press("ok")
        self.assertEqual(self.commands, [])
        self.press("down")
        self.press("open")
        self.assertEqual(self.screen.nav.current["id"], "windows")
        self.press("back")
        self.assertEqual(self.screen.nav.selection["id"], "windows")

    def test_right_never_switches_entity(self):
        self.press("open")
        self.press("pageDown")
        self.assertEqual(self.commands, [])
        self.assertEqual(self.pending, [])

    def test_entity_state_symbols_replace_text_and_change_with_state(self):
        self.press("open")
        state = self.screen.states["light.wohnzimmer"]
        state["icon"] = {"name": "mdi:lightbulb", "path": "M0,0H24V24H0Z"}
        rendered = []
        icon_globals = PLUGIN.StateIcons.get.__globals__
        def load(path, **kwargs):
            svg = Path(path).read_text()
            rendered.append(svg)
            return {"svg": svg, **kwargs}
        with patch.dict(icon_globals, LoadPixmap=load):
            self.screen.render()
            row = self.screen["list"].rows[0]
            self.assertEqual(row[2]["kind"], "pixmap")
            self.assertIn('#9e9e9e', row[2]["png"]["svg"])
            self.assertNotIn("text", row[2])
            self.assertEqual(self.screen["list"].rows[1][2]["text"], "22.4 °C")
            self.screen.render()
            self.assertEqual(len(rendered), 1, "Navigation redraws reuse native pixmaps")
            state["state"] = "on"
            self.screen.render()
            self.assertIn('#ffc107', self.screen["list"].rows[0][2]["png"]["svg"])
            self.assertEqual(len(rendered), 2)
            state["state"] = "unavailable"
            self.screen.render()
            self.assertEqual(self.screen["list"].rows[0][2]["text"], "Nicht verfügbar")
            state["state"] = "on"
            state["icon"]["path"] = '<svg><image href="http://elsewhere/"/></svg>'
            self.screen.render()
            self.assertEqual(self.screen["list"].rows[0][2]["text"], "Ein")
            self.assertEqual(len(rendered), 2)
        directory = Path(self.screen.state_icons.directory.name)
        self.assertEqual(list(directory.iterdir()), [], "No SVG files accumulate")
        self.screen.cleanup()
        self.assertFalse(directory.exists())

    def test_failed_symbol_decoding_keeps_readable_state(self):
        self.press("open")
        self.screen.states["light.wohnzimmer"]["icon"] = {"name": "mdi:lightbulb", "path": "M0,0H24V24H0Z"}
        def fail(*args, **kwargs):
            raise OSError("decoder failed")
        with patch.dict(PLUGIN.StateIcons.get.__globals__, LoadPixmap=fail):
            self.screen.render()
        self.assertEqual(self.screen["list"].rows[0][2]["text"], "Aus")

    def test_ok_is_nonblocking_and_blocks_duplicate_commands(self):
        self.press("open")
        self.press("ok")
        self.assertTrue(self.screen.busy)
        self.assertEqual(self.commands, [])
        self.press("ok")
        self.assertEqual(len(self.pending), 1)
        self.pending.pop().fire()
        self.assertEqual(len(self.commands), 1)
        self.assertFalse(self.screen.busy)

    def test_refresh_preserves_path_and_selection(self):
        self.press("open")
        self.press("down")
        self.press("refresh")
        self.pending.pop().fire()
        self.assertEqual(self.screen.nav.selection["id"], "temperature")
        self.assertEqual(self.screen.nav.current["id"], "living-room")

    def test_closed_screen_ignores_late_response(self):
        self.press("refresh")
        self.press("close")
        self.pending.pop().fire()
        self.assertTrue(self.screen.closed)
        self.assertFalse(self.screen.timer.running)

    def test_failure_marks_offline_and_disables_switching(self):
        self.press("open")
        def fail():
            raise PLUGIN.ClientError("connection_failed")
        self.screen.client.get_menu = fail
        self.press("refresh")
        self.pending.pop().fire()
        self.assertFalse(self.screen.online)
        self.assertIn("OFFLINE", self.screen["heading"].text)
        self.press("ok")
        self.assertEqual(self.commands, [])

    def test_peer_mismatch_has_localized_versions_blocks_actions_and_does_not_repeat_dialog(self):
        self.press("open")
        for language in ("de", "en"):
            self.screen.appearance.language = language
            self.screen.peer_notice = None
            error = PLUGIN.ClientError("version_mismatch", peer_version="99.0.0")
            failure = types.SimpleNamespace(value=error)
            self.screen.failed(failure, self.screen.generation)
            count = len(self.dialogs)
            self.assertIn(PLUGIN.VERSION, self.screen["status"].text)
            self.assertIn("99.0.0", self.screen["status"].text)
            self.assertIn("denselben Release" if language == "de" else "same release", self.dialogs[-1][1]["title"])
            self.assertIn("99.0.0", self.dialogs[-1][1]["list"][0][0])
            self.assertFalse(self.screen.online)
            self.press("ok")
            self.assertEqual(self.commands, [])
            self.screen.failed(failure, self.screen.generation)
            self.assertEqual(len(self.dialogs), count)
            self.screen.loaded((self.menu, self.states), self.screen.generation)
            self.assertTrue(self.screen.online)
            self.screen.failed(failure, self.screen.generation)
            self.assertEqual(len(self.dialogs), count + 1)
        error = PLUGIN.ClientError("unidentified_peer")
        self.screen.failed(types.SimpleNamespace(value=error), self.screen.generation)
        self.assertIn("Cannot identify", self.dialogs[-1][0][1])

    def test_settings_can_be_opened_and_cancelled(self):
        self.press("settings")
        self.assertFalse(self.screen.timer.running)
        self.assertEqual(len(self.dialogs), 1)
        self.screen.settings_done(None)
        self.assertEqual(len(self.pending), 1)

    def update_plan(self):
        return {"id": "b" * 32, "release": {"version": "2.0.0"}, "status": "pending", "attempt": 1}

    def test_conflict_update_is_checked_then_requires_local_install_confirmation(self):
        job = dict(self.update_plan(), local=True)
        self.screen.updater = types.SimpleNamespace(local_update=Mock(return_value=job), confirm=Mock(), perform=Mock())
        error = PLUGIN.ClientError("protocol_mismatch", peer_version="2.0.0", peer_protocol=2)
        self.screen.failed(types.SimpleNamespace(value=error), self.screen.generation)
        args, options = self.dialogs[-1]
        self.assertTrue(self.screen.busy)
        args[0](options["list"][0])
        self.assertEqual(len(self.pending), 1)
        self.screen.updater.perform.assert_not_called()
        self.pending.pop().fire()
        self.screen.updater.local_update.assert_called_once_with("2.0.0")
        args, options = self.dialogs[-1]
        self.assertFalse(options["default"])
        self.assertIn("Receiver auf Release 2.0.0", args[2])
        args[0](True)
        with patch.dict(sys.modules, {"Components.SystemInfo": types.SimpleNamespace(BoxInfo=types.SimpleNamespace(getItem=lambda key: "openatv"))}):
            self.pending.pop().fire()
        self.screen.updater.confirm.assert_called_once_with(job)
        self.screen.updater.perform.assert_called_once_with(job, None)
        self.assertIn("GUI jetzt neu starten", self.dialogs[-1][0][2])
        self.assertFalse(self.dialogs[-1][1]["default"])

    def test_conflict_update_cancellation_and_old_or_unknown_peers_never_install(self):
        self.screen.updater = types.SimpleNamespace(local_update=Mock(), confirm=Mock(), perform=Mock())
        error = PLUGIN.ClientError("legacy_version_mismatch", peer_version="9.0.0")
        self.screen.failed(types.SimpleNamespace(value=error), self.screen.generation)
        args, _ = self.dialogs[-1]
        args[0](None)
        self.assertFalse(self.screen.busy)
        self.assertTrue(self.screen.timer.running)
        self.assertEqual(self.pending, [])
        for version in ("0.0.1", PLUGIN.VERSION, None, "invalid"):
            error = PLUGIN.ClientError("protocol_mismatch", peer_version=version)
            self.screen.failed(types.SimpleNamespace(value=error), self.screen.generation)
            self.assertEqual(self.dialogs[-1][0][0], PLUGIN.MessageBox)
        self.screen.updater.local_update.assert_not_called()
        self.screen.updater.perform.assert_not_called()

    def test_conflict_action_reuses_ha_job_and_ignores_closed_screen(self):
        job = self.update_plan()
        self.screen.client.get_update = lambda: job
        self.screen.updater = types.SimpleNamespace(local_update=Mock())
        self.screen.mismatch_update_answer(("Update", "update"), "2.0.0", self.screen.generation)
        self.pending.pop().fire()
        self.screen.updater.local_update.assert_not_called()
        self.assertIn("für HA und Receiver", self.dialogs[-1][0][2])
        self.screen.cleanup()
        self.screen.mismatch_update_answer(("Update", "update"), "2.0.0", self.screen.generation)
        self.assertEqual(self.pending, [])

    def test_local_decline_does_not_report_a_nonexistent_ha_job(self):
        job = dict(self.update_plan(), local=True)
        self.screen.client.report_update = Mock()
        self.screen.updater = types.SimpleNamespace(confirm=Mock(), perform=Mock())
        self.screen.update_answer(job, False)
        self.screen.client.report_update.assert_not_called()
        self.screen.updater.confirm.assert_not_called()
        self.screen.updater.perform.assert_not_called()
        self.assertEqual(self.pending, [])

    def test_missing_conflict_release_is_explained_without_installing(self):
        self.screen.appearance.language = "en"
        self.screen.updater = types.SimpleNamespace(local_update=Mock(side_effect=PLUGIN.UpdateError("invalid_release")),
                                                   confirm=Mock(), perform=Mock())
        self.screen.mismatch_update_answer(("Update", "update"), "2.0.0", self.screen.generation)
        self.pending.pop().fire()
        self.assertIn("Matching release unavailable", self.dialogs[-1][0][1])
        self.screen.updater.confirm.assert_not_called()
        self.screen.updater.perform.assert_not_called()
        self.assertFalse(self.screen.busy)

    def test_local_restart_is_offered_even_when_ha_is_offline(self):
        for local in (True, False):
            with self.subTest(local=local):
                job = dict(self.update_plan(), status="restart_required")
                if local:
                    job["local"] = True
                with patch.object(PLUGIN, "ReceiverUpdater", return_value=types.SimpleNamespace(local_restart=lambda: job)):
                    self.screen.client.get_update = Mock(side_effect=PLUGIN.ClientError("connection_failed"))
                    self.assertEqual(self.screen.snapshot(self.screen.client), {"update": job})
                self.screen.client.get_update.assert_not_called()
                self.screen.update_notice = None
                self.screen.update_loaded(job)
                args, kwargs = self.dialogs[-1]
                self.assertIn("GUI jetzt neu starten", args[2])
                self.assertFalse(kwargs["default"])
                args[0](False)
                self.assertFalse(self.screen.busy)

    def test_receiver_declining_update_cannot_download_or_install(self):
        job = self.update_plan()
        self.screen.client.get_update = lambda: job
        self.screen.client.report_update = lambda job, status: job.update(status=status)
        self.screen.updater = types.SimpleNamespace(confirm=Mock(), perform=Mock())
        self.press("refresh")
        self.pending.pop().fire()
        args, kwargs = self.dialogs[-1]
        self.assertEqual(kwargs["default"], False)
        self.assertIn("2.0.0", args[2])
        self.screen.updater.perform.assert_not_called()
        args[0](False)
        self.pending.pop().fire()
        self.assertEqual(job["status"], "declined")
        self.screen.updater.confirm.assert_not_called()
        self.screen.updater.perform.assert_not_called()

    def test_receiver_confirms_install_and_gui_restart_separately_and_blocks_close(self):
        job = self.update_plan()
        self.screen.client.get_update = lambda: job
        def perform(job, client):
            job["status"] = "restart_required"
        self.screen.updater = types.SimpleNamespace(confirm=Mock(), perform=Mock(side_effect=perform))
        self.press("refresh")
        self.pending.pop().fire()
        args, kwargs = self.dialogs[-1]
        args[0](True)
        self.assertTrue(self.screen.update_installing)
        self.press("close")
        self.assertFalse(self.screen.closed)
        with patch.dict(sys.modules, {"Components.SystemInfo": types.SimpleNamespace(BoxInfo=types.SimpleNamespace(getItem=lambda key: "openatv"))}):
            self.pending.pop().fire()
        self.screen.updater.confirm.assert_called_once_with(job)
        self.screen.updater.perform.assert_called_once_with(job, self.screen.client)
        self.assertFalse(self.screen.update_installing)
        args, kwargs = self.dialogs[-1]
        self.assertIn("GUI jetzt neu starten", args[2])
        self.assertEqual(kwargs["default"], False)
        args[0](False)
        self.assertFalse(self.screen.busy)
        with patch.dict(sys.modules, {"Screens.Standby": types.SimpleNamespace(TryQuitMainloop=object)}):
            self.screen.restart_answer(True)
        self.assertEqual(self.dialogs[-1][0], (object, 3))

    def test_update_errors_are_localized_and_startup_only_reports_running_release(self):
        self.screen.appearance.language = "en"
        failure = types.SimpleNamespace(value=PLUGIN.UpdateError("checksum_failed"))
        self.screen.failed(failure, self.screen.generation)
        self.assertIn("checksum does not match", self.dialogs[-1][0][1])
        self.assertFalse(self.screen.online)
        fake = types.SimpleNamespace(get_update=Mock(return_value=None))
        journal = types.SimpleNamespace(acknowledge_running=Mock())
        with patch.object(PLUGIN, "load_settings", return_value=self.screen.config), \
             patch.object(PLUGIN, "CompanionClient", return_value=fake), \
             patch.object(PLUGIN, "ReceiverUpdater", return_value=journal):
            PLUGIN.report_after_restart(0)
            PLUGIN._UPDATE_REPORT_TIMER.callback[0]()
            self.pending.pop().fire()
        fake.get_update.assert_called_once()
        journal.acknowledge_running.assert_called_once_with(None)
        PLUGIN.report_after_restart(1)

    def test_private_config_roundtrip_and_validation(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["save_settings"])
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "config.json")
            settings.save_settings(self.screen.config, path)
            self.assertEqual(settings.load_settings(path), self.screen.config)
            self.assertEqual(settings.validate_settings(dict(self.screen.config, font_family="  "))["font_family"], "")
            with self.assertRaises(ValueError):
                settings.save_settings(dict(self.screen.config, font_size=4), path)
            self.assertEqual(settings.load_settings(path), self.screen.config)


    def test_mainmenu_registration_and_launch(self):
        with patch.object(PLUGIN, "_KEYMAP_LOADED", True):
            descriptors = PLUGIN.Plugins()
        self.assertEqual(descriptors[0].where, [PLUGIN.PluginDescriptor.WHERE_PLUGINMENU,
                                              PLUGIN.PluginDescriptor.WHERE_EXTENSIONSMENU])
        callback = next(item.fnc for item in descriptors if item.where == PLUGIN.PluginDescriptor.WHERE_MENU)
        with patch.object(PLUGIN, "load_settings", return_value=dict(PLUGIN.DEFAULTS)) as load:
            self.assertEqual(callback("setup"), [])
            load.assert_not_called()
            self.assertEqual(callback("mainmenu"), [])
            load.return_value = dict(PLUGIN.DEFAULTS, show_in_mainmenu=True)
            entry, = callback("mainmenu")
            self.assertEqual(entry[0], "EnigmaHA Companion")
            entry[1](self.screen.session, close=lambda: None)
            self.assertIs(self.dialogs[-1][0][0], PLUGIN.CompanionScreen)
            load.return_value = dict(PLUGIN.DEFAULTS, show_in_mainmenu=False)
            self.assertEqual(callback("mainmenu"), [])
        for error in (ValueError("invalid config"), OSError("unreadable config")):
            with patch.object(PLUGIN, "load_settings", side_effect=error):
                self.assertEqual(callback("mainmenu"), [])

    def test_direct_settings_hotkey_opens_saved_configuration_with_separate_path(self):
        with patch.object(PLUGIN, "_KEYMAP_LOADED", True):
            descriptors = PLUGIN.Plugins()
        settings, = [item for item in descriptors if item.where == PLUGIN.PluginDescriptor.WHERE_BUTTONSETUP]
        self.assertEqual(settings.name, "EnigmaHA Companion (Einstellungen)")
        settings.updateIcon("/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion")
        self.assertTrue(settings.path.replace("\\", "/").endswith("/EnigmaHACompanion/settings"))
        with patch.object(PLUGIN, "load_settings", return_value=self.screen.config):
            settings.fnc(self.screen.session)
        self.assertEqual(self.dialogs[-1][0], (PLUGIN.CompanionSetup, self.screen.config))
        with patch.object(PLUGIN, "load_settings", side_effect=ValueError("invalid config")):
            settings.fnc(self.screen.session)
        self.assertEqual(self.dialogs[-1][0], (PLUGIN.CompanionSetup, PLUGIN.DEFAULTS))

    def test_mainmenu_option_save_and_cancel(self):
        settings = __import__("eha_receiver_test.settings", fromlist=["save_settings"])
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "config.json")
            settings.save_settings(self.screen.config, path)
            with patch.dict(PLUGIN.CompanionSetup.save.__globals__,
                            save_settings=lambda values: settings.save_settings(values, path)):
                setup = PLUGIN.CompanionSetup(self.screen.session, settings.load_settings(path))
                self.assertIsInstance(setup.fields["show_in_mainmenu"], ConfigYesNo)
                setup.fields["show_in_mainmenu"].value = True
                setup.cancel()
                self.assertFalse(settings.load_settings(path)["show_in_mainmenu"])
                setup = PLUGIN.CompanionSetup(self.screen.session, settings.load_settings(path))
                setup.fields["show_in_mainmenu"].value = True
                setup.save()
                self.assertTrue(settings.load_settings(path)["show_in_mainmenu"])
                self.assertTrue(setup.close_result["show_in_mainmenu"])
            for invalid in ("false", 0, 1, None):
                with self.assertRaises(ValueError):
                    settings.validate_settings(dict(self.screen.config, show_in_mainmenu=invalid))


    def test_token_or_server_change_clears_previous_user_data_before_connecting(self):
        old_generation = self.screen.generation
        old_client = self.screen.client
        with patch.object(self.screen, "connect") as connect:
            self.screen.settings_done(dict(self.screen.config, token="different-user-token"))
        connect.assert_called_once()
        self.assertIsNone(self.screen.nav)
        self.assertEqual(self.screen.states, {})
        self.assertEqual(self.screen["list"].rows, [])
        self.screen.loaded((self.menu, self.states), old_generation)
        self.assertIsNone(self.screen.nav)
        self.screen.client = old_client
        self.screen.loaded((self.menu, self.states), self.screen.generation)
        self.assertIsNotNone(self.screen.nav)
        with patch.object(self.screen, "connect"):
            self.screen.settings_done(dict(self.screen.config, url="http://another-ha.test:8123"))
        self.assertIsNone(self.screen.nav)
        self.assertEqual(self.screen.states, {})

    def test_revoked_token_clears_menu_and_states(self):
        self.screen.failed(types.SimpleNamespace(value=PLUGIN.ClientError("unauthorized")), self.screen.generation)
        self.assertIsNone(self.screen.nav)
        self.assertEqual(self.screen.states, {})
        self.assertEqual(self.screen["list"].rows, [])

    def test_menu_access_removed_refresh_resets_path_and_explains_empty_menu(self):
        self.screen.nav.activate(self.screen.states)
        menu = dict(self.menu, revision=2, root={"type": "menu", "id": "__enigmaha_no_menu",
                                               "label": "Home Assistant", "children": []})
        self.screen.loaded((menu, {}), self.screen.generation)
        self.assertEqual(self.screen.nav.stack, [("__enigmaha_no_menu", 0)])
        self.assertEqual(self.screen.states, {})
        self.assertIn("kein Menü freigegeben", self.screen["status"].text)
        self.assertEqual(self.screen["list"].rows, [])


if __name__ == "__main__":
    unittest.main()
