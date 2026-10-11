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
Organisationsrichtlinien dürfen diese Berechtigung nicht sperren. Branch- und
Tagregeln müssen dem Workflow das Schreiben des Versionscommits und Release-Tags
erlauben; andernfalls bricht er ab, ohne diese Regeln zu umgehen.

HACS erkennt die Integration unter `custom_components/enigmaha_companion/`.
`hacs.json` legt `zip_release: true` und den festen Assetnamen
`enigmaha_companion.zip` fest. Das ZIP enthält die Integrationsdateien direkt an
seiner Wurzel, weil HACS es in den Integrationsordner entpackt.
Das versionierte HA-ZIP enthält hingegen `custom_components/enigmaha_companion/`
für die manuelle Installation. Beide enthalten dasselbe vollständige Paket
einschließlich Protokollmodul, Übersetzungen und Integrationslogo. Entitätssymbole
werden zur Laufzeit aus dem installierten HA-Frontend gelesen; ein MDI-Katalog
gehört nicht zu den Paketen.

## Release starten

1. Die zu veröffentlichenden Änderungen committen und pushen. Die Version muss
   vorher nicht manuell erhöht werden.
2. Auf GitHub **Actions → Release → Run workflow** öffnen.
3. Den gewünschten Branch und die **Automatische Versionserhöhung** auswählen:
   `patch` (Standard), `minor` oder `major`. Optional im Feld **Optionale Version**
   eine konkrete Nummer wie `0.1.6` oder `1.0.0` eingeben; sie ersetzt die automatische
   Auswahl. Optional **Als Vorabversion veröffentlichen** aktivieren.
4. **Run workflow** klicken.

Die automatische Erhöhung verwendet die höchste Nummer aus `package.json` und
allen vorhandenen Release-Tags `vMAJOR.MINOR.PATCH` im Repository. Bei einer Basis
`0.1.6` ergibt `patch` → `0.1.7`, `minor` → `0.2.0`, `major` → `1.0.0`.
Minor setzt Patch auf null, Major setzt Minor und Patch auf null. Die Auswahl
bestimmt der Maintainer; der Workflow klassifiziert Änderungen nicht automatisch.
Eine explizite Version muss mindestens der Projektversion entsprechen und höher
als alle bestehenden Release-Tags sein. So kann die erste Veröffentlichung die
vorhandene `0.1.6` verwenden. Akzeptiert wird ausschließlich `MAJOR.MINOR.PATCH`
ohne `v` oder Suffix; die Vorabversion-Checkbox setzt das GitHub-/HACS-Betaflag
und benötigt ebenfalls eine neue Nummer.

Der Workflow synchronisiert `package.json`, beide Versionsfelder in
`package-lock.json`, das HA-Manifest und `const.py`, baut die Pakete und führt die
Python- und Frontendtests aus. Erst danach erhält der separate Release-Job
Schreibrechte und prüft SHA256-Summen und den getesteten Git-Quellbaum. Er erstellt
einen Versionscommit `Release <Version>` und aktualisiert den ausgewählten Branch
und den Tag `v<Version>` gemeinsam. Hat sich der Branch während des Builds geändert,
bricht der Workflow ab; anschließend mit dem aktuellen Branch erneut starten.
Nach einem Release den lokalen Branch mit `git pull --ff-only` aktualisieren.

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
hinzu. Erst nach dem ersten veröffentlichten Release ist die Installation möglich.
Der Entwicklungsbranch wird ausgeblendet, da der Build das gemeinsame Protokoll
einbindet. Für Vorabversionen in HACS die Anzeige von Betaversionen aktivieren.
Eine Aufnahme in den HACS-Standardkatalog ist ein separater Vorgang.

## Fehlerbehebung

- **Run workflow fehlt:** Die Workflowdatei muss im Standardbranch liegen;
  zum Starten ist Schreibzugriff auf das Repository erforderlich.
- **Ungültige oder zu niedrige Version:** `MAJOR.MINOR.PATCH` ohne Präfix/Suffix
  und oberhalb vorhandener Tags verwenden oder das Versionsfeld leer lassen.
- **Branch wurde während des Builds geändert:** Workflow erneut starten.
- **Tag oder Release existiert bereits:** Für neue Änderungen die Version erhöhen.
  Nach fehlgeschlagener Veröffentlichung einen eventuell verbliebenen Entwurf unter
  **Releases** prüfen. Nur einen nachweislich unveröffentlichten Fehlversuch bereinigen
  und den Workflow erneut starten; veröffentlichte Releases unverändert lassen.
  Wurden Versionscommit und Tag schon geschrieben, bleibt die Nummer reserviert;
  ein neuer automatischer Lauf wählt die nächste Nummer.
- **403 beim Veröffentlichen:** Actions- und Repositoryrichtlinien für
  `GITHUB_TOKEN` / `contents: write` prüfen.
- **HACS findet das Paket nicht:** Öffentliches Repository, veröffentlichten Release
  und Asset `enigmaha_companion.zip` prüfen. Automatisch erzeugte GitHub-Quellarchive
  enthalten das beim Build ergänzte Protokollmodul nicht.

## Release-Hinweise

Funktionen, Voraussetzungen und bekannte Grenzen des Releases beschreiben.
Erforderliche Schritte zur Neueinrichtung ausdrücklich nennen. Den Teststand aus
der [Entwicklerdokumentation](Entwicklung.md#teststand-und-grenzen) berücksichtigen
und nur tatsächlich geprüfte Systeme als getestet ausweisen.

Grundlagen: [HACS-Integrationsstruktur](https://www.hacs.xyz/docs/publish/integration/),
[HACS-Release-ZIPs](https://www.hacs.xyz/docs/publish/start/),
[Workflows über GitHub starten](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/manually-run-a-workflow).
