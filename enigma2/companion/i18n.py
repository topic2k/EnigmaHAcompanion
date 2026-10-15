"""German/English messages with optional OpenATV language detection."""

LANGUAGE_CHOICES = [("de", "Deutsch"), ("en", "English"), ("auto", "Automatisch")]

ENGLISH = {
    "EnigmaHA: {path} – Umschalten": "EnigmaHA: {path} – Toggle",
    "Hotkey-Liste konnte nicht gespeichert werden. Dateirechte und freien Speicher prüfen.": "Could not save the hotkey list. Check file permissions and free space.",
    "Hotkey-Eintrag nicht mehr freigegeben oder geändert. Hotkeys neu zuordnen.": "Hotkey entry is no longer shared or has changed. Assign hotkeys again.",
    "Hotkey konnte nicht geschaltet werden. Zustand und Verbindung in EnigmaHA Companion prüfen.": "Could not toggle the hotkey entry. Check its state and connection in EnigmaHA Companion.",
    "Token ungültig oder abgelaufen. Menü: Einstellungen": "Token invalid or expired. Menu: Settings",
    "Keine Berechtigung für diesen Eintrag.": "No permission for this entry.",
    "Home Assistant nicht erreichbar. Adresse/Netzwerk prüfen.": "Home Assistant unreachable. Check its address and network.",
    "Menüposition beim Beenden merken": "Remember menu position on exit",
    "Ungültige Menüpositions-Einstellung": "Invalid menu position setting",
    "Auf/Ab: Eintrag wählen\nLinks/Rechts: eine Seite aufwärts/abwärts\nRecall: eine Ebene zurück; im Hauptmenü ohne Funktion\nOK/Grün: Untermenü öffnen oder Licht/Schalter umschalten\nMenü/Blau: Einstellungen\nGelb: Aktualisieren\n{channel_help}\nRot/Exit: Menü komplett schließen\nInfo: Programminformationen\nSensoren sind nur lesbar. Die Menüstruktur wird in Home Assistant festgelegt.": "Up/Down: Select entry\nLeft/Right: Page up/down\nRecall: Go back one level; no action at the root menu\nOK/Green: Open submenu or toggle light/switch\nMenu/Blue: Settings\nYellow: Refresh\n{channel_help}\nRed/Exit: Close the entire menu\nInfo: Program information\nSensors are read-only. The menu structure is configured in Home Assistant.",
    "OK/Grün: Öffnen/Schalten   Gelb: Laden   Rot/Exit: Schließen\nMenü/Blau: Einstellungen   Recall: Zurück   Info: Informationen": "OK/Green: Open/Toggle   Yellow: Reload   Red/Exit: Close\nMenu/Blue: Settings   Recall: Back   Info: Information",
    "Informationen": "Information",
    "Version auf dem Receiver: {version}": "Version on the receiver: {version}",
    "Version in Home Assistant: {version}": "Version in Home Assistant: {version}",
    "Angemeldeter Benutzer: {name}": "Logged-in user: {name}",
    "Für diesen Benutzer sichtbare Einträge:": "Entries visible to this user:",
    "Menüs: {count}": "Menus: {count}",
    "Untermenüs: {count}": "Submenus: {count}",
    "Entitäten: {count}": "Entities: {count}",
    "Benutzer und Menüumfang derzeit nicht abrufbar.": "User and menu counts are currently unavailable.",
    "Receiver auf {version} aktualisieren": "Update receiver to {version}",
    "Passendes Receiver-Update wird geprüft …": "Checking for the matching receiver update …",
    "Passender Release nicht verfügbar oder unvollständig. GitHub-Verbindung und Release-Pakete prüfen.": "Matching release unavailable or incomplete. Check the GitHub connection and release packages.",
    "Gemeinsames Update im HA-Editor fortsetzen oder erneut anbieten.": "Continue or offer the coordinated update again in the HA editor.",
    "Receiver auf Release {version} aktualisieren? Das geprüfte IPK wird installiert. Danach ist ein GUI-Neustart nötig.": "Update receiver to release {version}? The verified IPK will be installed. A GUI restart is required afterwards.",
    "Für diesen Benutzer ist kein Menü freigegeben.": "No menu is shared with this user.",
    "Verbunden · Receiver {receiver}, HA {ha} · Protokoll {protocol} passt.": "Connected · Receiver {receiver}, HA {ha} · Protocol {protocol} matches.",
    "Protokolle ungleich: Receiver {receiver}, HA {ha}. Reparatur in Home Assistant unter Einstellungen öffnen.": "Protocols differ: receiver {receiver}, HA {ha}. Open Repairs in Home Assistant Settings.",
    "Ältere HA-Integration verlangt denselben Release. HA und Receiver einmal gemeinsam aktualisieren.": "The older HA integration requires matching releases. Update HA and receiver together once.",
    "IPK konnte nicht geladen werden. Internetverbindung prüfen.": "Could not download the IPK. Check the internet connection.",
    "IPK-Prüfsumme stimmt nicht. Keine Installation ausgeführt.": "IPK checksum does not match. Nothing was installed.",
    "IPK passt nicht zu diesem Release oder Receiver.": "The IPK does not match this release or receiver.",
    "Installation unklar. Paketstatus prüfen; keine automatische Wiederholung.": "Installation outcome uncertain. Check package status; no automatic retry.",
    "Für das Receiver-Update werden Root-Rechte benötigt.": "Root permissions are required for the receiver update.",
    "Updatefortschritt konnte nicht gespeichert werden. Dateirechte prüfen.": "Could not save update progress. Check file permissions.",
    "Receiver-Update fehlgeschlagen. Fortschritt im HA-Editor prüfen.": "Receiver update failed. Check progress in the HA editor.",
    "Updateverbindung unterbrochen. Fortschritt wird beim nächsten Abruf geprüft.": "Update connection interrupted. Progress will be checked on the next refresh.",
    "Update wartet auf Bestätigung. Plugin erneut öffnen.": "Update is waiting for confirmation. Reopen the plugin.",
    "Release {version} für HA und Receiver verwenden? Das geprüfte IPK wird installiert. Danach ist ein GUI-Neustart nötig.": "Use release {version} for HA and receiver? The verified IPK will be installed. A GUI restart is required afterwards.",
    "Update abgelehnt.": "Update declined.",
    "Receiver-Update wird installiert. Bitte warten …": "Installing receiver update. Please wait …",
    "Update installiert. GUI-Neustart erforderlich.": "Update installed. GUI restart required.",
    "Release {version} installiert. Receiver-GUI jetzt neu starten? Aufnahmen werden durch die OpenATV-Neustartprüfung berücksichtigt.": "Release {version} installed. Restart the receiver GUI now? The OpenATV restart check considers recordings.",
    "Sprache (ab nächstem Öffnen)": "Language (from next opening)",
    "Auto (Skin-/Receiver-Standard)": "Auto (skin/receiver default)",
    "{name} (Ersatz: Regular)": "{name} (fallback: Regular)",
    "Home-Assistant-Adresse (mit http:// oder https://)": "Home Assistant address (with http:// or https://)",
    "Langlebiger HA-Zugriffstoken": "Long-lived HA access token",
    "Aktualisierung in Sekunden": "Refresh interval in seconds",
    "Skin-Profil (ab nächstem Öffnen)": "Skin profile (from next opening)",
    "Schriftfamilie": "Font family",
    "Schriftgröße": "Font size",
    "Verbindungszeitlimit in Sekunden": "Connection timeout in seconds",
    "Im Hauptmenü anzeigen": "Show in main menu",
    "Ch+/− umkehren (Nein: + aufwärts / − abwärts)": "Reverse Ch+/− (No: + up / − down)",
    "Grün: Speichern   Rot/Exit: Abbrechen\nOK/Gelb: Auswahl/Text   Links/Rechts: Wert ändern": "Green: Save   Red/Exit: Cancel\nOK/Yellow: Select/Text   Left/Right: Change value",
    "Einstellungen konnten nicht gespeichert werden. Adresse, Token, Schriftgröße und Dateirechte prüfen.": "Could not save settings. Check the address, token, font size and file permissions.",
    "Automatisch": "Automatic",
    "Standard (aktiver Skin)": "Standard (active skin)",
    "EnigmaHA Companion – Einstellungen": "EnigmaHA Companion – Settings",
    "EnigmaHA – Einstellungen": "EnigmaHA – Settings",
    "Abbrechen": "Cancel",
    "Schließen": "Close",
    "Speichern": "Save",
    "Öffnen/Schalten": "Open/Toggle",
    "Auswahl/Text": "Select/Text",
    "Aktualisieren": "Refresh",
    "Wert ändern": "Change value",
    "Einstellungen": "Settings",
    "Zurück": "Back",
    "Rot": "Red",
    "Grün": "Green",
    "Gelb": "Yellow",
    "Menü": "Menu",
    "Blau": "Blue",
    "Verbindung wird vorbereitet …": "Preparing connection …",
    "Konfiguration nicht lesbar. Bitte Einstellungen prüfen.": "Cannot read configuration. Please check the settings.",
    "Adresse oder Token ungültig. Menü: Einstellungen": "Invalid address or token. Menu: Settings",
    "Bitte aktuelle Zustände abwarten. Gelb: erneut laden.": "Please wait for current states. Yellow: Reload.",
    "Dieser Eintrag ist nur lesbar oder nicht verfügbar.": "This entry is read-only or unavailable.",
    "Schaltbefehl wird gesendet …": "Sending command …",
    "Zustände werden geladen …": "Loading states …",
    "Verbunden": "Connected",
    "Versionen ungleich: Receiver {receiver}, HA {ha}.": "Version mismatch: receiver {receiver}, HA {ha}.",
    "EnigmaHA-Gegenstelle nicht erkannt. Installation prüfen.": "EnigmaHA peer not identified. Check installation.",
    "Versionen ungleich: Receiver {receiver}, HA {ha}. Beide auf denselben Release aktualisieren.": "Version mismatch: receiver {receiver}, HA {ha}. Update both to the same release.",
    "Gegenstelle nicht als passende EnigmaHA-Integration erkennbar. Installation und Version prüfen.": "Cannot identify the peer as a matching EnigmaHA integration. Check installation and version.",
    "Menü ist leer. Einträge in Home Assistant hinzufügen.": "The menu is empty. Add entries in Home Assistant.",
    "Token abgelehnt. Menü: Einstellungen": "Token rejected. Menu: Settings",
    "Keine Berechtigung für diese Aktion.": "You do not have permission for this action.",
    "HA-Integration nicht erreichbar. Installation prüfen.": "HA integration is unreachable. Check the installation.",
    "Menü/Zustand geändert. Gelb: neu laden.": "Menu/state changed. Yellow: Reload.",
    "Menü geändert. Wird erneut geladen.": "Menu changed. Reloading.",
    "Verbindung fehlgeschlagen. Schaltzustand unklar; keine Wiederholung.": "Connection failed. Switch state is uncertain; command will not be repeated.",
    "HA hat ein ungültiges Menü geliefert.": "HA returned an invalid menu.",
    "Abruf fehlgeschlagen. Gelb: erneut laden.": "Request failed. Yellow: Reload.",
    "Bitte laufenden Abruf abwarten; danach Menü erneut drücken.": "Please wait for the current request, then press Menu again.",
    "Menü drücken, um Home Assistant einzurichten.": "Press Menu to set up Home Assistant.",
    "Home Assistant auf deinem Receiver": "Home Assistant on your receiver",
    "Ch+ abwärts / − aufwärts: seitenweise blättern": "Ch+ down / − up: page through entries",
    "Ch+ aufwärts / − abwärts: seitenweise blättern": "Ch+ up / − down: page through entries",
    "Nicht vorhanden": "Not found",
    "Nicht verfügbar": "Unavailable",
    "Unbekannt": "Unknown",
    "Ein": "On",
    "Aus": "Off",
    "Ungültige Konfigurationsfelder": "Invalid configuration fields",
    "Ungültiges Skin-Profil": "Invalid skin profile",
    "Ungültige Sprache": "Invalid language",
    "Ungültiger Hauptmenü-Schalter": "Invalid main menu setting",
    "Ungültige Ch-Blätterrichtung": "Invalid channel paging direction",
    "Ungültiger Textwert": "Invalid text value",
    "Ungültige Schriftfamilie": "Invalid font family",
    "Ungültiger Zahlenwert": "Invalid numeric value",
    "Schriftgröße: 0 oder 16–64": "Font size: 0 or 16–64",
    "Ja": "Yes",
    "Nein": "No"
}


def resolve_language(language):
    """Resolve automatic presentation from the OpenATV locale, without changing settings."""
    if language != "auto":
        return language if language in ("de", "en") else "de"
    try:
        from Components.International import international
        locale = international.getLocale()
    except (ImportError, AttributeError):
        try:
            from Components.Language import language as receiver_language
            locale = receiver_language.getLanguage()
        except (ImportError, AttributeError):
            locale = None
    if isinstance(locale, str):
        code = locale.strip().lower().replace("-", "_").split("_")[0]
        if code in ("de", "en"):
            return code
    return "de"


def translate(message, language="de", **values):
    text = ENGLISH.get(message, message) if resolve_language(language) == "en" else message
    return text.format(**values) if values else text
