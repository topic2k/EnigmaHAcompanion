# Projektregeln

- Das Projekt ist veröffentlicht. Bei Änderungen Rückwärtskompatibilität zu
  veröffentlichten Projektversionen beachten.
- Bei Änderungen an APIs, Menüformat, gespeicherter Konfiguration oder internen
  Schnittstellen bestehende Installationen berücksichtigen. Wenn Änderungen eine
  Migration erfordern, entsprechende Migrationen bereitstellen.
- Notwendige Migrationen und gegebenenfalls erforderliche Neueinrichtung kurz
  dokumentieren. Bestehende Nutzerdaten nicht ungefragt löschen. Die zugesagte
  Unterstützung der aktuellen Zielsysteme OpenATV und HA beibehalten.
- Entwicklung und Receiver-Tests erfolgen ausschließlich für und auf OpenATV.
- Für die Entitätsauswahl im HA-Editor native HA-Selector-Komponenten mit Filtern nutzen.
- Zugangsdaten, `.local_info/`, `.work/` und `.temp/` nicht committen.
  Tests vor Übergabe passend zur Änderung ausführen.
- Keine Informationen zu ausgeführten Tests oder deren Erfolg bzw. Fehlschlag in
  Changelogs, Dokumentation oder Release-Informationen aufnehmen.
- Release-Informationen beschreiben zuerst benutzersichtbare Änderungen. Weitere
  Änderungen danach kurz und knapp, ohne ausführliche technische Details aufführen.
- `.local_info/` enthält Dateien, die der Benutzer dauerhaft lokal behalten möchte.
  Vorhandene Dateien dort belassen und nicht als temporäre Arbeitsdateien behandeln.
- `.work/` ist für während der Arbeit erzeugte Dateien vorgesehen, die gelöscht
  werden können. Neu erstellte Update- oder Funktionstestprotokolle dort speichern;
  dauerhaft aufzubewahrende lokale Protokolle gehören nach `.local_info/`.
