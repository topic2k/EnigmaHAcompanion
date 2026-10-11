# Projektregeln

- Das Projekt befindet sich in aktiver Entwicklung. Rückwärtskompatibilität zu
  früheren Projektversionen ist nicht erforderlich.
- APIs, Menüformat, gespeicherte Konfiguration und interne Schnittstellen dürfen
  geändert werden. Keine Legacy-Adapter, Versionsmigrationen oder parallelen alten
  Implementierungen nur zur Kompatibilität mit bisherigen Entwicklungsständen bauen.
- Notwendige Neueinrichtung nach einer Änderung kurz dokumentieren. Bestehende
  Nutzerdaten nicht ungefragt löschen. Die Regel betrifft frühere Projektversionen,
  nicht die zugesagte Unterstützung der aktuellen Zielsysteme OpenATV und HA.
- Entwicklung und Receiver-Tests erfolgen ausschließlich für und auf OpenATV.
- Für die Entitätsauswahl im HA-Editor native HA-Selector-Komponenten mit Filtern nutzen.
- Zugangsdaten, `.work/` und `.temp/` nicht committen. Tests vor Übergabe passend zur Änderung ausführen.
