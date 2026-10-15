# Enigma2-Extension

**Deutsch** · [English](README.en.md)

Die Extension zeigt das in Home Assistant zusammengestellte Menü auf dem Receiver.
`Plugins/Extensions/EnigmaHACompanion/` enthält Screen, Tastenbelegung, lokale
Einstellungen und Darstellung. `companion/` enthält den GUI-unabhängigen
Navigationskern und HTTP-Client.

Für die Einrichtung siehe [Installation und Bedienung](../docs/Installation.md).
Build und Tests stehen in der [Entwicklerdokumentation](../docs/Entwicklung.md),
ebenso der [Updateablauf und seine Grenzen](../docs/Entwicklung.md#updateablauf-und-grenzen).

## Sprache

Neue Installationen verwenden **Automatisch**; bestehende Einstellungen bleiben erhalten.
**Menü/Blau → Sprache** bietet
**Deutsch**, **English** und **Automatisch**. Automatisch folgt der OpenATV-Systemsprache;
nicht unterstützte Sprachen verwenden Deutsch. Mit Grün speichern und das Plugin erneut öffnen.
`language` in `/etc/enigma2/enigmaha_companion.json` verwendet `de`, `en` oder `auto`.
Die Auswahl gilt für Texte, Hilfe, Zustände und die eingebauten Skin-Layouts.
Die Systemdialoge von OpenATV und vom aktiven Skin fest vorgegebene Texte folgen
weiterhin deren Sprache. Eigene HA-Menünamen bleiben erhalten.

## Paket und Laufzeit

Entwicklung und Tests erfolgen ausschließlich für und auf OpenATV mit
Python 3.13 oder neuer und Twisted.
Mit `python tools/build.py` im Projektstamm entstehen IPK und TAR unter `dist/`.
Der Build bettet `companion` und `enigmaha_protocol` in den Plugin-Ordner ein
und passt die Imports an. Zusätzliche globale Python-Pakete aus diesem Projekt
müssen auf dem Receiver nicht installiert werden.

Die Verbindungseinstellungen liegen unter
`/etc/enigma2/enigmaha_companion.json` außerhalb des Plugin-Ordners.
Nach der Paketinstallation die Receiver-GUI neu starten.

## Layout und Schrift

Hauptansicht und Einstellungen passen sich an die Desktopauflösung an.
Unter **Menü/Blau → Skin-Profil** stehen **Automatisch**, **Standard (aktiver Skin)**
und **GradientFHD** zur Auswahl. Standardmäßig wird der aktive Skin beim Öffnen
anhand von `config.skin.primary_skin` erkannt. Unbekannte Skins verwenden das
Standardprofil mit Fensterrahmen und Standardfarben des aktiven Skins.
Die manuelle Auswahl überschreibt die Erkennung. Mit Grün speichern; ein Wechsel
wird beim nächsten Öffnen des Plugins wirksam. Der systemweit aktive Skin wird
dadurch nicht geändert.
Für GradientFHD gibt es ein Profil mit zentriertem Dialog (1110 × 900 bei Full HD),
transparentem Hintergrund, Titelverlauf und blauer Auswahlmarkierung.
Vorhandene Skin-Farben, Schriften und Tastengrafiken werden direkt verwendet.
Verläufe und Rundungen werden bei vorhandenen Enigma2-APIs aktiviert,
andernfalls kommen einfache Farbflächen zum Einsatz.

Schriftfamilie und Schriftgröße werden ausschließlich am Receiver eingestellt.
**Auto (Skin-/Receiver-Standard)** verwendet jeweils die Skin- beziehungsweise
Profilvorgabe. GradientFHD verwendet dabei `Gradient_Font` mit 42 Pixeln
und 60 Pixeln Zeilenhöhe bei Full HD. Feste Schriftfamilien und Größen haben in
allen Profilen Vorrang; feste Größen behalten die Skalierung von 1280 × 720 auf
die Desktopauflösung. Fehlende Schriften fallen auf `Regular` zurück.
Leere Schriftfamilie und Größe `0` bleiben die gespeicherten Auto-Werte.
Vorhandene lokale Einstellungen bleiben erhalten; HA-Schriftwerte werden vom
aktualisierten Receiver ignoriert. Eine Neueinrichtung ist nicht nötig.

Die Tastenleiste lädt die farbigen Pfeile und Symbole für Menü, Info und Exit aus
`/usr/share/enigma2/GradientFHD/buttons/`, in den Einstellungen zusätzlich
Links/Rechts. Die Recall-Taste verwendet die mitgelieferte Grafik
`skin/GradientFHD/buttons/key_recall.png` im Plugin-Verzeichnis. Fehlt eine Grafik,
erscheint der Tastenname. Die Einstellungen
positionieren die numerische Eingabehilfe oberhalb der Tastenleiste.

## Schnittstelle für Skin-Autoren

Skins können die Screens `EnigmaHACompanion` und `EnigmaHASetup` definieren.
Im Modus **Automatisch** haben diese Vorrang vor den eingebauten Layouts.
Eine manuelle Profilauswahl verwendet das eingebaute Layout. Die Screen-Namen
`EnigmaHACompanionBuiltin` und `EnigmaHASetupBuiltin` sind dafür reserviert.

| Screen | Widgets |
| --- | --- |
| `EnigmaHACompanion` | `heading`, `list`, `status`, `footer` |
| `EnigmaHASetup` | `config`, `hint`, versteckter `HelpWindow`-Anker |

Nach dem Layout wird die tatsächliche Listengröße für Textspalten und
seitenweises Blättern übernommen. Das `font`-Attribut des Widgets `list` liefert
bei Auto Schriftfamilie und Größe; feste Receiver-Werte überschreiben sie einzeln.

### Weitere Profile ergänzen

`appearance.py` enthält das gemeinsame Layout und die Auflösungsskalierung.
Skin-spezifische Darstellung liegt in einem eigenen Unterordner je Skin:

```text
skin/
├── __init__.py              # Zentrale Profilliste und Erkennung
├── base.py                  # Gemeinsame Profil-Schnittstelle
├── native/
│   └── __init__.py          # Standardprofil
└── GradientFHD/
    └── __init__.py          # GradientFHD-Profil
```

Für einen weiteren Skin einen Ordner `skin/ExampleHD/` anlegen und dort in
`__init__.py` eine eigene Klasse von `SkinProfile` ableiten. Weitere Layout-Module
und eigene Grafiken können ebenfalls in diesem Skin-Ordner liegen:

```python
from ..base import SkinProfile


class ExampleProfile(SkinProfile):
    id = "example"
    label = "ExampleHD"
    skin_directories = ("ExampleHD",)
    width = 1000
    height = 620
    font_family = "ExampleFont"
    heading_family = "ExampleFont"
```

Die Klasse in `skin/__init__.py` mit `from .ExampleHD import ExampleProfile`
importieren und eine Instanz in `PROFILES`
ergänzen. Dadurch erscheint sie automatisch in der Einstellungs-Auswahl,
Konfigurationsprüfung und Skin-Erkennung. `id` muss eindeutig sein; `auto` ist
reserviert. `skin_directories` enthält vollständige Skin-Verzeichnisnamen;
die Erkennung ignoriert Groß-/Kleinschreibung und vergleicht keine Teilnamen.

Maße sind in der Referenzauflösung 1280 × 720 angegeben. `Appearance.px()`
skaliert sie. Für weitere Anpassungen gibt es drei Methoden:

- `menu_font(appearance, family, size)` liefert die Profilvorgaben für Schrift,
  Pixelgröße und Zeilenhöhe. `Appearance` wendet danach feste Receiver-Werte an.
- `decorate(appearance, root, element, label_attrs, list_attrs)` ergänzt Hintergründe
  und passt XML-Attribute für Beschriftungen und Listen an.
- `footer(appearance, element, label_attrs, setup)` baut die Tastenleiste und muss
  das Widget `footer` beziehungsweise `hint` bereitstellen.

`element(tag, x, y, width, height, **attrs)` ergänzt ein XML-Element mit bereits
skalierten Maßen. `setup` unterscheidet Hauptansicht und Einstellungen.
Navigation, HTTP-Client und Einstellungsdialog benötigen für neue Profile keine
Änderung. Fehlende Skin-Schriften und Grafiken sollten lesbare Ersatzdarstellungen
erhalten; `skin/GradientFHD/__init__.py` zeigt die Verwendung vorhandener OpenATV-Funktionen.

Nach Installation des aktualisierten Receiver-Pakets die GUI neu starten.
Keine Neueinrichtung erforderlich; Zugangsdaten bleiben erhalten. Fehlt
`skin_profile` in der Konfigurationsdatei, gilt der Standardwert `auto`.
Fehlt `language` in einer vorhandenen Datei, bleibt Deutsch aktiv. Nur ohne
Konfigurationsdatei wird automatisch die OpenATV-Systemsprache übernommen.

## Lizenz

Das Receiver-Plugin steht unter **GPL-2.0-or-later**, siehe [LICENSE](../LICENSE)
und [NOTICE](../NOTICE). IPK und TAR-Paket enthalten beide Dateien im
Plugin-Verzeichnis `EnigmaHACompanion/`. Externe OpenATV-Komponenten und
Skin-Grafiken behalten ihre eigenen Lizenzen und werden nicht mitgeliefert.

## Navigation und Einstieg

Auf/Ab bewegt die Auswahl um einen Eintrag. Ch+ blättert eine Seite aufwärts,
Ch− abwärts. Die Option **Ch+/− umkehren** tauscht diese Richtung und wird
mit Grün gespeichert. Die Hilfe zeigt die eingestellte Richtung.
Die Schrittweite ergibt sich aus sichtbarer Listenhöhe und Zeilenhöhe;
am ersten und letzten Eintrag bleibt die Auswahl stehen.
Gedrückt gehaltene Ch-Tasten lösen wiederholtes Blättern aus.

**Im Hauptmenü anzeigen** ergänzt einen direkten Einstieg in das Enigma2-Hauptmenü.
Die Option ist standardmäßig aus. Änderungen werden beim nächsten Öffnen des
Hauptmenüs berücksichtigt.

## Fernbedienung

**Rot/Exit** beendet das Menü aus jeder Ebene. **Recall** geht eine Ebene zurück
und bleibt auf oberster Ebene ohne Funktion. **Links/Rechts** blättert eine Seite
aufwärts/abwärts, unabhängig von der Ch+/−-Einstellung. **OK/Grün** öffnet Untermenüs
oder schaltet Einträge. **Info** zeigt die Version auf dem Receiver und in Home Assistant, den angemeldeten
HA-Benutzer und die Anzahl seiner sichtbaren Menüs, Untermenüs und Entitätseinträge
als Gesamtzahl unter **Entitäten**.
Mehrfach aufgeführte Entitäten zählen je Menüeintrag. Die erzeugte Menüauswahl zählt
nicht als eigenes Menü. Bei älteren HA-Integrationen oder fehlender Verbindung
bleiben Benutzer und Zähler als nicht abrufbar gekennzeichnet. Keine Migration
oder Neueinrichtung erforderlich.

**Menü/Blau → Menüposition beim Beenden merken** ist standardmäßig eingeschaltet,
auch bei bestehenden Installationen. Rot/Exit speichert Menübene und Auswahl für
das nächste Öffnen, auch nach einem GUI-Neustart. Ausgeschaltet beginnt das Menü
wieder auf oberster Ebene. Die Position liegt getrennt in
`/etc/enigma2/enigmaha_companion_position.json` und ist an HA-Adresse und Token
gebunden, ohne die Zugangsdaten dort abzulegen. Entfernte oder nicht mehr
freigegebene Einträge werden nicht wiederhergestellt. Die bestehende
Konfiguration wird beim Laden nicht verändert; eine Migration ist nicht nötig.

## Schalten über OpenATV-Hotkeys

Schaltbare Menüeinträge lassen sich über OpenATV-Hotkeys direkt mit frei
gewählten Fernbedienungstasten umschalten. Die Einrichtung beschreibt die
[Dokumentation](../docs/Installation.md#openatv-hotkeys).
