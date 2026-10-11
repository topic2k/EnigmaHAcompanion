"""Enigma2 GUI: main-loop drawing, worker-thread HTTP, remote navigation."""

import os

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from enigma import eListboxPythonMultiContent, eTimer, getDesktop, gFont, RT_VALIGN_CENTER
from twisted.internet.threads import deferToThread

from .companion.client import ClientError, CompanionClient
from .companion.navigation import Navigator
from .appearance import Appearance
from .settings import DEFAULTS, load_settings
from .setup import CompanionSetup
from .state_icons import StateIcons

_KEYMAP_LOADED = False
HELP = ("Auf/Ab: Eintrag wählen\nRechts: Untermenü öffnen\nLinks/Exit: zurück; im Hauptmenü schließen\n"
        "OK/Grün: Untermenü öffnen oder Licht/Schalter umschalten\nMenü/Blau: Einstellungen\n"
        "Gelb: Aktualisieren\n{channel_help}\nRot: sofort schließen\n"
        "Sensoren sind nur lesbar. Die Menüstruktur wird in Home Assistant festgelegt.")


def safe_text(value):
    return " ".join(str(value).split())


class CompanionScreen(Screen):
    def __init__(self, session):
        self.config_error = False
        try:
            self.config = load_settings()
        except (ValueError, OSError):
            self.config = dict(DEFAULTS)
            self.config_error = True
        self.appearance = Appearance(getDesktop(0).size(), self.config["skin_profile"])
        self.ui_scale = self.appearance.scale
        self.list_width = self.appearance.list_width
        self.list_height = self.appearance.list_height
        self.skin = self.appearance.layout()
        Screen.__init__(self, session)
        self.skinName = self.appearance.screen_names()
        self.onLayoutFinish.append(self.layout_finished)
        self["heading"] = Label("Home Assistant")
        self["list"] = MenuList([], enableWrapAround=True, content=eListboxPythonMultiContent)
        self["status"] = Label("Verbindung wird vorbereitet …")
        self["footer"] = Label("OK/Grün: Öffnen/Schalten   Gelb: Laden\nMenü/Blau: Einstellungen   Rot: Schließen   Exit: Zurück")
        self["actions"] = ActionMap(["EnigmaHACompanionActions"], {
            "up": lambda: self.move(-1), "down": lambda: self.move(1),
            "channelPlus": lambda: self.move_channel_page(-1),
            "channelMinus": lambda: self.move_channel_page(1),
            "back": self.back, "open": self.open_menu, "ok": self.activate,
            "settings": self.settings, "refresh": self.refresh, "close": self.close,
            "help": self.help,
        }, -2)
        self.nav = None
        self.states = {}
        self.state_icons = StateIcons()
        self.busy = False
        self.online = False
        self.closed = False
        self.generation = 0
        self.row_height = max(28, int(40*self.ui_scale))
        self.timer = eTimer()
        try:
            self.timer.callback.append(self.refresh)
        except AttributeError:
            self.timer_connection = self.timer.timeout.connect(self.refresh)
        self.onClose.append(self.cleanup)
        # Layout runs before Session makes this screen the active modal dialog.
        # Opening first-run settings is only safe once execution has begun.
        self.onFirstExecBegin.append(self.start)

    def layout_finished(self):
        # A skin-provided screen may choose a different list geometry.
        instance = getattr(self["list"], "instance", None)
        if instance is not None:
            size = instance.size()
            self.list_width, self.list_height = size.width(), size.height()
        self.render()

    def start(self):
        if self.config_error:
            self["status"].setText("Konfiguration nicht lesbar. Bitte Einstellungen prüfen.")
        if not self.config["url"] or not self.config["token"]:
            self.settings()
        else:
            self.connect()

    def connect(self):
        try:
            self.client = CompanionClient(self.config["url"], self.config["token"], self.config["timeout"])
        except ValueError:
            self["status"].setText("Adresse oder Token ungültig. Menü: Einstellungen")
            return
        self.refresh()

    def page_size(self):
        return max(1, self.list_height // self.row_height)

    def move(self, amount):
        if self.nav:
            self.nav.move(amount)
            self.render()

    def move_channel_page(self, direction):
        if self.config["reverse_channel_paging"]:
            direction = -direction
        self.move_page(direction)

    def move_page(self, direction):
        if self.nav and self.nav.current["children"]:
            position = self.nav.stack[-1][1]
            target = max(0, min(len(self.nav.current["children"]) - 1,
                                position + direction * self.page_size()))
            self.move(target - position)

    def back(self):
        if self.nav and self.nav.back():
            self.render()
        else:
            self.close()

    def open_menu(self):
        if self.nav and self.nav.selection and self.nav.selection["type"] == "menu":
            self.nav.activate(self.states)
            self.render()

    def activate(self):
        if not self.nav or not self.nav.selection:
            return
        if self.nav.selection["type"] == "menu":
            self.open_menu()
            return
        if self.busy or not self.online:
            self["status"].setText("Bitte aktuelle Zustände abwarten. Gelb: erneut laden.")
            return
        command = self.nav.activate(self.states)
        if command is None:
            self["status"].setText("Dieser Eintrag ist nur lesbar oder nicht verfügbar.")
            return
        client = self.client
        def work():
            client.execute(command)
            return self.snapshot(client)
        self.run(work, "Schaltbefehl wird gesendet …")

    @staticmethod
    def snapshot(client):
        menu = client.get_menu()
        return menu, client.get_states(menu)

    def refresh(self):
        if self.closed or self.busy or not hasattr(self, "client"):
            return
        client = self.client
        self.run(lambda: self.snapshot(client), "Zustände werden geladen …")

    def run(self, work, message):
        self.timer.stop()
        self.busy = True
        self["status"].setText(message)
        generation = self.generation
        deferred = deferToThread(work)
        deferred.addCallbacks(lambda result: self.loaded(result, generation),
                              lambda failure: self.failed(failure, generation))

    def loaded(self, result, generation):
        if self.closed or generation != self.generation:
            return
        menu, states = result
        overrides = {}
        if self.config["font_family"]:
            overrides["font_family"] = self.config["font_family"]
        if self.config["font_size"]:
            overrides["font_size"] = self.config["font_size"]
        new_nav = Navigator(menu, overrides)
        # Preserve menu path and selected entry by ID across edits and refreshes.
        if self.nav:
            old = self.nav
            for depth, (old_id, old_position) in enumerate(old.stack):
                if depth >= len(new_nav.stack) or new_nav.current["id"] != old_id:
                    break
                old_children = old.nodes[old_id]["children"]
                selected_id = old_children[old_position]["id"] if old_children else None
                for index, child in enumerate(new_nav.current["children"]):
                    if child["id"] == selected_id:
                        new_nav.stack[-1] = (old_id, index)
                        if depth + 1 < len(old.stack) and child["type"] == "menu" and child["id"] == old.stack[depth+1][0]:
                            new_nav.stack.append((child["id"], 0))
                        break
        self.nav, self.states = new_nav, states
        self.online, self.busy = True, False
        self.render()
        self["status"].setText("Verbunden" if self.nav.current["children"] else "Menü ist leer. Einträge in Home Assistant hinzufügen.")
        self.timer.start(self.config["refresh_seconds"] * 1000, True)

    def failed(self, failure, generation):
        if self.closed or generation != self.generation:
            return None
        self.busy, self.online = False, False
        error = failure.value
        code = error.code if isinstance(error, ClientError) else "unknown"
        messages = {"unauthorized": "Token abgelehnt. Menü: Einstellungen",
                    "forbidden": "Keine Berechtigung für diese Aktion.",
                    "not_found": "HA-Integration nicht erreichbar. Installation prüfen.",
                    "conflict": "Menü/Zustand geändert. Gelb: neu laden.",
                    "stale_menu": "Menü geändert. Wird erneut geladen.",
                    "connection_failed": "Verbindung fehlgeschlagen. Schaltzustand unklar; keine Wiederholung.",
                    "invalid_menu": "HA hat ein ungültiges Menü geliefert."}
        self["status"].setText(messages.get(code, "Abruf fehlgeschlagen. Gelb: erneut laden."))
        self["heading"].setText("OFFLINE – " + (safe_text(self.nav.breadcrumb) if self.nav else "Home Assistant"))
        self.timer.start(self.config["refresh_seconds"] * 1000, True)
        return None  # Consume Deferred failure; do not log request/token details.

    def render(self):
        if not self.nav:
            return
        face, font_size, self.row_height = self.appearance.menu_font(
            self.nav.display["font_family"], self.nav.display["font_size"])
        self["list"].l.setFont(0, gFont(face, font_size))
        self["list"].l.setItemHeight(self.row_height)
        value_width = int(self.list_width * .30)
        label_width = self.list_width - value_width - 24
        rows = []
        for index, (label, value) in enumerate(self.nav.rows(self.states)):
            node = self.nav.current["children"][index]
            state = self.states.get(node.get("entity_id"), {})
            size = min(self.row_height - 8, max(24, int(font_size * 1.2)))
            pixmap = self.state_icons.get(state, size) if node["type"] == "entity" else None
            value_entry = (MultiContentEntryPixmapAlphaBlend(
                pos=(label_width+16, (self.row_height-size)//2), size=(size, size), png=pixmap)
                if pixmap is not None else MultiContentEntryText(
                    pos=(label_width+16, 0), size=(value_width-16, self.row_height), font=0,
                    flags=RT_VALIGN_CENTER, text=safe_text(value)))
            rows.append([index, MultiContentEntryText(pos=(8, 0), size=(label_width, self.row_height), font=0,
                                                     flags=RT_VALIGN_CENTER, text=safe_text(label)), value_entry])
        self["list"].setList(rows)
        self["list"].moveToIndex(self.nav.stack[-1][1])
        self["heading"].setText(("" if self.online else "OFFLINE – ") + safe_text(self.nav.breadcrumb))

    def settings(self):
        if self.busy:
            self["status"].setText("Bitte laufenden Abruf abwarten; danach Menü erneut drücken.")
            return
        self.timer.stop()
        self.session.openWithCallback(self.settings_done, CompanionSetup, self.config)

    def settings_done(self, values):
        if self.closed:
            return
        if values is not None:
            self.config = values
            self.generation += 1
            self.online = False
            self.connect()
        elif hasattr(self, "client"):
            self.refresh()
        else:
            self["status"].setText("Menü drücken, um Home Assistant einzurichten.")

    def help(self):
        direction = "abwärts / − aufwärts" if self.config["reverse_channel_paging"] else "aufwärts / − abwärts"
        self.session.open(MessageBox, HELP.format(channel_help="Ch+ " + direction + ": seitenweise blättern"),
                          type=MessageBox.TYPE_INFO)

    def cleanup(self):
        self.closed = True
        self.generation += 1
        self.timer.stop()
        self.state_icons.close()


def main(session, **kwargs):
    session.open(CompanionScreen)


def menu(menuid, **kwargs):
    if menuid != "mainmenu":
        return []
    try:
        enabled = load_settings()["show_in_mainmenu"]
    except (ValueError, OSError):
        return []
    if not enabled:
        return []
    return [("EnigmaHA Companion", main, "enigmaha_companion", 50)]


def Plugins(**kwargs):
    global _KEYMAP_LOADED
    if not _KEYMAP_LOADED:
        try:
            from keymapparser import readKeymap
        except ImportError:
            from Components.ActionMap import loadKeymap as readKeymap
        readKeymap(os.path.join(os.path.dirname(__file__), "keymap.xml"))
        _KEYMAP_LOADED = True
    return [PluginDescriptor(name="EnigmaHA Companion", description="Home Assistant auf deinem Receiver",
                             where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU], fnc=main),
            PluginDescriptor(name="EnigmaHA Companion", description="Home Assistant auf deinem Receiver",
                             where=PluginDescriptor.WHERE_MENU, fnc=menu)]
