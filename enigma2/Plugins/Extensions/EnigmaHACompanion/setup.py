from Components.ActionMap import ActionMap
from Components.ConfigList import ConfigListScreen
from Components.Label import Label
from Components.config import ConfigInteger, ConfigPassword, ConfigSelection, ConfigText, ConfigYesNo, getConfigListEntry
from Screens.ChoiceBox import ChoiceBox
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard

from enigma import getDesktop, getFontFaces

from .companion.i18n import LANGUAGE_CHOICES, translate
from .appearance import Appearance
from .skin import profile_choices
from .companion.client import CompanionClient
from .settings import DEFAULTS, save_settings, validate_settings


class CompanionSetup(Screen, ConfigListScreen):
    def __init__(self, session, values=None):
        values = values or DEFAULTS
        self.language = values["language"]
        self.appearance = Appearance(getDesktop(0).size(), values["skin_profile"], self.language)
        self.skin = self.appearance.layout(setup=True)
        Screen.__init__(self, session)
        for name, text in self.appearance.text_labels.items():
            self[name] = Label(text)
        self.skinName = self.appearance.screen_names(setup=True)
        families = sorted(set(getFontFaces()) | {"Regular"})
        font_choices = [("", self.t("Aus HA übernehmen"))] + [(name, name) for name in families]
        if values["font_family"] and values["font_family"] not in families:
            # Keep an existing preference when the active skin no longer has it.
            font_choices.append((values["font_family"], self.t("{name} (Ersatz: Regular)", name=values["font_family"])))
        self.selection_choices = {
            "language": LANGUAGE_CHOICES,
            "skin_profile": profile_choices(self.language),
            "font_family": font_choices,
            "font_size": [("0", self.t("Aus HA übernehmen"))] + [(str(size), str(size)) for size in range(16, 65)],
        }
        self.fields = {
            "language": ConfigSelection(choices=LANGUAGE_CHOICES, default=self.language),
            "skin_profile": ConfigSelection(choices=self.selection_choices["skin_profile"], default=values["skin_profile"]),
            "url": ConfigText(default=values["url"], fixed_size=False),
            "token": ConfigPassword(default=values["token"], fixed_size=False, visible_width=24),
            "refresh_seconds": ConfigInteger(default=values["refresh_seconds"], limits=(5, 300)),
            "font_family": ConfigSelection(choices=self.selection_choices["font_family"], default=values["font_family"]),
            "font_size": ConfigSelection(choices=self.selection_choices["font_size"], default=str(values["font_size"])),
            "timeout": ConfigInteger(default=values["timeout"], limits=(1, 30)),
            "show_in_mainmenu": ConfigYesNo(default=values["show_in_mainmenu"]),
            "reverse_channel_paging": ConfigYesNo(default=values["reverse_channel_paging"]),
        }
        for key in ("show_in_mainmenu", "reverse_channel_paging"):
            self.fields[key].descriptions = {False: self.t("Nein"), True: self.t("Ja")}
        labels = [("language", "Sprache (ab nächstem Öffnen)"),
                  ("url", "Home-Assistant-Adresse (mit http:// oder https://)"),
                  ("token", "Langlebiger HA-Zugriffstoken"),
                  ("refresh_seconds", "Aktualisierung in Sekunden"),
                  ("skin_profile", "Skin-Profil (ab nächstem Öffnen)"),
                  ("font_family", "Schriftfamilie (Standard-Profil)"),
                  ("font_size", "Schriftgröße (Standard-Profil)"),
                  ("timeout", "Verbindungszeitlimit in Sekunden"),
                  ("show_in_mainmenu", "Im Hauptmenü anzeigen"),
                  ("reverse_channel_paging", "Ch+/− umkehren (Nein: + aufwärts / − abwärts)")]
        ConfigListScreen.__init__(self, [getConfigListEntry(self.t(label), self.fields[key]) for key, label in labels], session=session)
        self["hint"] = Label(self.t("Grün: Speichern   Rot/Exit: Abbrechen\nOK/Gelb: Auswahl/Text   Links/Rechts: Wert ändern"))
        self["setupActions"] = ActionMap(["SetupActions", "ColorActions"], {
            "save": self.save, "cancel": self.cancel, "ok": self.edit,
            "green": self.save, "red": self.cancel, "yellow": self.edit,
        }, -3)

    def t(self, message, **values):
        return translate(message, self.language, **values)

    def handleInputHelpers(self):
        handler = getattr(ConfigListScreen, "handleInputHelpers", None)
        if handler is not None:
            handler(self)
        current = self["config"].getCurrent()
        helper = getattr(current[1], "help_window", None) if current else None
        window = getattr(self, "instance", None)
        if window is not None and helper is not None and helper.instance is not None:
            from enigma import ePoint
            # Input help is a separate desktop window, not a child of this dialog.
            # Place it above the footer instead of ConfigList's unskinned (0, 0) anchor.
            position, size = window.position(), window.size()
            help_size = helper.instance.size()
            x = position.x() + max(0, (size.width() - help_size.width()) // 2)
            y = position.y() + max(0, size.height() - self.appearance.footer
                                  - self.appearance.px(12) - help_size.height())
            helper.instance.move(ePoint(x, y))

    def edit(self):
        current = self["config"].getCurrent()
        if current:
            for key, choices in self.selection_choices.items():
                if current[1] is not self.fields[key]:
                    continue
                field = current[1]
                entries = [(label, value) for value, label in choices]
                def selected(choice):
                    if choice is not None:
                        field.value = choice[1]
                        self["config"].invalidateCurrent()
                index = next((i for i, entry in enumerate(entries) if entry[1] == field.value), 0)
                self.session.openWithCallback(selected, ChoiceBox, title=current[0], list=entries, selection=index)
                return
        if current and isinstance(current[1], ConfigText):
            field = current[1]
            def changed(value):
                if value is not None:
                    field.value = value
                    self["config"].invalidateCurrent()
            self.session.openWithCallback(changed, VirtualKeyBoard, title=current[0], text=field.value)

    def cancel(self):
        self.close(None)

    def save(self):
        values = {name: field.value for name, field in self.fields.items()}
        values["font_size"] = int(values["font_size"])
        values["url"] = values["url"].strip().rstrip("/")
        values["token"] = values["token"].strip()
        try:
            values = validate_settings(values)
            CompanionClient(values["url"], values["token"], values["timeout"])
            save_settings(values)
        except (ValueError, OSError):
            self.session.open(MessageBox, self.t("Einstellungen konnten nicht gespeichert werden. Adresse, Token, Schriftgröße und Dateirechte prüfen."), type=MessageBox.TYPE_ERROR)
            return
        self.close(values)
