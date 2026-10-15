# Installation und Bedienung

**Deutsch** · [English](Installation.en.md)

EnigmaHA Companion verbindet Home Assistant mit deinem Enigma2-Receiver.
Du richtest das Menü in Home Assistant ein und bedienst es auf dem Fernseher
mit der Fernbedienung. Die Installation besteht aus einer HA-Integration und
einem Receiver-Plugin. Die Pakete enthalten alle projektspezifischen Module;
ein zusätzlicher Server oder MQTT-Broker ist nicht erforderlich.

## Voraussetzungen

- Home Assistant mit Administratorrechten für Installation und Menüeditor.
- Für die empfohlene Installation: eingerichtetes HACS und ein veröffentlichtes
  [EnigmaHA-Release](https://github.com/topic2k/EnigmaHAcompanion/releases).
- OpenATV mit Enigma2, Python 3.13 oder neuer und Twisted.
  Python-2-Images werden nicht unterstützt. Verwende einen HD- oder Full-HD-Skin.
- Der Receiver erreicht die HA-Adresse im Netzwerk.
- Ein langlebiger HA-Zugriffstoken eines aktiven Benutzers mit Lese- und
  Steuerungsrechten auf die ausgewählten Entitäten. Für den Receiver genügt ein
  normaler Benutzer; der Menüeditor erfordert einen Administrator.

Die [Entwicklerdokumentation](Entwicklung.md#updateablauf-und-grenzen) beschreibt
den Updateablauf und seine Grenzen.

## 1. Home Assistant installieren

### Über HACS (empfohlen)

1. In HACS **⋮ → Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/topic2k/EnigmaHAcompanion` mit Kategorie **Integration** hinzufügen.
3. **EnigmaHA Companion** suchen und herunterladen.
4. Home Assistant neu starten.
5. **Einstellungen → Geräte & Dienste → Integration hinzufügen → EnigmaHA Companion**.
6. In der Seitenleiste **EnigmaHA Companion** öffnen.

### Manuell über ZIP

Das versionierte HA-ZIP `enigmaha-companion-ha-<Version>.zip` aus den
[Releases](https://github.com/topic2k/EnigmaHAcompanion/releases) herunterladen.
Das separate ZIP `enigmaha_companion.zip` ist für HACS bestimmt.

1. Das versionierte ZIP entpacken.
2. Den enthaltenen Ordner `custom_components/enigmaha_companion` in den
   HA-Konfigurationsordner kopieren. Das Ergebnis muss
   `<HA-Konfiguration>/custom_components/enigmaha_companion/manifest.json` sein.
   Bei HA OS ist der Konfigurationsordner normalerweise `/config`.
3. Home Assistant neu starten.
4. **Einstellungen → Geräte & Dienste → Integration hinzufügen → EnigmaHA Companion**.
5. In der Seitenleiste **EnigmaHA Companion** öffnen.

## 2. Menü zusammenstellen

Bei jeder Receiver-Anfrage prüfen beide Seiten EnigmaHA-Kennung, Release und
Protokollversion. Bei gleichem Protokoll funktionieren unterschiedliche Releases;
der HA-Editor zeigt dazu einen Hinweis und Links zu den Release-Informationen.
Unterschiedliche oder unbekannte Protokolle sowie fehlende/ungültige Kennungen
sperren Abrufe und Schaltbefehle. Der Receiver zeigt einen entsprechenden Hinweis;
der HA-Editor zeigt die Anfragen der letzten fünf Minuten und aktualisiert die
Anzeige alle 30 Sekunden. Ohne Receiver-Anfrage ist noch keine Prüfung möglich.

Das [gemeinsame Update](#gemeinsames-update-über-hacs-und-ipk) bringt HA und die
beteiligten Receiver nach Bestätigung auf denselben Release. Menü,
Receiver-Einstellungen und Token bleiben erhalten; eine Neueinrichtung ist nicht nötig.

Bei einem Protokollkonflikt erscheint zusätzlich eine Meldung unter
**Einstellungen → System → Reparaturen**. Der dortige Assistent zeigt Zielrelease
und betroffene Receiver. Ältere Receiver werden nach Bestätigung auf die laufende
HA-Version gebracht; HA wird dabei weder aktualisiert noch neu gestartet.
Die Meldung bleibt über HA-Neustarts erhalten und verschwindet erst nach erfolgreicher
Prüfung. Für ältere Receiver mit kompatiblem Protokoll erscheint ein freiwilliges
**Receiver-Update verfügbar** unter Reparaturen. Über **Beheben** öffnest du den
Update-Assistenten. Die Verbindung bleibt nutzbar. Gleich alte oder neuere
kompatible Receiver erzeugen kein Updateangebot.
Veröffentlichte Versionen bis 1.0.2 verlangen selbst noch gleiche Releases; beide
Komponenten einmal aktualisieren, um die unabhängige Protokollprüfung zu verwenden.

Unter **Einstellungen → Geräte & Dienste → EnigmaHA Companion → Konfigurieren**
die **Sprache des Menüeditors** auf **Deutsch**, **English** oder
**Automatisch** (Standard bei neuen Installationen) stellen. Automatisch übernimmt die HA-Profilsprache, ersatzweise
die erste unterstützte Browsersprache. Regionale Varianten wie `en-GB` werden
erkannt; ohne passende Sprache wird Deutsch verwendet.
Die Auswahl gilt für alle Browser; ein geöffneter Editor übernimmt sie innerhalb
von 30 Sekunden und behält ungespeicherte Änderungen. Bis zum ersten Speichern
dieser Option bleibt bei bestehenden Installationen eine bisherige Browser-Sprachauswahl erhalten. Eine
Neueinrichtung ist nicht nötig. Menünamen bleiben unverändert. HA-eigene
Einrichtungsdialoge und die internen Texte nativer Auswahlfelder folgen der
Sprache im HA-Benutzerprofil.

Die Integrationsoptionen enthalten ausschließlich diese Sprachauswahl.
Schriftfamilie und Schriftgröße werden am jeweiligen Receiver eingestellt;
sie lassen sich in HA nicht auswählen.

1. Bei Bedarf Untermenüs anlegen und öffnen.
2. Im Entitätsfeld nach einer HA-Entität suchen, auswählen und hinzufügen.
   Die Filter für Entitätstyp, Bereich und Geräteklasse grenzen die Auswahl ein.
3. Anzeigenamen bearbeiten und die Reihenfolge mit dem Ziehgriff oder ↑/↓ ändern.
   Beim Ziehen an den Listenrand scrollt die Liste automatisch.
4. Menütitel direkt in der Menüübersicht bearbeiten. Schriftfamilie und
   Schriftgröße werden ausschließlich am jeweiligen Receiver eingestellt.
5. **Speichern** wählen.

Lampen, Schalter und `input_boolean` werden automatisch als schaltbar eingerichtet.
Andere Entitäten dienen der Anzeige. Der angemeldete Receiver-Benutzer benötigt
auch bei schaltbaren Einträgen die passenden HA-Berechtigungen.

Über **Menüs verwalten** können gemeinsame und persönliche Menüs angelegt werden.
**Freigabe** begrenzt ganze Menüs, Untermenüs und einzelne Einträge auf ausgewählte
HA-Benutzer. Maßgeblich ist der Benutzer des Receiver-Tokens. Die
[Anleitung für Benutzer-Menüs](Benutzermenues.md) erklärt Einrichtung, Vorschau
und die automatische Übernahme bestehender Menüs. Die Menüdatei
`.storage/enigmaha_companion.menu` wird von Home Assistant verwaltet und sollte
nicht bei laufendem HA manuell bearbeitet werden.

## Update-Anzeige in Home Assistant

Die Integration stellt die Update-Entität `update.enigmaha_companion` bereit.
Sie zeigt die tatsächlich laufende Integrationsversion, den neuesten vollständigen
stabilen Release und einen Link zu dessen Release-Informationen. Die Prüfung
erfolgt beim Laden der Integration und anschließend alle zwölf Stunden. Über
`homeassistant.update_entity` lässt sich die Prüfung auch manuell anfordern.
Die Anzeige benötigt Internetzugang zu GitHub, aber kein HACS. Bei einem
Prüffehler ist die Entität nicht verfügbar; das lokale Receiver-Menü bleibt nutzbar.
Ein späterer erfolgreicher Abruf stellt die Anzeige wieder her.

Über **Installieren** an dieser Entität oder `update.install` lässt sich das
HA-Update starten. Es aktualisiert ausschließlich Home Assistant; Receiver werden
nicht aufgenommen und müssen dafür nicht verbunden sein. Benötigt werden
Administratorrechte und eine aktive HACS-Update-Entität. Automationen
können den Dienst im Systemkontext aufrufen. Eine eigene Versionsauswahl und
die Backup-Option unterstützt diese Entität nicht.

HA wird über HACS auf den angebotenen Release aktualisiert. Fortschritt,
Wiederholung und den abschließenden HA-Neustart findest du im EnigmaHA-Editor.
Die Entität zeigt den laufenden Updatevorgang an und hält dessen Zielversion fest.
Wird zwischen Anzeige und Installation ein neuerer Release veröffentlicht,
musst du das aktualisierte Angebot erneut bestätigen. Bis zum HA-Neustart zeigt
sie weiterhin die geladene Version, auch wenn neuere Dateien bereits installiert
sind. Bestehende Konfigurationen und Updateaufträge benötigen keine Migration
oder Neueinrichtung. Die vorhandene HACS-Update-Entität bleibt separat bestehen.
Nach dem HA-Neustart werden ältere Receiver beim nächsten Kontakt erkannt.
Bei inkompatiblem Protokoll erscheint eine Fehler-Reparatur, bei kompatiblem
Protokoll ein freiwilliger Reparaturhinweis. HA-Benachrichtigungen unterstützen
keine frei belegbaren Aktionsbuttons; **Beheben** im Reparaturhinweis startet
deshalb den Assistenten. Dieser bietet den Release der laufenden HA-Version an,
ohne HACS zu benötigen. Öffne EnigmaHA Companion auf jedem beteiligten Receiver
und lasse es geöffnet. Nur bei geöffnetem Plugin wird der Updateauftrag
abgerufen; beim Fernsehen erscheint keine Installationsfrage. Bestätige im Plugin
die IPK-Installation und anschließend den GUI-Neustart.

Bei kompatiblem Protokoll bietet der Reparaturdialog außerdem **Für Version …
ignorieren** an. Damit schließt du die Reparatur ohne Receiver-Update ab. Die
Entscheidung bleibt nach einem HA-Neustart erhalten und gilt nur für die
angebotene HA-Version und die angezeigten Receiver-Versionen. Bei einem neuen
Versionsangebot erscheint der Hinweis erneut; inkompatible Protokolle bleiben
reparaturpflichtig. Ein bereits angebotener, noch nicht installierter Auftrag
wird beim Ignorieren beendet. Laufende oder unklare Installationen und ausstehende
GUI-Neustarts müssen zuerst geklärt bzw. abgeschlossen werden. Bestehende
Konfigurationen benötigen keine Migration oder Neueinrichtung.

## Update direkt bei einem Versionskonflikt

Meldet der Receiver einen Versions- oder Protokollkonflikt und läuft HA mit
einem neueren Release, bietet der Dialog **Receiver auf … aktualisieren** an.
Nach der Auswahl das geprüfte Paket und anschließend den GUI-Neustart bestätigen.
Der Receiver lädt genau den veröffentlichten stabilen Release der laufenden
HA-Integration und prüft Paket, Größe und SHA-256. Ist dieser Release nicht
vollständig verfügbar, erfolgt keine Installation. Downgrades bleiben gesperrt.

Ein bereits in HA angebotenes Update wird über den vorhandenen gemeinsamen
Ablauf fortgesetzt. Ohne solchen Auftrag wird nur der Receiver aktualisiert;
dafür sind GitHub-Zugang und Root-Rechte auf OpenATV erforderlich. Ein ausstehender
GUI-Neustart wird auch nach erneutem Öffnen des Plugins angeboten, wenn HA nicht
erreichbar ist. Das gilt auch für über HA gestartete Updates. Der Receiver prüft
dabei den lokalen Paketstatus und installiert das Paket nicht erneut. Sobald HA
wieder erreichbar ist, wird die tatsächlich laufende Version abgeglichen.
Bestehende Konfigurationen und Updatejournale bleiben nutzbar; eine Migration
oder Neueinrichtung ist nicht erforderlich.

## Gemeinsames Update über HACS und IPK

Beide Komponenten müssen einmal in einer Version installiert sein, die diesen
Updateablauf enthält. Ältere Installationen zuerst über HACS bzw. das IPK aus
demselben Release aktualisieren und HA sowie die Receiver-GUI neu starten.
Bei einer bisherigen ZIP-Installation zuerst EnigmaHA in HACS einrichten.

Voraussetzungen sind eine aktive HACS-Update-Entität für dieses Repository,
Internetzugang zu GitHub auf HA und den Receivern sowie Root-Rechte für `opkg`
auf OpenATV. Der Receiver benötigt weiterhin nur seinen normalen HA-Benutzertoken.
Die HTTPS-Zertifikatsprüfung bleibt aktiv. Zusätzliche SSH-Zugangsdaten sind nicht nötig.

1. Das Plugin auf allen beteiligten Receivern öffnen und bis zur
   Installationsbestätigung geöffnet lassen. Im HA-Editor erscheinen
   die Receiver-Anfragen der letzten fünf Minuten. Offline-Receiver werden nicht
   automatisch gesucht oder in ein Update aufgenommen.
2. Im HA-Editor **Auf Updates prüfen** wählen. Angeboten wird der neueste
   veröffentlichte stabile Release mit HACS-ZIP, IPK und `SHA256SUMS.txt`.
3. **Beide auf … aktualisieren** wählen und Zielversion sowie Receiverliste
   bestätigen. Die Auswahl gilt zehn Minuten. HACS installiert genau diese
   Version; Zielversion und beteiligte Receiver bleiben für diesen Vorgang fest.
4. Auf jedem Receiver die IPK-Installation bestätigen. Das Plugin lädt das
   passende Paket, prüft Größe, SHA-256-Prüfsumme, Paketname und Version und
   installiert es über `opkg`. Bis dahin wird nichts auf dem Receiver installiert.
5. Den anschließend angebotenen **GUI-Neustart** am Receiver bestätigen.
   Die native OpenATV-Neustartprüfung berücksichtigt laufende Aufnahmen.
   Nach dem Neustart meldet das Plugin seine tatsächlich geladene Version an HA.
6. Sobald alle beteiligten Receiver die Zielversion melden, im HA-Editor
   **Home Assistant neu starten** bestätigen. Ungespeicherte Menüänderungen
   vorher speichern. Danach die HA-Seite neu laden. Erst wenn auch HA mit
   der Zielversion läuft, erscheint der Vorgang als abgeschlossen.

Ein abgelehntes Receiver-Update kann im HA-Editor erneut angeboten werden und
erfordert erneut die lokale Bestätigung. Bei ungleichen Protokollen bleiben
Menüabruf und Schaltbefehle gesperrt; der Updatekanal funktioniert weiterhin.
HA speichert den Fortschritt unter `.storage/enigmaha_companion.update`, der
Receiver seine Kennung und sein Installationsjournal unter
`/etc/enigma2/enigmaha_companion_receiver_id` bzw.
`/etc/enigma2/enigmaha_companion_update.json`. Nicht manuell während eines Updates ändern.

Verbindungsabbrüche lösen keine zweite IPK-Installation aus. Bei unklarem
`opkg`-Ergebnis den Paketstatus am Receiver prüfen; eine Installation mit
unklarem Ausgang wird nicht automatisch wiederholt. Ein fehlender GUI-Neustart
wird erneut angeboten. Downgrades sind gesperrt. Während eines Vorgangs keine
andere Version über HACS oder `opkg` installieren. Nicht beteiligte Receiver
später aktualisieren; bei ungleichem Protokoll bleiben sie gesperrt.
Die manuelle Installation beider Pakete aus demselben Release bleibt möglich.

Der Repair-Assistent setzt offene Updateaufträge fort und bietet fehlgeschlagene
Schritte nach erneuter Bestätigung an. Bei unklarem Installationsergebnis fordert
er eine manuelle Prüfung. Den HA-Neustart separat bestätigen. Nach dem Update müssen
alle Beteiligten den Zielrelease mit dessen Protokoll melden, bevor die Reparatur
als abgeschlossen gilt. Die zusätzlichen Repair-Daten liegen getrennt vom Menü
unter `.storage/enigmaha_companion.repairs`.

## Langlebigen Zugriffstoken erstellen

Der Receiver meldet sich mit einem **langlebigen Zugriffstoken** bei Home Assistant
an. Er verwendet die Berechtigungen des Benutzers, der ihn erstellt.

1. Im Browser bei Home Assistant als der Benutzer anmelden, den der Receiver
   verwenden soll. Dieser benötigt Leserechte und zum Schalten auch Steuerungsrechte
   für die ausgewählten Entitäten.
2. Unten in der HA-Seitenleiste auf den **Benutzernamen bzw. das Profilbild** klicken.
3. Im Benutzerprofil den Reiter **Sicherheit** öffnen.
4. Zum Abschnitt **Langlebige Zugriffstoken** scrollen und **Token erstellen** wählen.
5. Einen erkennbaren Namen vergeben, z. B. **EnigmaHA Wohnzimmer**, und bestätigen.
6. Den angezeigten Token sofort vollständig kopieren und sicher aufbewahren.
   Nach dem Schließen des Dialogs lässt er sich nicht erneut anzeigen.
7. Den Token bei der [Receiver-Einrichtung](#4-receiver-einrichten) in das Feld
   **Token** eintragen oder über die [Konfigurationsdatei](#token-per-datei-eintragen)
   hinterlegen. Im HA-Menüeditor wird er nicht benötigt.

Falls du den Token nicht mehr hast, im selben Abschnitt einen neuen erstellen.
Zum Entziehen des Receiver-Zugriffs den zugehörigen Token dort löschen.
Siehe auch [HA-Benutzerprofil und Sicherheit](https://www.home-assistant.io/docs/authentication/)
und [HA-Zugriffstoken](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token).

## 3. Receiver-Plugin installieren

Das IPK `enigma2-plugin-extensions-enigmahacompanion_<Version>_all.ipk` aus
demselben Release wie die HA-Integration herunterladen. Für die Installation
stehen OpenWebif im Browser und SSH zur Auswahl.

<a id="ipk-ueber-openwebif"></a>

### IPK über OpenWebif installieren

1. Den eingeschalteten Receiver im Browser öffnen, z. B. unter
   `http://192.168.1.30`. Die eigene Receiver-Adresse verwenden und gegebenenfalls
   mit den eingerichteten OpenWebif-Zugangsdaten anmelden.
2. Falls noch nicht freigeschaltet: Am Receiver unter **Erweiterungen/Plugins →
   OpenWebif** die Einstellung **IPK Upload erlauben** aktivieren und speichern.
3. Im Browser die OpenWebif-Seite neu laden und **Pakete/Packages** öffnen.
   Je nach OpenWebif-Ansicht liegt der Eintrag unter **Extras**.
4. Die Uploadfunktion öffnen, das heruntergeladene EnigmaHA-IPK auswählen und hochladen.
5. Das hochgeladene Paket auswählen und **Installieren/Install** starten.
   Der Upload allein installiert das Plugin noch nicht.
6. Die erfolgreiche Installation abwarten. Bei einer Fehlermeldung zuerst deren
   Ursache beheben.
7. Über das Receiver-Menü die **Benutzeroberfläche/GUI neu starten** und unter
   **Erweiterungen/Plugins → EnigmaHA Companion** öffnen.

Falls deine OpenWebif-Version keine Uploadfunktion anbietet, den folgenden
SSH-Weg verwenden. Die Paketverwaltung und die Uploadfreigabe beschreibt auch
das [OpenATV-Handbuch](https://openatv.github.io/enigma2-doku/de/netzwerk/openwebif/werkzeuge/).

### IPK per SSH installieren

Das heruntergeladene IPK nach `/tmp` auf den Receiver kopieren.
Nur das gewünschte EnigmaHA-IPK dort ablegen und per SSH ausführen:

```sh
opkg install /tmp/enigma2-plugin-extensions-enigmahacompanion_*_all.ipk
```

Anschließend über das Receiver-Menü die **Benutzeroberfläche/GUI neu starten**.
Danach unter **Erweiterungen/Plugins → EnigmaHA Companion** öffnen.
Das Plugin erscheint auch im Erweiterungsmenü, sofern das Image dieses anzeigt.

Fehlende Abhängigkeiten aus dem Feed des jeweiligen Images installieren.
Das IPK benötigt `enigma2`, `python3-core (>= 3.13)`, `python3-json`,
`python3-netclient`, `python3-io` und `python3-twisted-core`.
Keine Abhängigkeiten mit `--force-depends` übergehen.

### Alternative: manuelles TAR-Paket

Wenn das Image keinen passenden IPK-Installationsweg bietet, auf dem Receiver
zunächst die benötigten Python-Module prüfen:

```sh
python3 -c "import json, ssl, urllib.request; from twisted.internet.threads import deferToThread"
```

Nach erfolgreicher Prüfung `enigmaha-companion-enigma2-<Version>.tar.gz` aus
dem Release nach `/tmp` kopieren. Im folgenden Befehl `<Version>` durch die
heruntergeladene Version ersetzen:

```sh
tar -xzf /tmp/enigmaha-companion-enigma2-<Version>.tar.gz -C /
```

Es enthält ausschließlich den Plugin-Ordner
`/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion/`.
Anschließend die GUI über das Receiver-Menü neu starten.

## 4. Receiver einrichten

Beim ersten Öffnen erscheinen die Einstellungen automatisch.
Später sind sie über **Menü/Blau** erreichbar.
Neue Installationen starten mit **Automatisch**. Bestehende Spracheinstellungen
bleiben erhalten; ältere Konfigurationsdateien ohne `language` verwenden weiter Deutsch.

| Einstellung | Bedeutung |
| --- | --- |
| Sprache | **Deutsch**, **English** oder **Automatisch** (Standard bei neuen Installationen, OpenATV-Systemsprache); wirksam beim nächsten Öffnen des Plugins |
| Home-Assistant-Adresse | Zum Beispiel `http://192.168.1.20:8123` oder deine HTTPS-Adresse; kein `/api` und keinen Unterpfad anfügen |
| Token | Vollständiger langlebiger HA-Zugriffstoken |
| Aktualisierung | Abrufintervall bei geöffnetem Plugin; Standard 10 Sekunden |
| Skin-Profil | **Automatisch**, **Standard (aktiver Skin)** oder **GradientFHD**; Standard automatisch |
| Schriftfamilie | Auf dem Receiver registrierte Schrift oder **Auto (Skin-/Receiver-Standard)** |
| Schriftgröße | Lokaler Wert von 16 bis 64 oder **Auto (Skin-/Receiver-Standard)** |
| Verbindungszeitlimit | Standard 5 Sekunden |
| Im Hauptmenü anzeigen | Direkter Einstieg im Enigma2-Hauptmenü; Standard aus |
| Ch+/− umkehren | Richtung des seitenweisen Blätterns tauschen; Standard aus |
| Menüposition beim Beenden merken | Letzte Menübene und Auswahl beim nächsten Öffnen wiederherstellen; Standard ein |

**Grün** speichert. **OK/Gelb** öffnet bei Textfeldern die Bildschirmtastatur
und bei Schriftfeldern sowie dem Skin-Profil die Auswahlliste. **Links/Rechts** wechselt Auswahlwerte.
Der Hauptmenüeintrag erscheint nach dem Speichern beim nächsten Öffnen des
Enigma2-Hauptmenüs.

Das Skin-Profil wird beim nächsten Öffnen des Plugins wirksam. **Automatisch**
erkennt den aktiven Skin und verwendet bei unbekannten Skins das Standardprofil.
Eine manuelle Auswahl überschreibt die Erkennung und etwaige vom Skin bereitgestellte
Plugin-Screens. Sie ändert nur die Plugin-Darstellung. Keine Neueinrichtung nötig.

### Schriftfamilie und Schriftgröße

Im Receiver-Plugin **Menü/Blau** drücken und **Schriftfamilie** beziehungsweise
**Schriftgröße** auswählen. Mit **Grün** speichern. Die Auswahl gilt für alle
Menüs auf diesem Receiver; andere Receiver behalten ihre eigenen Einstellungen.

| Einstellung | Auswahl | Verhalten |
| --- | --- | --- |
| Schriftfamilie | **Auto (Skin-/Receiver-Standard)** | Schrift des Skins beziehungsweise Receiver-Profils verwenden |
| Schriftfamilie | Registrierte Schrift | Diese Schrift anstelle der Skin-/Receiver-Vorgabe verwenden; fehlt sie, auf `Regular` zurückfallen |
| Schriftgröße | **Auto (Skin-/Receiver-Standard)** | Größe des Skins beziehungsweise Receiver-Profils verwenden |
| Schriftgröße | Zahlenwert von 16 bis 64 | Skin-/Receiver-Vorgabe ignorieren und die gewählte Größe verwenden |

Beide Einstellungen wirken unabhängig: Du kannst beispielsweise die Schriftfamilie
auf **Auto** lassen und nur die Größe festlegen. Feste Werte haben in allen
Profilen Vorrang, auch bei GradientFHD. Die bisherige Auflösungsskalierung fester
Größen bleibt erhalten: Die Werte beziehen sich auf 1280 × 720; bei Full HD
entspricht beispielsweise `32` einer Schriftgröße von 48 Pixeln. Die Zeilenhöhe
passt sich an die verwendete Größe an.

### Bisherige Schrifteinstellungen

Vorhandene lokale Schriftwerte bleiben erhalten. Die bisherige Auswahl
**Aus HA übernehmen** wird als **Auto (Skin-/Receiver-Standard)** angezeigt und
verwendet jetzt die Skin-/Receiver-Vorgabe. Gespeichert bleiben dafür die leere
Schriftfamilie und die Größe `0`.

Bisherige HA-Schriftwerte bleiben für ältere Receiver gespeichert; aktualisierte
Receiver verwenden sie nicht mehr. Falls du die bisher in HA gewählte Schrift
weiterverwenden möchtest, wähle sie am jeweiligen Receiver. Eine automatische
Übernahme aus HA erfolgt nicht. Menüs, Freigaben und Verbindungsdaten bleiben
erhalten; eine Migration oder Neueinrichtung ist nicht erforderlich.

### Token per Datei eintragen

Für einen langen Token kannst du einen Dateieditor oder SFTP verwenden.
Das Plugin beim Bearbeiten schließen. Die Datei liegt unter
`/etc/enigma2/enigmaha_companion.json`:

```json
{
  "url": "http://192.168.1.20:8123",
  "token": "HIER_DEN_EIGENEN_TOKEN_EINTRAGEN",
  "refresh_seconds": 10,
  "language": "auto",
  "skin_profile": "auto",
  "font_family": "",
  "font_size": 0,
  "timeout": 5,
  "show_in_mainmenu": false,
  "reverse_channel_paging": false,
  "remember_menu_position": true
}
```

Leere Schriftfamilie und Schriftgröße `0` bedeuten **Auto (Skin-/Receiver-Standard)**.
`language` akzeptiert `de` (Deutsch), `en` (English) und `auto`
(Standard bei neuen Installationen, OpenATV-Systemsprache; Deutsch als Rückfall
für nicht unterstützte Sprachen). Fehlt der Wert in einer vorhandenen Datei,
bleibt Deutsch aktiv. Es ist keine Migration oder Neueinrichtung nötig.
`skin_profile` akzeptiert `auto`, `native` (Standard) und `gradient` (GradientFHD).
Bei manueller Anlage mit `chmod 600 /etc/enigma2/enigmaha_companion.json` die
Dateirechte setzen. Das Plugin speichert die Datei selbst mit diesen Rechten.

Den Token nicht in Logs, Screenshots oder das Repository übernehmen. Bei Eingabe
über die Bildschirmtastatur ist der Text auf dem Fernseher sichtbar.
HTTPS prüft Zertifikate; die Prüfung lässt sich nicht abschalten.
HTTP überträgt auch den Token unverschlüsselt.

## Fernbedienung im Menü

| Taste | Funktion |
| --- | --- |
| Auf / Ab | Vorherigen / nächsten Eintrag wählen |
| Links / Rechts | Eine Seite nach oben / unten blättern |
| Recall | Eine Menübene zurück; auf oberster Ebene ohne Funktion |
| OK / Grün | Untermenü öffnen oder Licht/Schalter umschalten |
| Menü / Blau | Einstellungen öffnen |
| Gelb | Menü und Zustände neu laden |
| Kanal + / − | Eine Seite nach oben / unten; über **Ch+/− umkehren** umkehrbar |
| Rot / Exit | Menü aus jeder Ebene komplett schließen |
| Info | Version auf dem Receiver, Version in Home Assistant, angemeldeter Benutzer und Anzahl sichtbarer Menüs, Untermenüs und Entitäten |
| Hilfe | Tastenübersicht mit der eingestellten Kanal-Tastenrichtung anzeigen |

Ein-/Aus-Zustände erscheinen mit HA-Entitätssymbolen: Ein gelb, Aus grau.
Kann ein Symbol nicht dargestellt werden, bleibt der Zustand als Text sichtbar.
Sensorwerte werden mit ihrer Einheit angezeigt. Dimmen, Szenen und Scripts
werden nicht unterstützt.

Bei einem Verbindungsfehler bleibt die letzte Anzeige als **OFFLINE** sichtbar.
Schalten ist bis zum erfolgreichen Abruf gesperrt. Ein Schaltbefehl wird niemals
automatisch wiederholt, auch wenn seine Antwort verloren ging.

<a id="openatv-hotkeys"></a>

## Schalten über OpenATV-Hotkeys

Unter **Einstellungen → Bedienung → Hotkeys → Plugins** werden automatisch alle
schaltbaren Einträge aus den für den angemeldeten HA-Benutzer freigegebenen Menüs
angeboten, zum Beispiel **EnigmaHA: Zuhause > Wohnzimmer > Stehlampe – Umschalten**.
Der vollständige Menüpfad zeigt die Herkunft des Eintrags. Eine Entität in mehreren
Menüs wird für jeden Menüeintrag angeboten. Sensoren und Einträge ohne
Steuerungsberechtigung erscheinen nicht.

Die gewünschte Taste und anschließend den Eintrag auswählen und speichern.
Das funktioniert mit den von OpenATV angebotenen Tasten, einschließlich F1–F4
und, soweit unterstützt, kurzem und langem Tastendruck. Beim Fernsehen schaltet
die Taste direkt, ohne das Companion-Menü zu öffnen. In anderen Bildschirmen
gelten deren eigene Tastenbelegungen.

Die Liste wird beim Öffnen der Hotkey-Einstellungen einmal von Home Assistant
geladen. Es gibt keine regelmäßige Hintergrundabfrage. Nach Menüänderungen die
Hotkey-Einstellungen erneut öffnen. Die zuletzt geladene Liste wird lokal unter
`/etc/enigma2/enigmaha_companion_hotkeys.json` gespeichert, damit bestehende
Tastenbelegungen nach einem GUI-Neustart sofort verfügbar sind. Die Datei ist an
HA-Adresse und Token gebunden, enthält aber keine Zugangsdaten. Nach einem
Tokenwechsel die Hotkey-Einstellungen einmal öffnen. Vor jedem Schaltbefehl
werden der aktuelle Menüeintrag und die HA-Berechtigungen geprüft. Bei
Verbindungsproblemen erscheint eine Fehlermeldung; Schaltbefehle werden nicht
automatisch wiederholt.

Umbenennen, Verschieben und Umsortieren eines vorhandenen Eintrags erhalten seine
Tastenbelegung. Entfernte, nicht mehr freigegebene oder auf eine andere Entität
geänderte Einträge schalten nicht mehr. Für ersetzte Einträge oder eine geänderte
HA-Adresse die Taste erneut zuordnen. Bestehende Einstellungen und
OpenATV-Tastenbelegungen bleiben erhalten; eine Migration ist nicht erforderlich.

<a id="funktionspruefung"></a>

## Funktionsprüfung

1. In HA ein Untermenü „Test“ mit einer Lampe und einem Sensor speichern.
2. Plugin öffnen: „Test“ mit OK öffnen, beide Zustände prüfen.
3. Lampe mit OK umschalten und den erneut abgerufenen Zustand prüfen.
4. Sensor mit OK wählen: Es darf kein Schaltbefehl ausgelöst werden.
5. Mit Recall zurück, mit Rot oder Exit aus jeder Ebene schließen.
6. Im HA-Menüeditor einen Eintrag umbenennen, speichern und am Receiver Gelb drücken.
7. Beide Sprachen im Editor und am Receiver einschließlich Hilfe und Fehlermeldungen
   prüfen. Eigene Namen müssen unverändert bleiben.

## Aktualisieren

Für die Zweisprachigkeit ist keine Neueinrichtung erforderlich. Ohne Sprachauswahl
starten Menüeditor und Receiver auf Deutsch. Menüs und Zugangsdaten bleiben erhalten.

Die HA-Integration über HACS oder das manuelle ZIP aktualisieren und HA neu
starten. Das Receiver-Paket aus demselben Release installieren und die
Receiver-GUI neu starten. Hinweise zu Migrationen und gegebenenfalls erforderlicher
Neueinrichtung stehen in den Release-Informationen. Vor Änderungen die Konfiguration sichern.

## Fehlerbehebung und Entfernung

- **Integration nicht auffindbar:** Ordnerstruktur prüfen, HA neu starten, Browser neu laden.
- **Token abgelehnt:** Token, aktiven Benutzer und Rechte prüfen.
- **HTTP 404:** Installation der HA-Komponente und die verwendete HA-Adresse prüfen.
- **HTTP 503:** Prüfen, ob die Integration unter Geräte & Dienste eingerichtet und geladen ist.
- **Schrift fehlt:** `Regular` oder eine auf dem Receiver registrierte Schrift wählen.
- **Plugin fehlt im Menü:** Python-Version und Abhängigkeiten prüfen; Enigma2-Startlog
  auf Importfehler prüfen. Keine Tokens mitsenden.
- **IPK entfernen:** `opkg remove enigma2-plugin-extensions-enigmahacompanion`,
  danach GUI neu starten.
- **Manuelle Receiver-Installation entfernen:** Nur den oben genannten Plugin-Ordner
  entfernen. Die private Konfiguration bleibt separat bestehen.
- **HA entfernen:** Integration unter Geräte & Dienste entfernen, bei Bedarf den
  Custom-Component-Ordner entfernen und HA neu starten. Die gespeicherte Menüdatei
  bleibt beim Entfernen der Integration erhalten.
