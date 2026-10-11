# EnigmaHA Companion entwickeln

**Deutsch** · [English](Development.en.md)

EnigmaHA Companion besteht aus einer Home-Assistant-Integration mit Menüeditor
und einer Enigma2-Extension. Die Integration speichert das gemeinsame Menü und
stellt Zustände und Schaltaktionen über authentifizierte HTTP-Routen bereit.
Der Receiver ruft diese Daten ab und zeigt sie als fernbedienbares Menü an.

Entwicklung und Receiver-Tests erfolgen ausschließlich für und auf **OpenATV**.

Die [Installationsanleitung](Installation.md) beschreibt die Einrichtung,
das [Protokoll](Protokoll-v1.md) die Datenformate und HTTP-Routen und
die [Release-Anleitung](Releases.md) Paketierung und Veröffentlichung.

## Projektstruktur

| Pfad | Aufgabe |
| --- | --- |
| `custom_components/enigmaha_companion/` | HA-Integration, HTTP-API, Symbolauflösung und Menüeditor |
| `enigma2/Plugins/Extensions/EnigmaHACompanion/` | Enigma2-Screen, Einstellungen, Layout und Symbolanzeige |
| `enigma2/companion/` | GUI-unabhängige Navigation und synchroner HTTP-Client |
| `protocol/enigmaha_protocol/` | Gemeinsame Menüvalidierung und Befehlsprüfung |
| `protocol/*.example.json` | Beispielmenü und Zustandsantwort |
| `tests/` | Python- und Frontendtests |
| `tools/build.py` | Vollständige HA- und Receiver-Pakete erzeugen |
| `.github/workflows/release.yml` | Build, Tests und Veröffentlichung über GitHub Actions |

## Lokal bauen und testen

Die Release-CI verwendet Python 3.13 und Node.js 24. Der ausgelieferte Receiver-Code
muss Python-3.13-kompatible Syntax verwenden; Python 3.13 ist die Mindestversion
auf dem Receiver. Der Paketbau benötigt nur die
Python-Standardbibliothek; für die Tests kommen aiohttp sowie die npm-Abhängigkeiten
aus `package-lock.json` hinzu.

Im Projektstamm ausführen:

```console
python -m pip install -r requirements-test.txt
npm ci
python tools/build.py
python -m unittest discover -s tests -v
npm test
```

Der Build muss vor den Pakettests laufen. Er erzeugt unter `dist/` die beiden
HA-ZIPs, das Receiver-IPK, ein alternatives TAR-Paket, Prüfsummen und die entpackten
Paketbäume unter `dist/unpacked/`. Für lokale Installationen diese Pakete verwenden:
Die Quellordner allein enthalten noch nicht die eingebundenen gemeinsamen Module.

Optional dürfen die Frontend-Abhängigkeiten unter `.work/node_modules/` liegen.
Dazu `package.json` und `package-lock.json` nach `.work/` kopieren und
`npm ci --prefix .work --ignore-scripts` ausführen. Bei geänderten Abhängigkeiten
die Kopien erneuern. `npm test` bevorzugt `node_modules/` im Projektstamm und
verwendet andernfalls `.work/node_modules/`.

## Entwicklungsregeln

Die [Projektregeln](../AGENTS.md) gelten für alle Änderungen. Das Projekt befindet
sich in aktiver Entwicklung; Rückwärtskompatibilität zu früheren Projektständen
ist nicht erforderlich. APIs, Menüformat, Speicherformate und interne
Schnittstellen dürfen geändert werden. Keine Legacy-Adapter, Migrationen oder
parallelen Implementierungen allein für alte Entwicklungsstände vorsehen.

Eine erforderliche Neueinrichtung kurz dokumentieren und gespeicherte Nutzerdaten
nicht ungefragt löschen. Die Unterstützung der Zielsysteme OpenATV und
Home Assistant bleibt davon unberührt. Zugangsdaten, `.work/` und `.temp/` nicht
committen. Vor Übergabe die zur Änderung passenden Tests ausführen.

## Home-Assistant-Integration

Die Domain lautet `enigmaha_companion`. Ein einzelner Konfigurationseintrag
verwaltet das Menü für alle Receiver. Home Assistants `Store` speichert es unter
`.storage/enigmaha_companion.menu`. Die laufende Integration lädt und validiert
das Menü; Speichern erhöht dessen Revision dauerhaft.

Die API trennt Receiver-Zugriff und Administration. Menü und Zustände werden
anhand der Leseberechtigungen des angemeldeten Benutzers gefiltert. Fehlende
Steuerungsrechte entfernen die Aktionen eines Menüeintrags. Jeder Schaltbefehl
wird zusätzlich serverseitig auf Revision, Eintrag, erlaubte Aktion, aktuellen
Zustand und Berechtigungen geprüft und mit HA-Benutzerkontext ausgeführt.
Menüänderungen und Aktionen teilen sich eine Sperre. Eine fehlgeschlagene
Speicherung verändert weder das laufende Menü noch seine Revision.

