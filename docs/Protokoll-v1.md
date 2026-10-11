# Menü- und Receiver-Protokoll v1

Die HA-Integration und die Enigma2-Extension verwenden dieses Protokoll für
Menüdefinition, Zustandsabruf und Schaltaktionen. `schema_version: 1` bezeichnet
das Datenformat unabhängig von der Paketversion. Teststand und bekannte Grenzen
stehen in der [Entwicklerdokumentation](Entwicklung.md#teststand-und-grenzen).

## Menü

Die maßgebliche Validierung liegt in `protocol/enigmaha_protocol/menu.py`.
`protocol/menu.example.json` enthält ein vollständiges Beispiel.

- `schema_version`: exakt die Ganzzahl 1; unbekannte Versionen werden abgewiesen.
- `revision`: positive Ganzzahl bis 2147483647. HA erhöht sie bei jeder gespeicherten
  Änderung und speichert sie dauerhaft mit dem Menü. Kein Zurücksetzen bei Neustart.
- `display`: `font_family` (1–64 Zeichen) und `font_size` (16–64).
  Die Größe entspricht Pixeln bei einer Referenzhöhe von 720 Pixeln. Der
  Receiver-Renderer skaliert mit seiner Höhe und verwendet bei fehlender Schrift
  `Regular`. Ein Skin-Profil kann eigene Schriftvorgaben setzen; der portable Kern
  prüft Werte und verarbeitet lokale Überschreibungen.
- `root`: Menü mit `type`, `id`, `label` und `children`.
- Entitätseintrag: `type: entity`, `id`, `label`, `entity_id`, `actions`.
- `children` bestimmt die Reihenfolge; Menü- und Entitätseinträge dürfen gemischt sein.
- Alle IDs sind dokumentweit eindeutig, 1–64 ASCII-Buchstaben, Ziffern, `_` oder `-`.
- Labels enthalten 1–120 Zeichen und keine Steuerzeichen. Maximal 500 Knoten
  einschließlich Wurzel, maximal acht Ebenen unterhalb der Wurzel.
- Unbekannte Felder, doppelte IDs und nicht unterstützte Aktionen sind Fehler.
- Dieselbe HA-Entität darf in mehreren Menüs vorkommen, mit unterschiedlichen IDs.
- Leere Menüs sind zulässig. Bestehende Entitäten werden bei der HA-Konfiguration
  ausgewählt; später gelöschte Entitäten bleiben im Menü sichtbar als fehlend.

v1 unterstützt `toggle` für `light`, `switch` und `input_boolean`. Eine leere
Aktionsliste bedeutet nur Anzeige. Alle anderen Domains sind in diesem Stand
ausschließlich lesbar. Der HA-Editor leitet die Aktionen beim Hinzufügen und
Speichern automatisch aus der Domain ab. Das Protokoll erlaubt auch eine leere
Aktionsliste für diese Domains. Dimmen, Szenen und Scripts werden nicht unterstützt.

## HTTP-Vertrag

Basis: die konfigurierte HA-Origin plus `/api/enigmaha_companion/v1`.
JSON in UTF-8; jede Route verlangt HA-Bearer-Authentifizierung. Antwortlimit des
Clients: 8 MiB einschließlich der Symbolpfade. Redirects werden nicht verfolgt. HTTPS prüft Zertifikate mit den
Systemvorgaben. HTTP wird für lokale Installationen unterstützt und überträgt
den Token unverschlüsselt. Zugangsdaten gehören nur in lokale Receiver-Konfiguration.

| Methode / Route | Antwort / Bedeutung |
| --- | --- |
| GET `/menu` | Validierte Menüdefinition einschließlich `revision` |
| GET `/states` | `schema_version`, `revision`, `states`, `icons` nach Beispiel |
| POST `/actions` | Prüft Eintrag/Aktion und ruft den passenden HA-Service auf |
| GET `/config` | Vollständige Menüdefinition; nur für Administratoren |
| PUT `/config` | Menü validieren und speichern; nur für Administratoren |

PUT `/config` erwartet die vollständige Menüdefinition mit der aktuellen
Revision. Die Integration prüft und speichert sie unter derselben Sperre wie
Schaltaktionen und erhöht die Revision um eins. Die Antwort enthält das
gespeicherte Menü. Bei einem veralteten Stand antwortet sie mit HTTP 409
(`stale_menu`). Schlägt die Speicherung fehl, bleiben Menü und Revision unverändert.

`states` ist eine Map von konfigurierten `entity_id` zu Objekten mit `state`
(String, maximal 255 Zeichen), `unit_of_measurement` (String bis 64 Zeichen
oder null) und `icon` (MDI-Name oder null). `icons` ordnet den referenzierten
MDI-Namen ihren SVG-`path`-Daten für eine ViewBox von 24 × 24 zu. Gleiche Symbole
werden pro Antwort nur einmal übertragen. Namen bestehen aus `mdi:` und 1–100
Kleinbuchstaben, Ziffern oder Bindestrichen; Pfade sind auf 16384 Zeichen begrenzt
und dürfen ausschließlich SVG-Pfadbefehle, Zahlen und Trennzeichen enthalten.
Freies SVG/XML, URLs und ausführbare Inhalte sind nicht Teil des Protokolls.
Symbole werden nur bei `on`/`off` übertragen. Nicht existierende Entitäten fehlen
in der Map. `unknown` und
`unavailable` sind tatsächliche HA-Zustände. Die HA-Seite liefert nur für den
authentifizierten Benutzer lesbare, im Menü ausgewählte Entitäten. Ein abweichender
Revisionsstand erfordert ein Neuladen des Menüs vor weiteren Aktionen.

Beispiel für einen Befehl:

```json
{"schema_version": 1, "revision": 1, "entry_id": "ceiling", "action": "toggle"}
```

Der Receiver sendet keine frei wählbaren Service-Namen, Entity-IDs oder Service-Daten.
Die HA-Seite prüft die aktuelle Revision, den Eintrag, dessen Aktionsliste, die
Steuerungsberechtigung des angemeldeten Benutzers und den aktuellen Zustand.
`prepare_action` implementiert diese Prüfungen mit injizierten Zustands- und
Berechtigungsabfragen. Die HA-Anbindung führt diese gegen HA aus und ruft
den Service mit Benutzerkontext auf. Ein Menü ersetzt keine HA-Berechtigung.

Erfolg: HTTP 200 mit `{"accepted": true}` bedeutet, dass der Service-Aufruf angenommen
wurde; der physische Zielzustand ist damit noch nicht garantiert. Danach Zustände
neu laden. Bei Timeout ist der Ausgang unklar: Zustand prüfen und niemals einen
Toggle-Befehl automatisch wiederholen. Während ein Abruf oder Befehl läuft,
blockiert das Receiver-UI weitere Schaltaktionen.

| HTTP | Fehlercode der HA-Seite |
| --- | --- |
| 400 | `invalid_request`, bei Menüvalidierung `invalid_menu` |
| 401 | `unauthorized` (HTTP-Authentifizierung) |
| 403 | `forbidden`, `action_not_allowed` |
| 404 | `entry_not_found` |
| 409 | `stale_menu`, `entity_unavailable`, beim Speichern `revision_limit` |
| 500 | `service_failed`, beim Speichern `storage_failed` |
| 503 | Integration nicht geladen oder bereits entladen |

Die fachlichen Fehlerantworten haben die Form `{"error": "code"}`;
`invalid_menu` enthält zusätzlich `detail`. HTTP-Fehler aus Authentifizierung,
Verfügbarkeits- und Eingangsprüfung können davon abweichen. Anfragen über 1 MiB
werden mit HTTP 413 abgewiesen. Keine Tokens, Tracebacks oder internen URLs
an den Receiver zurückgeben. Der Client zeigt nur aus dem HTTP-Status
abgeleitete Fehler an und verwirft den Antworttext bei Fehlern.

## Implementierung

Die HA-Integration unter `custom_components/enigmaha_companion/` enthält eine
Konfigurationsoberfläche für Entitätsauswahl und verschachtelte Menüs,
persistente Speicherung mit Revision, authentifizierte Routen, Lese- und
Steuerungsberechtigungen und atomare Prüfung der Revision vor Service-Aufruf.
Menükonfiguration bleibt HA-Administratoren vorbehalten. Der Menü-Endpunkt filtert
nicht lesbare Einträge; leere Untermenüs bleiben bestehen. Bei fehlenden
Steuerungsrechten wird die Aktionsliste des Eintrags geleert.

Die Enigma2-Extension unter `enigma2/` enthält Screen und ActionMap,
Hintergrundarbeit für HTTP, Rückkehr zum GUI-Thread
für Anzeigeänderungen, periodische Aktualisierung nur bei offenem Menü,
Abbruch/Verwerfen alter Antworten beim Schließen, Statuskennzeichnung bei
Verbindungsfehlern, Schriftauflösung, lokale Konfiguration und Paketierung.
Der HTTP-Client ist synchron und läuft über Twisted `deferToThread` außerhalb
des GUI-Threads.

## Quellen

- [HA REST-API](https://developers.home-assistant.io/docs/api/rest/)
- [HA-Authentifizierung](https://developers.home-assistant.io/docs/auth_api/)
- [Struktur einer HA-Integration](https://developers.home-assistant.io/docs/creating_integration_file_structure/)

Die eigenen Routen und das Menüformat sind Projektentscheidungen; sie sind kein
Bestandteil der offiziellen HA-API.

Die [Installationsanleitung](Installation.md) beschreibt die Einrichtung beider
Komponenten. Der Build bindet das gemeinsame Protokollmodul in beide Pakete ein.
