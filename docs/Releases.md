# HACS und GitHub-Releases

**Deutsch** · [English](Releases.en.md)

Diese Anleitung beschreibt den Paketbau und die Veröffentlichung. Für die
Benutzereinrichtung siehe [Installation und Bedienung](Installation.md), für
lokale Tests die [Entwicklerdokumentation](Entwicklung.md).

## Einmalig vorbereiten

Die Projektdateien einschließlich `.github/workflows/release.yml`, `hacs.json`,
`package-lock.json` und `custom_components/` in den Standardbranch des öffentlichen
Repositories `topic2k/EnigmaHAcompanion` übernehmen. GitHub Actions muss aktiviert
sein. Der Release-Job benötigt die im Workflow angeforderte Berechtigung
`contents: write`; es ist kein zusätzlicher Token oder Secret nötig.
Organisationsrichtlinien dürfen diese Berechtigung nicht sperren. Versionsänderungen
werden über den normalen PR-Prozess in den geschützten Branch übernommen; der
Release-Job benötigt Schreibrecht für den Release-Tag. Er umgeht keine Branch- oder
Tagregeln.

HACS erkennt die Integration unter `custom_components/enigmaha_companion/`.
`hacs.json` legt `zip_release: true` und den festen Assetnamen
`enigmaha_companion.zip` fest. Das ZIP enthält die Integrationsdateien direkt an
seiner Wurzel, weil HACS es in den Integrationsordner entpackt.
Das versionierte HA-ZIP enthält hingegen `custom_components/enigmaha_companion/`
für die manuelle Installation. Beide enthalten dasselbe vollständige Paket
einschließlich Protokollmodul, Übersetzungen und Integrationslogo. Entitätssymbole
werden zur Laufzeit aus dem installierten HA-Frontend gelesen; ein MDI-Katalog
gehört nicht zu den Paketen.

## Lizenzen in den Paketen

Alle vier Installationspakete enthalten den GPLv2-Lizenztext als `LICENSE`
und die Freigabe unter `GPL-2.0-or-later` samt Fremdlizenzübersicht als `NOTICE`
im jeweiligen Integrations- beziehungsweise Plugin-Verzeichnis.
Das IPK nennt zusätzlich `License: GPL-2.0-or-later` in seinen Metadaten.
Die HA-ZIPs enthalten für die separat unter Apache 2.0 lizenzierten
Branding-Grafiken weiterhin `brand/NOTICE` und `brand/LICENSE-enigma2-connect.txt`.
Die Poppins-Schrift und ihr OFL-Lizenztext gehören nur zu den Entwicklungsquellen;
die Schriftdatei wird nicht in den Installationspaketen ausgeliefert.

Der zum Release gehörende Quellcode einschließlich Build- und
Installationsskripten steht unter dem zugehörigen Tag `v<Version>` im Repository
bereit. Diese Quellen zusammen mit den Paketen zugänglich halten.

## Release starten

1. Einen Arbeitsbranch erstellen und `python tools/release_version.py --bump patch`
   (oder `minor`/`major`) ausführen. Für eine konkrete Nummer stattdessen
   `python tools/release_version.py --version 1.3.0` verwenden.
2. Die fünf geänderten Versionsdateien committen, einen PR nach `main` öffnen und
   nach den erforderlichen Prüfungen mergen.
3. Auf GitHub **Actions → Release → Run workflow** öffnen, `main` auswählen und
   dieselbe bereits gemergte Version im Feld **Version** angeben.
   Optional **Als Vorabversion veröffentlichen** aktivieren.
4. **Run workflow** klicken.

Die automatische Erhöhung des Vorbereitungsskripts verwendet die höchste Nummer
aus `package.json` und allen vorhandenen Release-Tags `vMAJOR.MINOR.PATCH` im
Repository. Bei einer Basis `1.0.2` ergibt `patch` → `1.0.3`, `minor` → `1.1.0`,
`major` → `2.0.0`.
Minor setzt Patch auf null, Major setzt Minor und Patch auf null. Die Auswahl
bestimmt der Maintainer; Änderungen werden nicht automatisch klassifiziert.
Eine explizite Version muss mindestens der Projektversion entsprechen und höher
als alle bestehenden Release-Tags sein. Akzeptiert wird ausschließlich `MAJOR.MINOR.PATCH`
ohne `v` oder Suffix; die Vorabversion-Checkbox setzt das GitHub-/HACS-Betaflag
und benötigt ebenfalls eine neue Nummer.

Der Workflow synchronisiert `package.json`, beide Versionsfelder in
`package-lock.json`, das HA-Manifest, `const.py` und die gemeinsame Komponentenversion
in `protocol/enigmaha_protocol/compatibility.py`, baut die Pakete und führt die
Python- und Frontendtests aus. Erst danach erhält der separate Release-Job
Schreibrechte und prüft SHA256-Summen sowie den getesteten Git-Quellbaum. Die
Versionsänderung muss bereits im ausgewählten Branch enthalten sein; andernfalls
bricht der Workflow ab. Der Release-Job veröffentlicht ausschließlich den Tag
`v<Version>` für diesen geprüften Commit und lädt die getesteten Pakete hoch. Hat
sich der Branch während des Builds geändert, bricht der Workflow ab; anschließend
mit dem aktuellen Branch erneut starten. Nach einem Release den lokalen Branch mit
`git pull --ff-only` aktualisieren.

