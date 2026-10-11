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
und betroffene Receiver und verwendet nach Bestätigung denselben HACS/IPK-Ablauf.
Die Meldung bleibt über HA-Neustarts erhalten und verschwindet erst nach erfolgreicher
Prüfung. Reine Release-Unterschiede erzeugen keine Reparatur und erfordern kein Update.
Veröffentlichte Versionen bis 1.0.2 verlangen selbst noch gleiche Releases; beide
Komponenten einmal aktualisieren, um die unabhängige Protokollprüfung zu verwenden.

Unter **Sprache** zwischen **Deutsch** (Standard) und **English** wechseln.
Die Auswahl gilt für diesen Browser und ändert keine Menünamen. HA-eigene
Einrichtungsdialoge und die internen Texte nativer Auswahlfelder folgen der
Sprache im HA-Benutzerprofil.

1. Bei Bedarf Untermenüs anlegen und öffnen.
2. Im Entitätsfeld nach einer HA-Entität suchen, auswählen und hinzufügen.
   Die Filter für Entitätstyp, Bereich und Geräteklasse grenzen die Auswahl ein.
3. Anzeigenamen bearbeiten und die Reihenfolge mit dem Ziehgriff oder ↑/↓ ändern.
   Beim Ziehen an den Listenrand scrollt die Liste automatisch.
4. Unter **Darstellung auf dem Receiver** Schriftfamilie und Schriftgröße wählen.
5. **Speichern** wählen.

Lampen, Schalter und `input_boolean` werden automatisch als schaltbar eingerichtet.
Andere Entitäten dienen der Anzeige. Der angemeldete Receiver-Benutzer benötigt
auch bei schaltbaren Einträgen die passenden HA-Berechtigungen.

Alle Receiver verwenden dasselbe Menü. Die Menüdatei
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

Installationen werden weiterhin im EnigmaHA-Editor oder Reparaturassistenten
bestätigt. Die neue Entität bietet keine Installation an. Bis zum HA-Neustart
zeigt sie weiterhin die geladene Version, auch wenn neuere Dateien bereits
installiert sind. Bestehende Konfigurationen benötigen keine Migration oder
Neueinrichtung; die Entität wird nach dem Aktualisieren und Neustarten von HA
automatisch hinzugefügt. Eine vorhandene HACS-Update-Entität bleibt separat bestehen.

## Gemeinsames Update über HACS und IPK

Beide Komponenten müssen einmal in einer Version installiert sein, die diesen
Updateablauf enthält. Ältere Installationen zuerst über HACS bzw. das IPK aus
demselben Release aktualisieren und HA sowie die Receiver-GUI neu starten.
Bei einer bisherigen ZIP-Installation zuerst EnigmaHA in HACS einrichten.

Voraussetzungen sind eine aktive HACS-Update-Entität für dieses Repository,
Internetzugang zu GitHub auf HA und den Receivern sowie Root-Rechte für `opkg`
auf OpenATV. Der Receiver benötigt weiterhin nur seinen normalen HA-Benutzertoken.
Die HTTPS-Zertifikatsprüfung bleibt aktiv. Zusätzliche SSH-Zugangsdaten sind nicht nötig.

1. Das Plugin auf allen beteiligten Receivern öffnen. Im HA-Editor erscheinen
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

| Einstellung | Bedeutung |
| --- | --- |
| Sprache | **Deutsch** (Standard) oder **English**; wirksam beim nächsten Öffnen des Plugins |
| Home-Assistant-Adresse | Zum Beispiel `http://192.168.1.20:8123` oder deine HTTPS-Adresse; kein `/api` und keinen Unterpfad anfügen |
| Token | Vollständiger langlebiger HA-Zugriffstoken |
| Aktualisierung | Abrufintervall bei geöffnetem Plugin; Standard 10 Sekunden |
| Skin-Profil | **Automatisch**, **Standard (aktiver Skin)** oder **GradientFHD**; Standard automatisch |
| Schriftfamilie | Auf dem Receiver registrierte Schrift oder **Aus HA übernehmen** |
| Schriftgröße | Lokaler Wert von 16 bis 64 oder **Aus HA übernehmen** |
| Verbindungszeitlimit | Standard 5 Sekunden |
| Im Hauptmenü anzeigen | Direkter Einstieg im Enigma2-Hauptmenü; Standard aus |
| Ch+/− umkehren | Richtung des seitenweisen Blätterns tauschen; Standard aus |

