"""Enigma2 GUI: main-loop drawing, worker-thread HTTP, remote navigation."""

import os

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText, MultiContentEntryPixmapAlphaBlend
from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from Screens.ChoiceBox import ChoiceBox
from Screens.Screen import Screen
from enigma import eListboxPythonMultiContent, eSize, eTimer, getDesktop, gFont, RT_VALIGN_CENTER
from twisted.internet.threads import deferToThread

from .companion.client import ClientError, CompanionClient
from .companion.updater import ReceiverUpdater, load_receiver_id
from .enigmaha_protocol.releases import UpdateError, version_tuple
from .enigmaha_protocol.compatibility import VERSION, PROTOCOL_VERSION, valid_version
from .companion.navigation import Navigator
from .companion.i18n import translate
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
        self.appearance = Appearance(getDesktop(0).size(), self.config["skin_profile"], self.config["language"])
        self.ui_scale = self.appearance.scale
        self.list_width = self.appearance.list_width
        self.list_height = self.appearance.list_height
        self.skin = self.appearance.layout()
        Screen.__init__(self, session)
        for name, text in self.appearance.text_labels.items():
            self[name] = Label(text)
        self.skinName = self.appearance.screen_names()
        self.onLayoutFinish.append(self.layout_finished)
        self["heading"] = Label("Home Assistant")
        self["list"] = MenuList([], enableWrapAround=True, content=eListboxPythonMultiContent)
        self["status"] = Label(self.t("Verbindung wird vorbereitet …"))
        self["footer"] = Label(self.t("OK/Grün: Öffnen/Schalten   Gelb: Laden\nMenü/Blau: Einstellungen   Rot: Schließen   Exit: Zurück"))
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
        self.peer_notice = None
        self.update_notice = None
        self.update_installing = False
        self.updater = ReceiverUpdater()
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

    def t(self, message, **values):
        return translate(message, self.appearance.language, **values)

    def layout_finished(self):
        # A skin-provided screen may choose a different list geometry.
        instance = getattr(self["list"], "instance", None)
        if instance is not None:
            size = instance.size()
            self.list_width, self.list_height = size.width(), size.height()
        self.appearance.apply_list_skin(getattr(self["list"], "skinAttributes", None) or [],
                                        getattr(self, "scale", ((1, 1), (1, 1))))
        self.render()

    def start(self):
        if self.config_error:
            self["status"].setText(self.t("Konfiguration nicht lesbar. Bitte Einstellungen prüfen."))
        if not self.config["url"] or not self.config["token"]:
            self.settings()
        else:
            self.connect()

    def connect(self):
        try:
            self.client = CompanionClient(self.config["url"], self.config["token"], self.config["timeout"],
                                          receiver_id=load_receiver_id())
        except (ValueError, OSError):
            self["status"].setText(self.t("Adresse oder Token ungültig. Menü: Einstellungen"))
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
            self["status"].setText(self.t("Bitte aktuelle Zustände abwarten. Gelb: erneut laden."))
            return
        command = self.nav.activate(self.states)
        if command is None:
            self["status"].setText(self.t("Dieser Eintrag ist nur lesbar oder nicht verfügbar."))
            return
        client = self.client
        def work():
            client.execute(command)
            return self.snapshot(client)
        self.run(work, self.t("Schaltbefehl wird gesendet …"))

    @staticmethod
    def snapshot(client):
        local = ReceiverUpdater().local_restart()
        if local:
            return {"update": local}
        job = client.get_update()
        if job and job["status"] in {"pending", "installing", "restart_required"}:
            return {"update": job}
        if job:
            ReceiverUpdater().acknowledge_running(job)
        menu = client.get_menu()
        return menu, client.get_states(menu)

    def refresh(self):
        if self.closed or self.busy or not hasattr(self, "client"):
            return
        client = self.client
        self.run(lambda: self.snapshot(client), self.t("Zustände werden geladen …"))

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
        if isinstance(result, dict) and "update" in result:
            self.busy, self.online = False, False
            self.update_loaded(result["update"])
            return
        if isinstance(result, dict) and "installed_update" in result:
            self.busy, self.online, self.update_installing = False, False, False
            self.offer_restart(result["installed_update"])
            return
        menu, states = result
        new_nav = Navigator(menu, language=self.appearance.language)
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
        self.peer_notice = None
        self.render()
        message = self.t("Verbunden") if self.nav.current["children"] else self.t("Menü ist leer. Einträge in Home Assistant hinzufügen.")
        no_menu = menu["root"]["id"] == "__enigmaha_no_menu" and not menu["root"]["children"]
        if no_menu:
            message = self.t("Für diesen Benutzer ist kein Menü freigegeben.")
        peer_version = getattr(getattr(self, "client", None), "peer_version", None)
        if peer_version and peer_version != VERSION and not no_menu:
            message = self.t("Verbunden · Receiver {receiver}, HA {ha} · Protokoll {protocol} passt.",
                            receiver=VERSION, ha=peer_version, protocol=PROTOCOL_VERSION)
        self["status"].setText(message)
        self.timer.start(self.config["refresh_seconds"] * 1000, True)

    def failed(self, failure, generation):
        if self.closed or generation != self.generation:
            return None
        was_updating = self.update_installing
        self.busy, self.online = False, False
        self.update_installing = False
        error = failure.value
        if isinstance(error, UpdateError):
            reasons = {"download_failed": "IPK konnte nicht geladen werden. Internetverbindung prüfen.",
                       "checksum_failed": "IPK-Prüfsumme stimmt nicht. Keine Installation ausgeführt.",
                       "invalid_package": "IPK passt nicht zu diesem Release oder Receiver.",
                       "install_uncertain": "Installation unklar. Paketstatus prüfen; keine automatische Wiederholung.",
                       "permission_denied": "Für das Receiver-Update werden Root-Rechte benötigt.",
                       "update_storage_failed": "Updatefortschritt konnte nicht gespeichert werden. Dateirechte prüfen.",
                       "invalid_release": "Passender Release nicht verfügbar oder unvollständig. GitHub-Verbindung und Release-Pakete prüfen.",
                       "release_check_failed": "Passender Release nicht verfügbar oder unvollständig. GitHub-Verbindung und Release-Pakete prüfen.",
                       "update_in_progress": "Gemeinsames Update im HA-Editor fortsetzen oder erneut anbieten."}
            message = self.t(reasons.get(error.code, "Receiver-Update fehlgeschlagen. Fortschritt im HA-Editor prüfen."))
            self["status"].setText(message)
            self.session.open(MessageBox, message, type=MessageBox.TYPE_ERROR)
            self.timer.start(self.config["refresh_seconds"] * 1000, True)
            return None
        if was_updating:
            self["status"].setText(self.t("Updateverbindung unterbrochen. Fortschritt wird beim nächsten Abruf geprüft."))
            self.timer.start(self.config["refresh_seconds"] * 1000, True)
            return None
        code = error.code if isinstance(error, ClientError) else "unknown"
        if code == "unauthorized":
            self.nav, self.states = None, {}
            self.render()
        messages = {"unauthorized": self.t("Token abgelehnt. Menü: Einstellungen"),
                    "protocol_mismatch": self.t("Protokolle ungleich: Receiver {receiver}, HA {ha}. Reparatur in Home Assistant unter Einstellungen öffnen.",
                                              receiver=PROTOCOL_VERSION, ha=getattr(error, "peer_protocol", None) or "?"),
                    "legacy_version_mismatch": self.t("Ältere HA-Integration verlangt denselben Release. HA und Receiver einmal gemeinsam aktualisieren."),
                    "version_mismatch": self.t("Versionen ungleich: Receiver {receiver}, HA {ha}. Beide auf denselben Release aktualisieren.",
                                              receiver=VERSION, ha=getattr(error, "peer_version", None) or "?"),
                    "unidentified_peer": self.t("Gegenstelle nicht als passende EnigmaHA-Integration erkennbar. Installation und Version prüfen."),
                    "forbidden": self.t("Keine Berechtigung für diese Aktion."),
                    "not_found": self.t("HA-Integration nicht erreichbar. Installation prüfen."),
                    "conflict": self.t("Menü/Zustand geändert. Gelb: neu laden."),
                    "stale_menu": self.t("Menü geändert. Wird erneut geladen."),
                    "connection_failed": self.t("Verbindung fehlgeschlagen. Schaltzustand unklar; keine Wiederholung."),
                    "invalid_menu": self.t("HA hat ein ungültiges Menü geliefert.")}
        self["status"].setText(messages.get(code, self.t("Abruf fehlgeschlagen. Gelb: erneut laden.")))
        if code in {"version_mismatch", "protocol_mismatch", "legacy_version_mismatch", "unidentified_peer"}:
            notice = (code, error.peer_version, getattr(error, "peer_protocol", None))
            if notice != self.peer_notice:
                self.peer_notice = notice
                if code != "unidentified_peer" and valid_version(error.peer_version) and version_tuple(error.peer_version) > version_tuple(VERSION):
                    self.busy = True
                    self.session.openWithCallback(
                        lambda choice: self.mismatch_update_answer(choice, error.peer_version, generation), ChoiceBox,
                        title=messages[code], list=[
                            (self.t("Receiver auf {version} aktualisieren", version=error.peer_version), "update"),
                            (self.t("Schließen"), "close")])
                else:
                    self.session.open(MessageBox, messages[code], type=MessageBox.TYPE_ERROR)
            # Keep the status line short; the dialog contains the recovery steps.
            self["status"].setText(messages[code] if code in {"protocol_mismatch", "legacy_version_mismatch"} else self.t("Versionen ungleich: Receiver {receiver}, HA {ha}.",
                                         receiver=VERSION, ha=error.peer_version or "?")
                                   if code == "version_mismatch" else self.t("EnigmaHA-Gegenstelle nicht erkannt. Installation prüfen."))
        self["heading"].setText("OFFLINE – " + (safe_text(self.nav.breadcrumb) if self.nav else "Home Assistant"))
        self.timer.start(self.config["refresh_seconds"] * 1000, True)
        return None  # Consume Deferred failure; do not log request/token details.

    def mismatch_update_answer(self, choice, version, generation):
        if self.closed or generation != self.generation:
            return
        self.busy = False
        if choice and choice[1] == "update":
            client = self.client
            def work():
                try:
                    job = client.get_update()
                except ClientError as error:
                    if error.code not in {"not_found", "legacy_version_mismatch"}:
                        raise
                    job = None
                if job and job["status"] != "completed":
                    if job["status"] not in {"pending", "installing", "restart_required"}:
                        raise UpdateError("update_in_progress")
                    return {"update": job}
                return {"update": self.updater.local_update(version)}
            self.run(work, self.t("Passendes Receiver-Update wird geprüft …"))
        else:
            self.timer.start(self.config["refresh_seconds"] * 1000, True)

    def update_loaded(self, job):
        self.timer.stop()
        key = (job["id"], job["attempt"])
        if job["status"] == "restart_required":
            self.offer_restart(job)
            return
        if job["status"] == "installing":
            # Resume only consent already written locally. perform() checks the journal.
            self.install_update(job, confirmed=False)
            return
        if key == self.update_notice:
            self["status"].setText(self.t("Update wartet auf Bestätigung. Plugin erneut öffnen."))
            self.timer.start(self.config["refresh_seconds"] * 1000, True)
            return
        self.update_notice = key
        self.busy = True
        prompt = ("Receiver auf Release {version} aktualisieren? Das geprüfte IPK wird installiert. Danach ist ein GUI-Neustart nötig."
                  if job.get("local") else "Release {version} für HA und Receiver verwenden? Das geprüfte IPK wird installiert. Danach ist ein GUI-Neustart nötig.")
        self.session.openWithCallback(lambda answer: self.update_answer(job, answer), MessageBox,
            self.t(prompt, version=job["release"]["version"]), type=MessageBox.TYPE_YESNO, default=False)

    def update_answer(self, job, answer):
        if self.closed:
            return
        self.busy = False
        if answer:
            self.install_update(job, confirmed=True)
        elif job.get("local"):
            self["status"].setText(self.t("Update abgelehnt."))
            self.timer.start(self.config["refresh_seconds"] * 1000, True)
        else:
            client = self.client
            def work():
                client.report_update(job, "declined")
                return self.snapshot(client)
            self.run(work, self.t("Update abgelehnt."))

    def install_update(self, job, confirmed):
        client = self.client
        def work():
            from Components.SystemInfo import BoxInfo
            if BoxInfo.getItem("distro") != "openatv":
                raise UpdateError("invalid_package")
            if confirmed:
                self.updater.confirm(job)
            self.updater.perform(job, None if job.get("local") else client)
            return {"installed_update": job}
        self.update_installing = True
        self.run(work, self.t("Receiver-Update wird installiert. Bitte warten …"))

    def offer_restart(self, job):
        key = (job["id"], "restart")
        self["status"].setText(self.t("Update installiert. GUI-Neustart erforderlich."))
        if self.update_notice == key:
            self.timer.start(self.config["refresh_seconds"] * 1000, True)
            return
        self.update_notice = key
        self.busy = True
        self.session.openWithCallback(self.restart_answer, MessageBox,
            self.t("Release {version} installiert. Receiver-GUI jetzt neu starten? Aufnahmen werden durch die OpenATV-Neustartprüfung berücksichtigt.",
                   version=job["release"]["version"]), type=MessageBox.TYPE_YESNO, default=False)

    def restart_answer(self, answer):
        if self.closed:
            return
        self.busy = False
        if answer:
            from Screens.Standby import TryQuitMainloop
            self.session.open(TryQuitMainloop, 3)
        self.timer.start(self.config["refresh_seconds"] * 1000, True)

    def close(self, *args, **kwargs):
        if self.update_installing:
            self["status"].setText(self.t("Receiver-Update wird installiert. Bitte warten …"))
            return
        Screen.close(self, *args, **kwargs)

    def render(self):
        if not self.nav:
            self["list"].setList([])
            self["heading"].setText("Home Assistant")
            return
        face, font_size, self.row_height = self.appearance.menu_font(
            self.config["font_family"], self.config["font_size"])
        self["list"].l.setFont(0, gFont(face, font_size))
        self["list"].l.setItemHeight(self.row_height)
        instance = getattr(self["list"], "instance", None)
        if instance is not None:
            # Font-dependent row heights need a whole-row viewport. Otherwise
            # OpenATV can draw the next entry cut off above the status line.
            height = self.page_size() * self.row_height
            if instance.size().height() != height:
                instance.resize(eSize(self.list_width, height))
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
            self["status"].setText(self.t("Bitte laufenden Abruf abwarten; danach Menü erneut drücken."))
            return
        self.timer.stop()
        self.session.openWithCallback(self.settings_done, CompanionSetup, self.config)

    def settings_done(self, values):
        if self.closed:
            return
        if values is not None:
            identity_changed = any(values.get(key) != self.config.get(key) for key in ("url", "token"))
            self.config = values
            self.generation += 1
            self.online = False
            if identity_changed:
                self.nav, self.states = None, {}
                self.render()
            self.connect()
        elif hasattr(self, "client"):
            self.refresh()
        else:
            self["status"].setText(self.t("Menü drücken, um Home Assistant einzurichten."))

    def help(self):
        channel_help = ("Ch+ abwärts / − aufwärts: seitenweise blättern" if self.config["reverse_channel_paging"]
                        else "Ch+ aufwärts / − abwärts: seitenweise blättern")
        self.session.open(MessageBox, self.t(HELP, channel_help=self.t(channel_help)),
                          type=MessageBox.TYPE_INFO)

    def cleanup(self):
        self.closed = True
        self.generation += 1
        self.timer.stop()
        self.state_icons.close()


