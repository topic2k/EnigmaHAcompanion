# EnigmaHA Companion entwickeln

**Deutsch** · [English](Development.en.md)

EnigmaHA Companion besteht aus einer Home-Assistant-Integration mit Menüeditor
und einer Enigma2-Extension. Die Integration speichert gemeinsame und persönliche Menüs und
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

Die [Projektregeln](../AGENTS.md) gelten für alle Änderungen. Das Projekt ist
veröffentlicht. Rückwärtskompatibilität zu veröffentlichten Versionen beachten
und bei Änderungen an APIs, Menüformat, gespeicherter Konfiguration oder internen
Schnittstellen bestehende Installationen berücksichtigen. Erforderliche
Migrationen bereitstellen und ebenso wie eine gegebenenfalls notwendige
Neueinrichtung kurz dokumentieren. Gespeicherte Nutzerdaten nicht ungefragt löschen.
Die Unterstützung der Zielsysteme OpenATV und Home Assistant beibehalten.

Zugangsdaten, `.local_info/`, `.work/` und `.temp/` nicht committen. `.local_info/`
enthält dauerhaft aufzubewahrende lokale Dateien; vorhandene Dateien dort belassen.
Während der Arbeit erzeugte, löschbare Dateien gehören nach `.work/`, auch neu
erstellte Update- oder Funktionstestprotokolle. Dauerhaft aufzubewahrende lokale
Protokolle gehören nach `.local_info/`. Vor Übergabe die zur Änderung passenden
Tests ausführen. Informationen zu ausgeführten Tests und deren Ergebnissen
gehören nicht in Changelogs, Dokumentation oder Release-Informationen.
Release-Informationen nennen zuerst benutzersichtbare Änderungen und danach
weitere Änderungen kurz und ohne ausführliche technische Details.

## Home-Assistant-Integration

Die Domain lautet `enigmaha_companion`. Ein einzelner Konfigurationseintrag
verwaltet die Menüs und Benutzerfreigaben für alle Receiver. Home Assistants `Store` speichert sie unter
`.storage/enigmaha_companion.menu`. Die laufende Integration lädt und validiert
die Konfiguration; Speichern erhöht deren gemeinsame Revision dauerhaft.
`menus.py` validiert Konfigurationsschema 2 und übernimmt gespeicherte v1-Menüs
beim Laden automatisch ohne Datenverlust. Das Receiver-Menüformat bleibt v1.

Die API trennt Receiver-Zugriff und Administration. Menü und Zustände werden
anhand der Menüfreigaben und Leseberechtigungen des angemeldeten Benutzers gefiltert. Fehlende
Steuerungsrechte entfernen die Aktionen eines Menüeintrags. Jeder Schaltbefehl
wird zusätzlich serverseitig auf Revision, Eintrag, erlaubte Aktion, aktuellen
Zustand und Berechtigungen geprüft und mit HA-Benutzerkontext ausgeführt.
Menüänderungen und Aktionen teilen sich eine Sperre. Eine fehlgeschlagene
Speicherung verändert weder das laufende Menü noch seine Revision.

Der Menüeditor sowie `/configuration`, `/users`, `/preview` und die kompatible
Einzelmenü-Route `/config` sind Administratoren vorbehalten. Die Vorschau nutzt
dieselbe Filterlogik wie Menü-, Zustands- und Aktionsabrufe. Details zu Freigaben
und Migration stehen unter [Benutzer-Menüs](Benutzermenues.md).
Receiver-Zugangsdaten werden nicht im Editor gespeichert.

### Schriftoptionen und Kompatibilität

Der HA-Options-Flow bietet nur `language` an. Beim Speichern der Sprache bleiben
Menükonfiguration, `display` und Menürevision unverändert. Die bisherigen
`display.font_family`- und `display.font_size`-Felder bleiben im Speicher und in
den API-Dokumenten erhalten, damit ältere Receiver weiterhin funktionieren.

