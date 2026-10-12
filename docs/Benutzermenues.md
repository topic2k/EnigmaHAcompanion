# Benutzerabhängige Menüs

**Deutsch** · [English](User-menus.en.md)

Im HA-Menüeditor lassen sich mehrere vollständige Menüs mit eigenem Titel und
eigener Struktur anlegen. Gemeinsame Menüs und persönliche Menüs können
nebeneinander verwendet werden. Ganze Menüs, Untermenüs und einzelne Einträge
lassen sich für HA-Benutzer freigeben.

## Menüs und Freigaben einrichten

1. **EnigmaHA Companion** öffnen. Die Übersicht **Menüs verwalten** zeigt alle
   vollständigen Menüs mit ihrem Titel. Über **Menü anlegen** oder das Kopiersymbol
   weitere Menüs erstellen. Duplikate erhalten neue IDs und behalten ihre Freigaben.
2. Menüs am Ziehgriff per Drag&Drop oder mit den Pfeilsymbolen sortieren.
   Das Stiftsymbol öffnet die Menüeinträge. **Zur Menüverwaltung** führt zurück;
   Änderungen bleiben bis zum Speichern im Entwurf erhalten.
3. Den Titel direkt in der Menüliste ändern. Schriftfamilie und Schriftgröße
   ausschließlich am jeweiligen Receiver unter **Menü/Blau → Einstellungen**
   wählen. **Auto** verwendet den Skin-/Receiver-Standard; feste Werte haben
   Vorrang. Eine Neueinrichtung ist nicht nötig.
4. Das Benutzer-Symbol oberhalb der Menüeinträge öffnen. Bei Menüeinträgen und
   Untermenüs öffnet das Benutzer-Symbol (`mdi:account-edit`) direkt vor dem
   Löschen-Symbol denselben Dialog. Dort die **Freigabe** wählen:

   | Ebene | Auswahl |
   | --- | --- |
   | Vollständiges Menü | Alle Benutzer, Ausgewählte Benutzer, Menü deaktiviert |
   | Untermenü oder Eintrag | Vom übergeordneten Menü übernehmen, Ausgewählte Benutzer, Menü deaktiviert |

5. Bei **Ausgewählte Benutzer** einen oder mehrere aktive HA-Benutzer auswählen.
   Angezeigt werden Namen ohne IDs. Personen haben keine eigenen Tokens und
   werden nicht zusätzlich angeboten; maßgeblich ist ihr verknüpfter HA-Benutzer.
   Eine leere Auswahl gibt niemandem Zugriff. Übergeordnete Einschränkungen
   gelten zusätzlich; ein Kind kann eine gesperrte Elternebene nicht freigeben.
   Mit **Übernehmen** die Zuordnung in den Entwurf übernehmen; **Abbrechen** oder
   Escape verwerfen die Änderungen im Dialog.
6. Im Vorschau-Block rechts in der Übersicht unter **Ansicht für Benutzer** einen
   Benutzer wählen und **Vorschau öffnen**.
   Die Vorschau berücksichtigt den aktuellen, auch ungespeicherten Entwurf sowie
   die HA-Entitätsrechte dieses Benutzers. Anschließend **Speichern** wählen.
   Eine HA-Einblendung bestätigt das Speichern. Versionsinfo, fehlende
   Receiver-Verbindung und nicht verfügbare HACS-Updates werden ausschließlich
   als DEBUG-Ausgaben protokolliert.

Fehlende oder inaktive Benutzer bleiben intern über ihre ID in bestehenden Freigaben
erhalten und werden ohne Anzeige der ID entsprechend gekennzeichnet. Die Zuordnung kann manuell
entfernt werden; daraus entsteht keine Freigabe für alle Benutzer.

## Verhalten auf dem Receiver

Der HA-Benutzer des am Receiver gespeicherten Tokens bestimmt die verfügbaren
Menüs. Verschiedene Tokens desselben Benutzers ergeben dieselbe Ansicht. Für
unterschiedliche Ansichten müssen Tokens unterschiedlicher HA-Benutzer verwendet
werden. Das gilt auch für Administrator-Tokens.

Ein verfügbares Menü öffnet sich direkt. Bei mehreren Menüs erscheint eine
Auswahl in der festgelegten Reihenfolge. Ist kein Menü verfügbar, zeigt der
Receiver einen entsprechenden Hinweis. Durch Filterung vollständig geleerte
Menüs verschwinden; bewusst leer angelegte Menüs bleiben sichtbar.

Freigaben und HA-Entitätsrechte gelten gemeinsam. Ohne Leserecht erscheint eine
Entität nicht, ohne Steuerrecht sind ihre Aktionen gesperrt. Menü, Zustände und
Aktionen werden serverseitig auf dieselbe Benutzeransicht begrenzt. Menüfreigaben
ändern keine Rechte für andere HA-APIs. Dieselbe Entität kann über einen anderen,
freigegebenen Eintrag weiterhin verfügbar sein.

Gespeicherte Änderungen greifen sofort für neue API-Anfragen. Die Receiver-Anzeige
aktualisiert sich beim nächsten erfolgreichen Abruf. Beim Wechsel von Token oder
HA-Adresse leert die aktuelle Receiver-Version vorherige Menüs und Zustände sofort.

## Bestehende Installationen

Das bisherige Menü wird beim ersten Laden der aktualisierten Integration
automatisch in die neue Menüsammlung übernommen und für alle Benutzer freigegeben.
Eintrags-IDs, Titel, Reihenfolge, Darstellung und Revision bleiben erhalten.
Die vorhandenen HA-Entitätsrechte gelten weiterhin. Die Konfiguration bleibt in
`.storage/enigmaha_companion.menu`; eine Neueinrichtung oder neue Tokens sind
nicht erforderlich.

Das Receiver-Menüformat bleibt Protokoll v1. Ältere Receiver erhalten bereits
gefilterte Menübäume; die bestehende Release-/Protokoll-Kompatibilitätsprüfung
gilt weiterhin. Die neue Receiver-Version ergänzt den Hinweis bei fehlender
Menüfreigabe und das sofortige Leeren beim Tokenwechsel.

Die bisherige Admin-Route `/config` bleibt für ein uneingeschränktes Einzelmenü
verwendbar. Sobald mehrere Menüs oder Benutzerbeschränkungen eingerichtet sind,
weist sie Zugriffe mit HTTP 409 `configuration_upgrade_required` zurück, damit
alte Editoren oder Werkzeuge keine Freigaben überschreiben. Dafür die neue Route
`/configuration` verwenden; Details stehen im [Protokoll](Protokoll-v1.md).
