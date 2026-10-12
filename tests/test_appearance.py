"""Layout and capability checks independent of receiver hardware."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


PATH = Path(__file__).resolve().parents[1] / "dist/unpacked/enigma2/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion/appearance.py"
PACKAGE = types.ModuleType("receiver_appearance")
PACKAGE.__path__ = [str(PATH.parent)]
sys.modules[PACKAGE.__name__] = PACKAGE
SPEC = importlib.util.spec_from_file_location("receiver_appearance.appearance", PATH)
APPEARANCE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPEARANCE)
PROFILES = sys.modules["receiver_appearance.skin"]
GRADIENT = sys.modules["receiver_appearance.skin.GradientFHD"]


class AppearanceTests(unittest.TestCase):
    def environment(self, path="GradientFHD/skin.xml", modern=True):
        config = types.ModuleType("Components.config")
        config.config = types.SimpleNamespace(skin=types.SimpleNamespace(
            primary_skin=types.SimpleNamespace(value=path)))
        enigma = types.ModuleType("enigma")
        enigma.getFontFaces = lambda: ["Regular", "Gradient_Font", "Italic"]
        enigma.eLabel = types.SimpleNamespace(**({"setBackgroundGradient": None} if modern else {}))
        enigma.eListbox = types.SimpleNamespace(**({
            "setItemGradientSelected": None, "setItemCornerRadiusSelected": None} if modern else {}))
        skin = types.ModuleType("skin")
        skin.colors = {"gradient_BGLM": object()}
        return patch.dict(sys.modules, {"Components.config": config, "enigma": enigma, "skin": skin})

    def layout(self, width=1920, height=1080, selection="auto"):
        return APPEARANCE.Appearance(types.SimpleNamespace(width=lambda: width, height=lambda: height), selection)

    def test_profile_detection(self):
        for path, expected in [("GradientFHD/skin.xml", "gradient"),
                               ("/usr/share/enigma2/GradientFHD/skin.xml", "gradient"),
                               ("gradientfhd\\skin.xml", "gradient"),
                               ("Other/skin.xml", "native"),
                               ("Other/GradientFHD", "native"),
                               ("MyGradientFHD/skin.xml", "native")]:
            with self.environment(path):
                self.assertEqual(APPEARANCE.active_profile(), expected)

    def test_english_titles_and_gradient_footer_with_and_without_key_images(self):
        for selection in ("native", "gradient"):
            for assets_present in (False, True):
                with self.subTest(profile=selection, assets=assets_present), self.environment(), patch.object(
                        GRADIENT.os.path, "isfile", return_value=assets_present):
                    appearance = APPEARANCE.Appearance(
                        types.SimpleNamespace(width=lambda: 1920, height=lambda: 1080), selection, language="en")
                    setup = ET.fromstring(appearance.layout(setup=True))
                    self.assertEqual(setup.get("title"), "EnigmaHA Companion – Settings")
                    self.assertIn("EnigmaHA – Settings", appearance.text_labels.values())
                    self.assertEqual(setup.findall("eLabel[@text]"), [])
                    for name in appearance.text_labels:
                        self.assertIsNotNone(setup.find("widget[@name='%s']" % name))
                    if selection == "gradient":
                        setup_text = list(appearance.text_labels.values())
                        self.assertIn("Save", setup_text)
                        self.assertIn("Cancel", setup_text)
                        self.assertIn("Change value", setup_text)
                        menu = ET.fromstring(appearance.layout())
                        self.assertEqual(menu.findall("eLabel[@text]"), [])
                        menu_text = list(appearance.text_labels.values())
                        self.assertIn("Settings", menu_text)
                        self.assertIn("Open/Toggle", menu_text)
                        if not assets_present:
                            self.assertIn("Green", menu_text)
                            self.assertIn("Menu", menu_text)
        self.assertEqual(PROFILES.profile_choices("en")[:2],
                         [("auto", "Automatic"), ("native", "Standard (active skin)")])

    def test_manual_profile_overrides_detection_and_external_screen_names(self):
        with self.environment():
            appearance = self.layout(selection="native")
            self.assertEqual(appearance.profile, "native")
            self.assertEqual(appearance.menu_font("Italic", 32), ("Italic", 48, 72))
            self.assertNotIn("flags", ET.fromstring(appearance.layout()).attrib)
            self.assertEqual(appearance.screen_names(), ["EnigmaHACompanionBuiltin"])
            self.assertEqual(appearance.screen_names(setup=True), ["EnigmaHASetupBuiltin"])
            self.assertEqual(self.layout().screen_names(), ["EnigmaHACompanion", "CompanionScreen"])
        with self.environment("Other/skin.xml"):
            appearance = self.layout(selection="gradient")
            self.assertEqual(appearance.profile, "gradient")
            self.assertEqual(ET.fromstring(appearance.layout()).get("flags"), "wfNoBorder")

    def test_manual_gradient_without_assets_palette_or_fonts(self):
        with self.environment("Other/skin.xml"), patch.object(GRADIENT.os.path, "isfile", return_value=False):
            sys.modules["enigma"].getFontFaces = lambda: ["Regular"]
            sys.modules["skin"].colors = {}
            appearance = self.layout(selection="gradient")
            self.assertEqual(appearance.font, "Regular")
            for setup in (False, True):
                root = ET.fromstring(appearance.layout(setup))
                self.assertEqual(root.findall("ePixmap"), [])
                widget = root.find("widget[@name='%s']" % ("config" if setup else "list"))
                self.assertEqual(widget.get("backgroundColorSelected"), "#001b5a91")

    def test_registered_profile_is_available_for_selection_detection_and_layout(self):
        class ExampleProfile(PROFILES.NativeProfile):
            id, label = "example", "Example Skin"
            skin_directories = ("ExampleHD",)
            width = 900

        with patch.object(PROFILES, "PROFILES", PROFILES.PROFILES + (ExampleProfile(),)):
            self.assertIn(("example", "Example Skin"), PROFILES.profile_choices())
            with self.environment("ExampleHD/skin.xml"):
                for selection in ("auto", "example"):
                    appearance = self.layout(selection=selection)
                    self.assertEqual(appearance.profile, "example")
                    self.assertEqual(appearance.width, 1350)
                    ET.fromstring(appearance.layout(setup=True))

    def test_unavailable_active_skin_uses_standard(self):
        with patch.dict(sys.modules, {"Components.config": types.ModuleType("Components.config")}):
            self.assertEqual(self.layout().profile, "native")

    def test_layouts_fit_desktop_and_widgets_fit_window(self):
        for path in ("GradientFHD/skin.xml", "Other/skin.xml"):
            with self.environment(path):
                for width, height in ((720, 576), (1280, 720), (1920, 1080), (3840, 2160)):
                    appearance = self.layout(width, height)
                    for setup in (False, True):
                        root = ET.fromstring(appearance.layout(setup))
                        self.assertLess(appearance.width, width)
                        self.assertLess(appearance.height, height)
                        for widget in root:
                            x, y = map(int, widget.get("position").split(","))
                            w, h = map(int, widget.get("size").split(","))
                            self.assertGreater(w, 0)
                            self.assertGreater(h, 0)
                            self.assertLessEqual(x + w, appearance.width)
                            self.assertLessEqual(y + h, appearance.height)

    def test_gradient_uses_skin_palette_and_capabilities(self):
        with self.environment():
            appearance = self.layout()
            self.assertEqual(appearance.font, "Gradient_Font")
            root = ET.fromstring(appearance.layout())
            widget = root.find("widget[@name='list']")
            self.assertEqual(widget.get("backgroundColorSelected"), "gradient_BGLM")
            self.assertIn("horizontal", widget.get("itemGradientSelected"))
            self.assertEqual(root.get("flags"), "wfNoBorder")

    def test_missing_gradient_apis_use_plain_colors(self):
        with self.environment(modern=False):
            root = ET.fromstring(self.layout().layout())
            for widget in root:
                self.assertNotIn("itemGradientSelected", widget.attrib)
                self.assertNotIn("itemCornerRadiusSelected", widget.attrib)
                self.assertNotIn(",", widget.get("backgroundColor", ""))

    def test_other_skins_keep_native_window_and_list_colors(self):
        with self.environment("Other/skin.xml"):
            root = ET.fromstring(self.layout().layout())
            self.assertNotIn("flags", root.attrib)
            self.assertNotIn("backgroundColorSelected", root.find("widget[@name='list']").attrib)

    def test_unavailable_font_falls_back(self):
        with self.environment():
            sys.modules["enigma"].getFontFaces = lambda: ["Regular"]
            self.assertEqual(self.layout().font, "Regular")

    def test_auto_uses_profile_defaults_and_local_choices_override_each_setting(self):
        with self.environment():
            appearance = self.layout()
            self.assertEqual(appearance.menu_font("", 0), ("Gradient_Font", 42, 60))
            self.assertEqual(appearance.menu_font("Italic", 0), ("Italic", 42, 60))
            self.assertEqual(appearance.menu_font("", 64), ("Gradient_Font", 96, 144))
            self.assertEqual(appearance.menu_font("Italic", 32), ("Italic", 48, 72))
            self.assertEqual(appearance.menu_font("Missing", 32), ("Regular", 48, 72))
        with self.environment("Other/skin.xml"):
            self.assertEqual(self.layout().menu_font("", 0), ("Regular", 42, 63))
            self.assertEqual(self.layout().menu_font("Italic", 32), ("Italic", 48, 72))

    def test_external_skin_font_is_default_and_explicit_choices_take_precedence(self):
        with self.environment():
            appearance = self.layout()
            parse = types.SimpleNamespace(parseFont=lambda value, scale:
                types.SimpleNamespace(family="Italic", pointSize=37))
            with patch.dict(sys.modules, {"skin": parse}):
                appearance.apply_list_skin([("font", "MenuFont")], ((1, 1), (1, 1)))
            self.assertEqual(appearance.menu_font("", 0), ("Italic", 37, 55))
            self.assertEqual(appearance.menu_font("Regular", 0), ("Regular", 37, 55))
            self.assertEqual(appearance.menu_font("", 32), ("Italic", 48, 72))
            self.assertEqual(appearance.menu_font("Regular", 32), ("Regular", 48, 72))
            appearance.apply_list_skin([], ((1, 1), (1, 1)))
            self.assertEqual(appearance.menu_font("", 0), ("Gradient_Font", 42, 60))

    def test_gradient_buttons_use_installed_assets_for_their_actions(self):
        with self.environment(), patch.object(GRADIENT.os.path, "isfile", return_value=True):
            for setup in (False, True):
                root = ET.fromstring(self.layout().layout(setup))
                assets = {Path(p.get("pixmap")).stem for p in root.findall("ePixmap")}
                self.assertTrue({"key_red", "key_green", "key_yellow", "ok", "exit"} <= assets)
                self.assertIn("key_leftright" if setup else "menu", assets)
                self.assertEqual("key_blue" in assets, not setup)

    def test_missing_button_assets_keep_readable_action_labels(self):
        with self.environment(), patch.object(GRADIENT.os.path, "isfile", return_value=False):
            appearance = self.layout()
            root = ET.fromstring(appearance.layout())
            self.assertEqual(root.findall("ePixmap"), [])
            texts = set(appearance.text_labels.values())
            self.assertTrue({"Rot", "Schließen", "OK", "Öffnen/Schalten", "Exit", "Zurück"} <= texts)


if __name__ == "__main__":
    unittest.main()