Alle Dateien werden zunächst an einen Release-Entwurf gehängt;
erst nach vollständigem Upload wird dieser veröffentlicht. Bestehende Tags oder
Releases werden nicht überschrieben. Ein Vorabrelease wird nicht als „Latest“ markiert.

Ein Release enthält:

| Datei | Verwendung |
| --- | --- |
| `enigmaha_companion.zip` | HACS-Installation und Updates |
| `enigmaha-companion-ha-<Version>.zip` | Manuelle HA-Installation |
| `enigma2-plugin-extensions-enigmahacompanion_<Version>_all.ipk` | OpenATV-Receiver |
| `enigmaha-companion-enigma2-<Version>.tar.gz` | Alternative Receiver-Installation |
| `SHA256SUMS.txt` | Prüfsummen der vier Pakete |

HACS-Nutzer fügen das Repository einmal als benutzerdefinierte **Integration**
hinzu und installieren einen veröffentlichten Release.
Der Entwicklungsbranch wird ausgeblendet, da der Build das gemeinsame Protokoll
einbindet. Für Vorabversionen in HACS die Anzeige von Betaversionen aktivieren.
Eine Aufnahme in den HACS-Standardkatalog ist ein separater Vorgang.

## Fehlerbehebung

- **Run workflow fehlt:** Die Workflowdatei muss im Standardbranch liegen;
  zum Starten ist Schreibzugriff auf das Repository erforderlich.
- **Ungültige oder zu niedrige Version:** `MAJOR.MINOR.PATCH` ohne Präfix/Suffix
  verwenden; sie muss mindestens der Projektversion entsprechen und höher als alle
  vorhandenen Tags sein. Im Release-Workflow die bereits gemergte Version angeben.
- **Branch wurde während des Builds geändert:** Workflow erneut starten.
- **Release-Version ist noch nicht im Branch:** Versionsdateien über einen PR
  aktualisieren, die erforderlichen Prüfungen abwarten und den Release-Workflow
  danach mit derselben Version erneut starten.
- **Tag oder Release existiert bereits:** Für neue Änderungen die Version erhöhen.
  Nach fehlgeschlagener Veröffentlichung einen eventuell verbliebenen Entwurf unter
  **Releases** prüfen. Nur einen nachweislich unveröffentlichten Fehlversuch bereinigen
  und den Workflow erneut starten; veröffentlichte Tags und Pakete unverändert lassen.
  Wurde der Versions-PR bereits gemergt, bleibt die Nummer reserviert; das
  Vorbereitungsskript wählt bei automatischer Erhöhung die nächste Nummer.
- **403 beim Veröffentlichen:** Actions- und Repositoryrichtlinien für
  `GITHUB_TOKEN` / `contents: write` prüfen.
- **HACS findet das Paket nicht:** Öffentliches Repository, veröffentlichten Release
  und Asset `enigmaha_companion.zip` prüfen. Automatisch erzeugte GitHub-Quellarchive
  enthalten das beim Build ergänzte Protokollmodul nicht.

## Release-Hinweise

Das gemeinsame HACS/IPK-Update bietet nur veröffentlichte stabile Releases an.
HACS-ZIP, IPK und `SHA256SUMS.txt` müssen unter den oben genannten Namen im
selben Release liegen. Nach Veröffentlichung Assets und Prüfsummen unverändert
lassen: Ein gestarteter Updatevorgang bindet Receiver und Zielversion fest.
Der Release mit der Updatefunktion muss zunächst einmal auf beiden Seiten
installiert werden; erst danach ist der koordinierte Ablauf verfügbar.

Die automatisch erzeugten Release-Informationen nach dem Workflow überarbeiten:
Nur kurze Zusammenfassungen der Änderungen aufnehmen, gruppiert nach **Allgemein**,
**Home Assistant** (nur HA betreffend) und **Receiver** (nur Receiver betreffend).
Leere Gruppen weglassen. Innerhalb jeder Gruppe zuerst benutzersichtbare Änderungen
nennen und ausführliche technische Details vermeiden. Rückwärtsinkompatible
Änderungen gesondert unter **Rückwärtsinkompatible Änderungen** hervorheben;
erforderliche Migrationen oder Neueinrichtung kurz nennen. Voraussetzungen,
bekannte Fehler und Grenzen nur kurz nennen, soweit sie die Nutzung betreffen.
Keine Informationen zu
ausgeführten Tests, Testergebnissen oder Links auf Testprotokolle aufnehmen.
Neu erstellte Update- oder Funktionstestprotokolle unter `.work/` speichern;
dauerhaft aufzubewahrende lokale Dateien gehören nach `.local_info/`.
Vorhandene Dateien in `.local_info/` belassen. Beide Ordner nicht veröffentlichen.

Das Projekt ist veröffentlicht. Bei Änderungen Rückwärtskompatibilität zu
veröffentlichten Versionen beachten und erforderliche Migrationen bereitstellen.
Migrationen und gegebenenfalls notwendige Neueinrichtung in den Release-Informationen
kurz beschreiben. Bestehende Nutzerdaten nicht ungefragt löschen. Die HA-Integration
und das Receiver-Plugin weiterhin aus demselben Release installieren.

Grundlagen: [HACS-Integrationsstruktur](https://www.hacs.xyz/docs/publish/integration/),
[HACS-Release-ZIPs](https://www.hacs.xyz/docs/publish/start/),
[Workflows über GitHub starten](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
