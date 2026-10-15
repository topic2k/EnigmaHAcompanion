"""Native hotkey rendering preserves full selection data and readable suffixes."""

import copy
import sys
import types
import unittest
from unittest.mock import patch

from test_receiver_plugin import PLUGIN

DISPLAY = sys.modules[PLUGIN.__package__ + ".hotkey_display"]
TEXT = 0


def row(label, action="Plugins/Extensions/EnigmaHACompanion/hotkeys/abc/1"):
    return [(label, action), (TEXT, 45, 0, 1235, 25, 0, 16, label), (2, 5, 0, 35, 25, "icon")]


class ChoiceList:
    def __init__(self, rows, width=420):
        self.position = 0
        self.width = width
        self.instance = types.SimpleNamespace(
            size=lambda: types.SimpleNamespace(width=lambda: self.width), getScrollbarListOffset=lambda: 12)
        self.l = types.SimpleNamespace(setList=self.render)
        self.setList(rows)

    def render(self, rows):
        self.rendered = rows

    def setList(self, rows):
        self.list = rows
        self.l.setList(rows)

    def getCurrentIndex(self):
        return self.position

    def getCurrent(self):
        return self.rendered[self.position]


class HotkeyDisplayTests(unittest.TestCase):
    def test_long_nested_label_shows_command_suffix_in_the_available_pixels(self):
        label = "EnigmaHA: Home Assistant > Dachboden > Untermenü > Licht Dachboden – Umschalten"
        rows = [row(label)]
        original = copy.deepcopy(rows)
        rendered = DISPLAY.display_rows(rows, 360, lambda value: len(value) * 9, TEXT)
        self.assertEqual(rows, original)
        self.assertEqual(rendered[0][0], rows[0][0])
        self.assertEqual(rendered[0][2], rows[0][2])
        self.assertTrue(rendered[0][1][7].startswith("…"))
        self.assertTrue(rendered[0][1][7].endswith("Licht Dachboden – Umschalten"))
        self.assertLessEqual(len(rendered[0][1][7]) * 9, 315)

    def test_short_labels_categories_and_other_plugins_keep_their_display(self):
        short = row("EnigmaHA: Flur – Umschalten")
        other = row("Another plugin with a very long name " * 5, "Plugins/Extensions/Other/1")
        category = row("Plugins", "Expander")
        rendered = DISPLAY.display_rows([short, other, category], 400, lambda value: len(value) * 8, TEXT)
        self.assertEqual(rendered[0][1][7], short[1][7])
        self.assertIs(rendered[1], other)
        self.assertIs(rendered[2], category)

    def test_selection_assignment_removal_reordering_and_cancel_keep_full_native_rows(self):
        available = ChoiceList([row("EnigmaHA: " + "Untermenü > " * 8 + "Licht – Umschalten"), row("Other")])
        DISPLAY.fit_component(available, lambda value: len(value) * 8, TEXT)
        current = available.getCurrent()
        self.assertIs(current, available.list[0])
        self.assertNotEqual(current[1][7], available.rendered[0][1][7])
        selected = [current[:2]]  # Native ButtonSetupSelect.keyOk.
        previous = copy.deepcopy(selected)
        chosen = ChoiceList(selected, width=260)
        DISPLAY.fit_component(chosen, lambda value: len(value) * 8, TEXT)
        self.assertIn(available.getCurrent()[:2], selected)
        self.assertEqual(selected, previous)  # No false unsaved-change prompt.
        self.assertEqual([item[0][1] for item in selected], [current[0][1]])
        chosen.setList(list(reversed(selected)))
        selected.remove(chosen.getCurrent())
        self.assertFalse(selected)
        available.width = 2000
        available.setList(available.list)
        self.assertEqual(available.rendered[0][1][7], current[1][7])

    def test_unicode_suffix_and_extremely_narrow_lists(self):
        self.assertEqual(DISPLAY.elide_left("Licht Küche – Umschalten", 13, len), "…– Umschalten")
        self.assertEqual(DISPLAY.elide_left("Label", 0, len), "")
        self.assertEqual(DISPLAY.elide_left("Label", 1, len), "…")
        self.assertEqual(DISPLAY.elide_left("Label", 5, len), "Label")

    def test_layout_uses_first_three_skin_metrics_with_realistic_extended_font_definition(self):
        enigma = types.SimpleNamespace(
            eLabel=types.SimpleNamespace(calculateTextSize=lambda font, text, target, nowrap:
                types.SimpleNamespace(width=lambda: len(text) * font[1] // 2)),
            gFont=lambda family, size: (family, size), eSize=lambda width, height: (width, height),
            eListboxPythonMultiContent=types.SimpleNamespace(TYPE_TEXT=TEXT))
        for font in (("Regular", 20, 25), ("Regular", 28, 42, 0), ("Regular", 32, 48, 0, 1)):
            with self.subTest(font=font):
                screen = {"list": ChoiceList([row("EnigmaHA: " + "Menü > " * 15 + "Lampe – Umschalten")]),
                          "choosen": ChoiceList([])}
                with patch.dict(sys.modules, {"enigma": enigma, "skin": types.SimpleNamespace(fonts={"ChoiceList": font})}):
                    DISPLAY.fit_lists(screen)
                self.assertTrue(screen["list"].rendered[0][1][7].startswith("…"))
                self.assertTrue(screen["list"].rendered[0][1][7].endswith("Lampe – Umschalten"))