def main(session, **kwargs):
    session.open(CompanionScreen)


_UPDATE_REPORT_TIMER = None


def report_after_restart(reason, **kwargs):
    """Report the running release after GUI restart; never install in the background."""
    global _UPDATE_REPORT_TIMER
    if reason != 0:
        if _UPDATE_REPORT_TIMER is not None:
            _UPDATE_REPORT_TIMER.stop()
        return
    attempts = [0]
    timer = _UPDATE_REPORT_TIMER = eTimer()
    def work():
        config = load_settings()
        if not config["url"] or not config["token"]:
            return
        client = CompanionClient(config["url"], config["token"], config["timeout"], receiver_id=load_receiver_id())
        ReceiverUpdater().acknowledge_running(client.get_update())
    def failed(failure):
        attempts[0] += 1
        if attempts[0] < 10:
            timer.start(30000, True)
        return None
    def report():
        deferToThread(work).addCallbacks(lambda result: None, failed)
    timer.callback.append(report)
    timer.start(10000, True)


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
    try:
        language = load_settings()["language"]
    except (ValueError, OSError):
        language = "de"
    t = lambda message: translate(message, language)
    global _KEYMAP_LOADED
    if not _KEYMAP_LOADED:
        try:
            from keymapparser import readKeymap
        except ImportError:
            from Components.ActionMap import loadKeymap as readKeymap
        readKeymap(os.path.join(os.path.dirname(__file__), "keymap.xml"))
        _KEYMAP_LOADED = True
    return [PluginDescriptor(name="EnigmaHA Companion", description=t("Home Assistant auf deinem Receiver"),
                             where=[PluginDescriptor.WHERE_PLUGINMENU, PluginDescriptor.WHERE_EXTENSIONSMENU], fnc=main),
            PluginDescriptor(name="EnigmaHA Companion", description=t("Home Assistant auf deinem Receiver"),
                             where=PluginDescriptor.WHERE_MENU, fnc=menu),
            PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=report_after_restart)]
