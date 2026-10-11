# Live-Update-Test vom 11. Oktober 2026

Ergebnis: HA-Integration und OpenATV-Plugin laufen mit **Release 1.0.2**.
Der vollständige bestätigte Updateablauf von 1.0.1 auf 1.0.2 war erfolgreich,
ohne manuelles Kopieren von Programmdateien oder Reparieren von Python-Caches.

## Zielsysteme und Vorbereitung

- Home Assistant 2026.10.1 auf HAOS 18.3, Raspberry Pi 5; bestehende HACS-Integration.
- Octagon SF8008 4K Supreme, OpenATV 7.6.0, Python 3.13.12, OpenWebif 2.4.0.
- Menü, Receiver-Konfiguration und vorhandene Programmdateien vor Änderungen gesichert.
- Zunächst Entwicklungsbuilds mit der neuen Updatefunktion unter Versionskennung
  1.0.0 installiert. Die zuvor laufenden Veröffentlichungen enthielten diese Funktion
  noch nicht; das war eine einmalige Vorbereitung dieses Tests.

## Erster Durchlauf und gefundener Fehler

Das gemeinsame Update auf 1.0.1 installierte die HA-Komponente über die registrierte
HACS-Update-Entität und das Receiver-Paket nach lokaler Bestätigung über `opkg`.
Eine vorherige Ablehnung ließ die Receiver-Paketversion bei 1.0.0; erneutes
Anbieten behielt die feste Zielversion bei und erforderte eine neue Bestätigung.

Nach dem GUI-Neustart blieb die Receiver-Laufzeit jedoch bei 1.0.0, obwohl
Paketstatus und Python-Quelltext bereits 1.0.1 meldeten. Ursache waren alte
Bytecode-Dateien: Die reproduzierbaren Tar-Zeitstempel und die unveränderte
Dateigröße ließen den alten Python-Cache gültig erscheinen. Die Updatekoordination
verhinderte korrekt einen vorzeitigen Abschluss.

Für diesen ersten Durchlauf wurde ausschließlich der Bytecode des eigenen Plugins
gezielt erneuert und die GUI erneut gestartet. Danach meldete der Receiver 1.0.1.
Während HA noch 1.0.0 ausführte, zeigten beide Oberflächen die Versionsabweichung;
normale Menüabrufe waren gesperrt. Der separate HA-Neustartdialog wurde zunächst
abgebrochen und dann bestätigt. Erst nach laufendem HA 1.0.1 war der Auftrag abgeschlossen.

## Korrektur und vollständiger zweiter Durchlauf

[Release 1.0.2](https://github.com/topic2k/EnigmaHAcompanion/releases/tag/v1.0.2)
enthält ein ausführbares IPK-`postinst`, das den Plugin-Bytecode mit geprüften
Quellcode-Hashes in allen Optimierungsstufen neu erzeugt. Ein Regressionstest
reproduziert den alten Cachefehler bei gleicher Dateigröße und gleichem Zeitstempel
und prüft die Korrektur. [Build, Tests und Veröffentlichung](https://github.com/topic2k/EnigmaHAcompanion/actions/runs/38151814573)
waren erfolgreich: **150 Python- und 34 Frontendtests**.

| Prüfung | Ergebnis |
| --- | --- |
| Releaseprüfung und Startbestätigung im HA-Editor | Feste Zielversion 1.0.2 und beteiligter Receiver angezeigt |
| Installation über HACS | `update.enigmaha_companion_update` installierte `v1.0.2` |
| Receiver-Ablehnung und erneutes Anbieten | Keine Installation ohne Zustimmung; Ziel blieb 1.0.2, neuer Versuch erforderte Bestätigung |
| IPK-Installation nach lokalem Ja | `opkg`: Version 1.0.2, `install ok installed` |
| Separate GUI-Neustartbestätigung | Vor Neustart blieb die gemeldete Laufzeit 1.0.1 und der Auftrag offen |
| Laufzeit nach GUI-Neustart | Receiver meldete selbstständig 1.0.2, ohne manuelle Cachekorrektur |
| Versionsabweichung vor HA-Neustart | HA 1.0.1 und Receiver 1.0.2 erkannt; Verbindung gesperrt |
| Separat bestätigter HA-Neustart | HA lud 1.0.2; persistierter Auftrag wechselte auf `completed` |
| Normale Receiver-Verbindung danach | Menürevision 14, acht lesbare Entitätszustände; Anzeige „Verbunden“ |
| Probe mit absichtlich falscher Versionskennung | `version_mismatch`; normaler Client anschließend wieder erfolgreich |

## Abschließender Dateivergleich

Alle vier veröffentlichten Paket-Prüfsummen stimmen mit `SHA256SUMS.txt` überein.
Die 27 installierten HA-Dateien entsprechen byteweise dem veröffentlichten HACS-ZIP;
die 22 Receiver-Dateien entsprechen byteweise dem veröffentlichten Receiver-Payload.
Das IPK hat SHA-256 `278bd21fa5d020c47e071318a20e9881df33f1f294628982f169d0a8bb1b60a5`.

Das HA-Menü entspricht vollständig der Sicherung einschließlich Revision 14.
Die Receiver-Konfiguration ist byteweise unverändert und weiterhin mit Modus `0600`
geschützt. Receiver-Identität und Updatejournal blieben über Neustarts erhalten;
das Journal meldet Version 1.0.2 und `completed`. Der tatsächlich verwendete
Python-Cache besitzt das Flag 3 für geprüfte Quellcode-Hashes.

## Grenzen

Während des Tests lief keine Aufnahme. Das Verhalten des nativen OpenATV-
Neustartdialogs bei aktiver Aufnahme wurde daher nicht praktisch geprüft.
Der abschließende Funktionstest las Menü und Zustände; er schaltete keine realen
Lampen. Zugangsdaten, Sicherungen und interne Testbelege bleiben außerhalb des
Repositories in den ignorierten Arbeitsdateien.