Der Menüeditor und GET/PUT `/config` sind Administratoren vorbehalten.
Receiver-Zugangsdaten werden nicht im Editor gespeichert.

### Übersetzungen

Deutsch ist Standard und erste Auswahl. Der Menüeditor enthält sein englisches
Wörterbuch in `panel.js`; `t()` übersetzt deutsche Quelltexte und setzt benannte
Platzhalter ein. Die Sprachauswahl wird unter `enigmaha_companion.language` im
Browser gespeichert. Der Wechsel erhält Menüentwurf, Navigation und Filter.
HA-Konfigurationsdialoge verwenden `translations/de.json` und `translations/en.json`
und folgen der HA-Profilsprache; beide Kataloge liegen auch im Quellbaum.

Der Receiver nutzt `companion/i18n.py` und die lokale Einstellung `language`
(`de` oder `en`, Standard `de`). Navigation, Hilfe, Einstellungen und eingebaute
Skin-Texte werden damit übersetzt. Ein Wechsel gilt ab dem nächsten Öffnen,
damit auch die Skin-Tastenleiste dieselbe Sprache verwendet. Eigene Labels,
Entity-IDs, Rohzustände und Protokoll-Fehlercodes bleiben unverändert.
Neue Oberflächentexte in den passenden Katalog aufnehmen und Platzhalter in
beiden Sprachen beibehalten. Spracheinstellungen benötigen keine Neueinrichtung.

### Menüeditor

Für die Entitätsauswahl native `ha-selector`-Komponenten verwenden. Die Filter
für Domain, Bereich und Geräteklasse sind kombinierbar. Der Bereich einer Entität
hat Vorrang vor dem Bereich ihres Geräts. Vor dem Hinzufügen muss die Entität
existieren und zu den Filtern passen; Filter verändern keine gespeicherten Einträge.

Der Editor verwendet HA-Komponenten für Karten, Eingaben, Schaltflächen,
Zustandssymbole, Auswahlfelder und Sortierung. `ha-sortable` sortiert innerhalb
des geöffneten Untermenüs; Auf-/Ab-Pfeile bieten dieselbe Funktion. Beim Ziehen
scrollt die Eintragsliste am Rand automatisch. Auf breiten Bildschirmen haben
Einträge und Einstellungen getrennte Scrollbereiche, auf schmalen eine gemeinsame
Ansicht. Eingabefokus und Scrollpositionen sollen bei Aktualisierungen erhalten bleiben.

Das Modell übernimmt eine Sortierung erst nach dem Ablegen. Neue Einträge werden
sichtbar gemacht und unter Beachtung reduzierter Bewegung hervorgehoben.
Bestätigungsdialoge schützen ungespeicherte Änderungen und gefüllte Untermenüs;
Abbrechen, Escape und Schließen verwerfen die angefragte Aktion.

Beim Hinzufügen und Speichern leitet der Editor `toggle` automatisch für `light`,
`switch` und `input_boolean` ab. Andere Domains bleiben lesend. Die serverseitige
HA-Berechtigungsprüfung entscheidet weiterhin über jede Receiver-Aktion.

### Entitätssymbole

`icons.py` berücksichtigt Registry-Icons, das Zustandsattribut `icon`,
Integrations-Icons und Domain-/Geräteklassensymbole aus HA. Die MDI-Pfade stammen
aus `hass_frontend.where()/static/mdi/*.json`; `iconMetadata.json` ordnet Namen
den Dateien zu. Dateizugriffe laufen im HA-Executor, höchstens vier Grafikblöcke
bleiben im Cache. Nach einem Frontendupdate HA neu starten, um den Cache zu erneuern.

Ein zusätzlicher MDI-Katalog, Netzwerkabfragen oder ein geöffneter Browser sind
nicht erforderlich. Browserseitige Custom-Icon-Provider werden nicht ausgeführt;
dafür wird ein MDI-Standardsymbol verwendet. Bei fehlenden oder defekten Grafikdateien
bleibt die Zustandsanzeige als Text erhalten.

Die API überträgt ausschließlich geprüfte SVG-Pfadgeometrie für `on`/`off`.
Der Receiver validiert diese erneut, erzeugt SVGs in einem privaten temporären
Verzeichnis und lädt sie über Enigma2s `LoadPixmap`. Die Dateien werden direkt
nach dem Laden entfernt; bis zu 128 Pixmaps bleiben pro offenem Screen im Cache.
Ein ist gelb, Aus grau. Ist kein Bild darstellbar, erscheint der Zustand als Text.

## Enigma2-Extension

Der synchrone HTTP-Client läuft über Twisted `deferToThread` außerhalb des
GUI-Threads. Anzeigeänderungen erfolgen in den Rückrufen. Während eines Abrufs
oder Befehls sind weitere Schaltaktionen gesperrt. Alte Antworten werden nach
Schließen oder Verbindungswechsel verworfen. Die periodische Aktualisierung
läuft nur bei geöffnetem Plugin.

