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
    fake["Plugins.Plugin"].PluginDescriptor = type("PluginDescriptor", (), {
        "WHERE_PLUGINMENU": 1, "WHERE_EXTENSIONSMENU": 2, "WHERE_MENU": 3, "WHERE_SESSIONSTART": 4,
        "__init__": lambda self, **kwargs: self.__dict__.update(kwargs)})
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
    return module


PLUGIN = load_receiver()


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.states = json.loads((ROOT / "protocol/states.example.json").read_text(encoding="utf-8"))["states"]
        self.pending, self.commands, self.dialogs = [], [], []
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
            self.assertEqual(setup.selection_choices["language"], [("de", "Deutsch"), ("en", "English")])
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
            self.assertEqual(reopened.selection_choices["font_family"][0], ("", "Use HA setting"))
            self.assertEqual(reopened.fields["show_in_mainmenu"].descriptions, {False: "No", True: "Yes"})
            self.assertIn("Green: Save", reopened["hint"].text)
            def fail_save(data):
                raise OSError()
            with patch.dict(reopened.save.__globals__, {"save_settings": fail_save}):
                reopened.save()
            self.assertIn("Could not save settings", self.dialogs[-1][0][1])

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
        self.assertEqual(screen["heading"].text, "OFFLINE – " + screen.nav.breadcrumb)

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

    def test_receiver_font_choices_use_registered_fonts_and_keep_saved_preferences(self):
        with patch.dict(PLUGIN.CompanionSetup.__init__.__globals__,
                        getFontFaces=lambda: ["Regular", "SkinFont", "Italic", "SkinFont"]):
            setup = PLUGIN.CompanionSetup(self.screen.session, dict(self.screen.config, font_family="OldFont", font_size=31))
        self.assertIsInstance(setup.fields["font_family"], ConfigSelection)
        self.assertIsInstance(setup.fields["font_size"], ConfigSelection)
        self.assertNotIsInstance(setup.fields["font_family"], ConfigText)
        self.assertEqual(setup.selection_choices["font_family"], [
            ("", "Aus HA übernehmen"), ("Italic", "Italic"), ("Regular", "Regular"),
            ("SkinFont", "SkinFont"), ("OldFont", "OldFont (Ersatz: Regular)")])
        self.assertEqual(setup.fields["font_family"].value, "OldFont")
        self.assertEqual(setup.fields["font_size"].value, "31")
        self.assertEqual([value for value, _ in setup.selection_choices["font_size"]],
                         ["0"] + [str(size) for size in range(16, 65)])

    def test_receiver_font_choice_dialog_cancel_select_save_and_ha_inheritance(self):
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
        self.press("open")
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
            self.assertIn("denselben Release" if language == "de" else "same release", self.dialogs[-1][0][1])
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


if __name__ == "__main__":
    unittest.main()