Der aktuelle Receiver validiert diese Felder weiterhin, verwendet zum Zeichnen
aber ausschließlich seine lokalen Schriftoptionen. Leere Schriftfamilie und
Größe `0` bedeuten Auto. Die Vorgaben kommen aus dem Skin-Layout beziehungsweise
Skin-Profil; feste Werte überschreiben beide unabhängig voneinander. Lokale
Zahlenwerte behalten die Skalierung von der Referenzauflösung 1280 × 720.
Bestehende Konfigurationsdateien benötigen keine Migration. Details stehen unter
[Schrifteinstellungen](Installation.md#schriftfamilie-und-schriftgröße).

### Übersetzungen

Neue Installationen verwenden `auto`. Der Menüeditor enthält sein englisches
Wörterbuch in `panel.js`; `t()` übersetzt deutsche Quelltexte und setzt benannte
Platzhalter ein. Die Sprachauswahl liegt als `language` (`de`, `en` oder `auto`) in den
Config-Entry-Optionen und wird über den Options-Flow geändert. Der Editor übernimmt
sie mit der regelmäßigen Statusabfrage, ohne die Integration neu zu laden; der
Wechsel erhält Menüentwurf, Navigation und Filter. Solange die Option fehlt,
bleibt `enigmaha_companion.language` aus dem Browser als Rückfall erhalten.
Dieser bisherige Wert wird weder überschrieben noch gelöscht. Eine Migration der
Menüdaten oder Neueinrichtung ist nicht erforderlich. Der Einrichtungs-Flow
speichert `language: auto` nur für neu angelegte Config Entries. Vorhandene
Optionen bleiben unverändert; bei fehlender Option bleibt die bisherige
Browserauswahl erhalten und der Optionsdialog bietet weiterhin Deutsch als Vorgabe.
`auto` nutzt die effektive HA-Profilsprache (`hass.language`), ersatzweise die
erste unterstützte Browsersprache und zuletzt Deutsch. Regionale Sprachcodes
werden auf `de` oder `en` abgebildet. Änderungen der HA-/Browsersprache werden
im offenen Editor übernommen. Gemeinsame persistente HA-Hinweise folgen bei
`auto` der HA-Systemsprache.
HA-Konfigurationsdialoge verwenden `translations/de.json` und `translations/en.json`
und folgen der HA-Profilsprache; beide Kataloge liegen auch im Quellbaum.

Der Receiver nutzt `companion/i18n.py` und die lokale Einstellung `language`
(`de`, `en` oder `auto`, Standard `auto` bei neuer Installation). Ohne Konfigurationsdatei
liefert `load_settings()` die neuen Vorgaben. Eine vorhandene Datei ohne `language`
wird weiterhin mit `de` ergänzt; feste Werte werden beibehalten. Die Datei wird
beim Lesen nicht verändert. `auto` liest beim Öffnen die OpenATV-Locale
über `Components.International`, ersatzweise `Components.Language`; nicht
unterstützte Sprachen verwenden Deutsch. Der gespeicherte Wert bleibt `auto`.
Navigation, Hilfe, Einstellungen und eingebaute
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

## Updateablauf und Grenzen

`PROTOCOL_VERSION` in `protocol/enigmaha_protocol/compatibility.py` ist unabhängig
von der Releaseversion und wird nur bei inkompatiblen Protokolländerungen erhöht.
Beide Pakete erhalten dieselbe Protokollkennung. Gleiche Protokolle mit ungleichen
Releases erzeugen nur einen Hinweis; die normale Kommunikation bleibt freigegeben.

`repair_issues.py` verwaltet dauerhafte Protokollmeldungen, freiwillige Updatehinweise
für ältere kompatible Receiver und den Bezug zu einem
bestätigten Updateauftrag. Der native HA-Assistent in `repairs.py` delegiert
Installation, Wiederholung und Neustart an die bestehende Updatekoordination.
Das Schließen des Dialogs beendet nur die Fortschrittsbeobachtung. Die native
HA-Repair-API verlangt Administratorrechte, übergibt aber keine Benutzer-ID;
der Assistent verwendet deshalb den Systemkontext für HA-Dienste.

Die Updatekoordination liegt in `updates.py`, die portable Releaseprüfung in
`protocol/enigmaha_protocol/releases.py` und die OpenATV-Installation in
`enigma2/companion/updater.py`. Verwendet werden die öffentliche
[HACS-Update-Entität](https://github.com/hacs/integration/blob/main/custom_components/hacs/update.py)
und OpenATVs [`opkg`](https://github.com/openatv/enigma2/blob/master/lib/python/Components/Opkg.py)
sowie [`TryQuitMainloop`](https://github.com/openatv/enigma2/blob/master/lib/python/Screens/Standby.py).
Die bestehenden Python-Paketabhängigkeiten decken auch Hashing, UUID und
Prozessaufrufe ab; `python3-netclient` zieht `python3-crypt` nach.

Die eigene Update-Entität bietet `INSTALL` und `PROGRESS` an. Ihre
Installationsaktion prüft den Administrator- beziehungsweise Systemkontext,
validiert den angezeigten Release erneut und startet über `UpdateManager`
einen Auftrag ausschließlich für HA. Der HACS-Aufruf erhält den Benutzerkontext;
der HA-Neustart bleibt ein getrennter Schritt. Receiver-Reparaturen bieten älteren
Receivern den Release der laufenden HA-Version an, ohne HACS aufzurufen oder HA
neu zu starten. IPK-Installation und GUI-Neustart erfordern lokale Bestätigungen.
Änderungen am gespeicherten Auftrag aktualisieren die Entität ebenso
wie die bisherigen Reparaturhinweise. Das Abbrechen des Dienstaufrufs beendet
die vom Manager verwaltete Installation nicht. Speicherformat und Entitätskennung
bleiben erhalten; eine Migration ist nicht erforderlich. Die vorhandenen
Reparaturdaten akzeptieren zusätzlich kompatible ältere Receiver. Das optionale
Feld `job_issue` ordnet einen laufenden Auftrag dem passenden Hinweis zu; ohne
dieses Feld gilt weiterhin die bisherige Protokollreparatur.

Das IPK kompiliert im `postinst` die Python-Dateien des Plugins mit geprüften
Quellcode-Hashes für alle Optimierungsstufen neu. Die reproduzierbaren
Tar-Zeitstempel allein reichen zur Cacheprüfung nicht: Bei gleicher Dateigröße
kann sonst Bytecode des vorherigen Releases nach einem GUI-Neustart gültig
erscheinen.

### Prüfhinweise

Update-Tests prüfen feste HACS-Zielversionen, Benutzer-/Receiverbindung,
Bestätigungen, Ablehnung, Prüfsummen und Paketmetadaten, verlorene Antworten,
Speicherfehler, unterbrochene Installationen und Abschluss erst nach tatsächlich
laufender Zielversion auf beiden Seiten. HACS-Dienste und `opkg` werden in diesen
automatisierten Tests ersetzt.

Die automatisierten Tests decken Menüvalidierung, Befehle, echte HTTP-Anfragen
gegen Testserver, HA-Lebenszyklus und Berechtigungen, Symbolauflösung,
Receiver-Navigation, Layouts sowie Inhalt und Metadaten der Pakete ab.
HA-Dienste und Enigma2-Gerätefunktionen werden dabei durch Testobjekte ersetzt.
Die Receiver-Pakete werden auch auf Python-3.13-kompatible Syntax geprüft.
Sprachtests prüfen neue Standardwerte, den Erhalt bestehender Einstellungen, englische Texte, Platzhalter, gespeicherte
Sprachauswahl und unveränderte Menüentwürfe beim Wechsel.
Die Skin-Profiltests prüfen automatische und manuelle Auswahl, Speicherung und
Abbrechen, Übernahme beim erneuten Öffnen sowie fehlende Skin-Ressourcen.

Die Frontendtests verwenden jsdom und ersetzen native HA-Komponenten durch
Custom-Element-Testobjekte. Sie prüfen Filter, Modelländerungen, Sortierereignisse,
Scrollaufrufe und Dialogaktionen. Sie ersetzen keine Browserprüfung von Darstellung,
Gesten und modaler Fokusführung.

Vor einer Veröffentlichung die Schritte im Abschnitt „Funktionsprüfung“ der
[Installationsanleitung](Installation.md) auf den OpenATV-Zielreceivern mit
Home Assistant durchführen. Den Ablauf und die Ergebnisse unter `.work/`
protokollieren.

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