Bei Verbindungsfehlern bleibt die letzte Anzeige als OFFLINE stehen. Ein
Toggle-Befehl wird auch bei verlorener Antwort niemals automatisch wiederholt.
HTTPS verwendet die Zertifikatsprüfung des Systems; Redirects werden abgewiesen.

Die lokale Konfiguration liegt unter `/etc/enigma2/enigmaha_companion.json`
außerhalb des Plugin-Ordners und wird mit Dateirechten `0600` gespeichert.
Layout, Schriftprioritäten, Skin-Schnittstellen und Tastenbelegung sind in der
[Enigma2-Dokumentation](../enigma2/README.md) beschrieben.
Weitere Skin-Profile werden unter `skin/<Skinname>/` implementiert und einmal in
`skin/__init__.py` in `PROFILES` registriert. Die gemeinsame Schnittstelle liegt
in `skin/base.py`. Erkennung, manuelle Auswahl und Konfigurationsprüfung verwenden diese
gemeinsame Liste; das gemeinsame Layout bleibt in `appearance.py`.

## Teststand und Grenzen

Die Updatekoordination liegt in `updates.py`, die portable Releaseprüfung in
`protocol/enigmaha_protocol/releases.py` und die OpenATV-Installation in
`enigma2/companion/updater.py`. Verwendet werden die öffentliche
[HACS-Update-Entität](https://github.com/hacs/integration/blob/main/custom_components/hacs/update.py)
und OpenATVs [`opkg`](https://github.com/openatv/enigma2/blob/master/lib/python/Components/Opkg.py)
sowie [`TryQuitMainloop`](https://github.com/openatv/enigma2/blob/master/lib/python/Screens/Standby.py).
Die bestehenden Python-Paketabhängigkeiten decken auch Hashing, UUID und
Prozessaufrufe ab; `python3-netclient` zieht `python3-crypt` nach.

Update-Tests prüfen feste HACS-Zielversionen, Benutzer-/Receiverbindung,
Bestätigungen, Ablehnung, Prüfsummen und Paketmetadaten, verlorene Antworten,
Speicherfehler, unterbrochene Installationen und Abschluss erst nach tatsächlich
laufender Zielversion auf beiden Seiten. HACS-Dienste und `opkg` werden dabei
ersetzt; ein kompletter HACS/IPK-Updatezyklus auf HA und OpenATV-Hardware steht
noch aus. Vor Freigabe einschließlich GUI-Neustart bei laufender Aufnahme prüfen.

Die automatisierten Tests decken Menüvalidierung, Befehle, echte HTTP-Anfragen
gegen Testserver, HA-Lebenszyklus und Berechtigungen, Symbolauflösung,
Receiver-Navigation, Layouts sowie Inhalt und Metadaten der Pakete ab.
HA-Dienste und Enigma2-Gerätefunktionen werden dabei durch Testobjekte ersetzt.
Die Receiver-Pakete werden auch auf Python-3.13-kompatible Syntax geprüft.
Sprachtests prüfen Deutsch als Standard, englische Texte, Platzhalter, gespeicherte
Sprachauswahl und unveränderte Menüentwürfe beim Wechsel.
Die Skin-Profiltests prüfen automatische und manuelle Auswahl, Speicherung und
Abbrechen, Übernahme beim erneuten Öffnen sowie fehlende Skin-Ressourcen.

Die Frontendtests verwenden jsdom und ersetzen native HA-Komponenten durch
Custom-Element-Testobjekte. Sie prüfen Filter, Modelländerungen, Sortierereignisse,
Scrollaufrufe und Dialogaktionen. Sie ersetzen keine Browserprüfung von Darstellung,
Gesten und modaler Fokusführung.

Vor einer Veröffentlichung die Schritte im Abschnitt „Funktionsprüfung“ der
[Installationsanleitung](Installation.md) auf den OpenATV-Zielreceivern mit
Home Assistant durchführen.

## Eigene HA-Testinstanz

Mit Docker und Compose startet `python tools/ha_dev.py start` eine separate
HA-Instanz unter **http://127.0.0.1:18123**. Der Befehl baut und installiert das
vollständige Entwicklungspaket, erledigt das HA-Onboarding und richtet die
Integration samt Testmenü automatisch ein. Frische Labore verwenden den
Testzugang `enigma2ha:notsecret`. Benutzer, Menü und Datenbank bleiben in einem
eigenen Docker-Volume erhalten. Virtuelle Testentitäten benötigen keine Geräte
oder Zugangsdaten aus der produktiven Installation.

`python tools/ha_dev.py check` prüft die Konfiguration, `logs` zeigt Protokolle,
`stop` beendet den Container und erhält seine Daten. Einrichtung und Grenzen:
[Docker-Testumgebung](../dev/ha/README.md). Für HA-Core-Entwicklung selbst ist die
[offizielle Devcontainer-Umgebung](https://developers.home-assistant.io/docs/development_environment/)
geeignet; für diese Custom Integration genügt der kleinere HA-Container.