**Grün** speichert. **OK/Gelb** öffnet bei Textfeldern die Bildschirmtastatur
und bei Schriftfeldern sowie dem Skin-Profil die Auswahlliste. **Links/Rechts** wechselt Auswahlwerte.
Der Hauptmenüeintrag erscheint nach dem Speichern beim nächsten Öffnen des
Enigma2-Hauptmenüs.

Das Skin-Profil wird beim nächsten Öffnen des Plugins wirksam. **Automatisch**
erkennt den aktiven Skin und verwendet bei unbekannten Skins das Standardprofil.
Eine manuelle Auswahl überschreibt die Erkennung und etwaige vom Skin bereitgestellte
Plugin-Screens. Sie ändert nur die Plugin-Darstellung. Keine Neueinrichtung nötig.

Im Standardprofil überschreiben lokale Schriftoptionen die HA-Vorgaben. Bei einem
automatisch oder manuell gewählten Profil wie GradientFHD hat dessen Schrift Vorrang. Eine fehlende Schrift
wird durch `Regular` ersetzt.

### Token per Datei eintragen

Für einen langen Token kannst du einen Dateieditor oder SFTP verwenden.
Das Plugin beim Bearbeiten schließen. Die Datei liegt unter
`/etc/enigma2/enigmaha_companion.json`:

```json
{
  "url": "http://192.168.1.20:8123",
  "token": "HIER_DEN_EIGENEN_TOKEN_EINTRAGEN",
  "refresh_seconds": 10,
  "language": "de",
  "skin_profile": "auto",
  "font_family": "",
  "font_size": 0,
  "timeout": 5,
  "show_in_mainmenu": false,
  "reverse_channel_paging": false
}
```

Leere Schriftfamilie und Schriftgröße `0` bedeuten **Aus HA übernehmen**.
`language` akzeptiert `de` (Deutsch, Standard) und `en` (English).
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
| Rechts | Ausgewähltes Untermenü öffnen |
| Links / Exit | Übergeordnetes Menü; auf oberster Ebene Plugin schließen |
| OK / Grün | Untermenü öffnen oder Licht/Schalter umschalten |
| Menü / Blau | Einstellungen öffnen |
| Gelb | Menü und Zustände neu laden |
| Kanal + / − | Eine Seite nach oben / unten; über **Ch+/− umkehren** umkehrbar |
| Rot | Plugin sofort schließen |
| Hilfe | Tastenübersicht mit der eingestellten Kanal-Tastenrichtung anzeigen |

Ein-/Aus-Zustände erscheinen mit HA-Entitätssymbolen: Ein gelb, Aus grau.
Kann ein Symbol nicht dargestellt werden, bleibt der Zustand als Text sichtbar.
Sensorwerte werden mit ihrer Einheit angezeigt. Dimmen, Szenen und Scripts
werden nicht unterstützt.

Bei einem Verbindungsfehler bleibt die letzte Anzeige als **OFFLINE** sichtbar.
Schalten ist bis zum erfolgreichen Abruf gesperrt. Ein Schaltbefehl wird niemals
automatisch wiederholt, auch wenn seine Antwort verloren ging.

<a id="funktionspruefung"></a>

## Funktionsprüfung

1. In HA ein Untermenü „Test“ mit einer Lampe und einem Sensor speichern.
2. Plugin öffnen: „Test“ mit Rechts öffnen, beide Zustände prüfen.
3. Lampe mit OK umschalten und den erneut abgerufenen Zustand prüfen.
4. Sensor mit OK wählen: Es darf kein Schaltbefehl ausgelöst werden.
5. Mit Links zurück, mit Exit auf oberster Ebene schließen.
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
