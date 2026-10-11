# Menü- und Receiver-Protokoll v1

**Deutsch** · [English](Protocol.en.md)

Die HA-Integration und die Enigma2-Extension verwenden dieses Protokoll für
Menüdefinition, Zustandsabruf und Schaltaktionen. `schema_version: 1` bezeichnet
das Datenformat unabhängig von der Paketversion. Updateablauf und Grenzen
stehen in der [Entwicklerdokumentation](Entwicklung.md#updateablauf-und-grenzen).

## Komponenten- und Versionsprüfung

Receiver-Anfragen an `/menu`, `/states` und `/actions` senden
`X-EnigmaHA-Component: receiver`, `X-EnigmaHA-Version: MAJOR.MINOR.PATCH`
und `X-EnigmaHA-Protocol: 1`.
HA prüft die Header nach der Authentifizierung und vor dem Abruf bzw. Schalten.
Antworten der Companion-Views enthalten `X-EnigmaHA-Component: homeassistant`
und die eigene `X-EnigmaHA-Version` sowie `X-EnigmaHA-Protocol`. Der Receiver
prüft sie vor dem Verarbeiten erfolgreicher Antworten sowie bei HTTP 426.
Die Protokollversion ist unabhängig vom Release und wird nur bei inkompatiblen
Protokolländerungen erhöht. Gleiche Protokolle erlauben unterschiedliche Releases;
`version_mismatch` ist dann lediglich ein Hinweis mit Links zu den Release-Informationen.
Eine bloß gleiche Menü-`schema_version` ersetzt diese Prüfung nicht.

HTTP 426 meldet `protocol_mismatch` bei unterschiedlichem oder unbekanntem Protokoll oder
`unidentified_peer` bei fehlender/ungültiger Kennung oder Version; die JSON-Antwort
enthält zusätzlich die HA-`version` und `protocol_version`. Die Kennung dient der Kompatibilitätsprüfung,
nicht als Ersatz für HA-Authentifizierung oder TLS.

GET `/compatibility` ist Administratoren vorbehalten und liefert
`{"version": "1.0.2", "protocol_version": 1, "receivers": [], "updates": {...}}` mit der tatsächlich
geladenen HA-Paketversion. Receiver-Einträge enthalten `id` (ggf. `null`),
`address`, `version`, `protocol_version` (jeweils ggf. `null`) und `status`
(`compatible`, `version_mismatch`, `protocol_mismatch`, `unidentified_peer`). HA hält höchstens 64
Einträge der letzten fünf Minuten im Arbeitsspeicher, gruppiert nach HA-Benutzer
und `X-EnigmaHA-Receiver-ID` (32 kleingeschriebene Hex-Zeichen); ohne gültige ID
wird die Quelladresse verwendet. Die ID liegt dauerhaft auf dem Receiver.
Es findet kein aktiver Scan statt; die Liste bleibt im Arbeitsspeicher.

Protokollprobleme identifizierter Receiver mit gültiger ID werden zusätzlich unter
`.storage/enigmaha_companion.repairs` gespeichert und als native HA-Reparatur
angeboten. Der Repair-Flow verwendet die bestehende Updatekoordination; er startet
erst nach Bestätigung und setzt offene Vorgänge fort. Reine Release-Unterschiede
erzeugen keine Reparatur. Alte veröffentlichte Releases 1.0.0 bis 1.0.2 ohne
Protokollheader sind als Protokoll 1 bekannt; für andere Releases wird kein
Protokoll angenommen. Diese alten Komponenten verlangen selbst weiterhin gleiche
Releases und müssen für die neue Prüfung einmal auf beiden Seiten aktualisiert werden.

## Bestätigtes Release-Update

`updates` enthält `hacs` (Update-Entität oder `null`), `candidate` (geprüfter
Release mit zufälliger `id` oder `null`) und `job` (dauerhafter Vorgang oder `null`).
HACS wird über seine registrierte Update-Entität mit `INSTALL | SPECIFIC_VERSION`
angesprochen. Die folgenden Administrator-Anfragen an POST `/updates` liefern
jeweils den aktualisierten `updates`-Status; fachliche Fehler liefern HTTP 409.

| Anfrage | Wirkung |
| --- | --- |
| `{"action":"check"}` | Neuesten stabilen GitHub-Release und Assets prüfen; Auswahl zehn Minuten gültig |
| `{"action":"start","candidate_id":"…","receiver_ids":["…"]}` | Bestätigte Auswahl festschreiben; Receiver müssen kürzlich gemeldet sein |
| `{"action":"retry","job_id":"…"}` | Gescheiterte Schritte bzw. Ablehnungen für denselben Release erneut anbieten |
| `{"action":"restart","job_id":"…"}` | HA-Neustart erst nach Zielversion aller beteiligten Receiver anfordern |

Ein Release-Deskriptor enthält exakt `version`, `ipk_url`, `ipk_sha256` und
`ipk_size`. URLs müssen zum festen Repository, Tag `v<Version>` und erwarteten
IPK-Dateinamen passen. Nur veröffentlichte stabile Releases mit HACS-ZIP, IPK und
Prüfsummendatei werden angeboten. HACS erhält `update.install` mit explizitem
`version: v<Version>` und dem bestätigenden Administrator als Benutzerkontext.
Der native, nur Administratoren zugängliche Repair-Flow verwendet den HA-Systemkontext.
Der Release und die Receiverliste wechseln innerhalb eines Vorgangs nicht.

GET/POST `/receiver_update` verlangen einen aktiven authentifizierten HA-Benutzer,
Receiver-Kennung, gültige Version und Receiver-ID. Hier sind ungleiche Versionen
ausdrücklich erlaubt, ebenso unterschiedliche Protokolle. Bei Protokollproblemen
bleiben andere Receiver-Routen gesperrt. Ein Receiver
erhält nur den an seine ID **und** seinen HA-Benutzer gebundenen Vorgang.

GET liefert `{"job":null}` oder `{"job":{"id":"…","release":{...},
"status":"pending","attempt":1}}`. Nach lokaler Bestätigung meldet POST
`{"job_id":"…","attempt":1,"status":"installing","error":null}`;
weitere Meldungen sind `declined`, `restart_required` oder `failed` mit festen,
nicht sensitiven Fehlercodes. Erfolg ist `{"accepted":true}`. Veraltete
Vorgänge/Versuche werden mit `stale_update` abgewiesen. Eine `completed`-Meldung
wird nicht akzeptiert: Erst ein GET mit tatsächlich geladener Zielversion und Zielprotokoll
schließt den Receiver ab.

Vorgangsphasen: `ha_installing`, `receivers`, `ha_restart_required`, `completed`,
`failed`. Receiverstatus: `pending`, `installing`, `restart_required`, `completed`,
`declined`, `failed`. HA speichert den Vorgang getrennt vom Menü. Der Receiver
speichert die lokale Bestätigung vor dem Paketaufruf und prüft Paketgröße,
SHA-256, Paketmetadaten sowie anschließend `opkg status`. Bei unklarem
Installationsergebnis wird nicht automatisch erneut installiert. Weder
GitHub-Downloads noch Paketaufrufe erhalten den HA-Token. Neustarts verlangen
separate Bestätigung. `completed` setzt die tatsächlich laufende Zielversion
und das Zielprotokoll auf HA und allen beteiligten Receivern voraus. Das Zielprotokoll
wird aus den durch HACS installierten Quelldateien gelesen, unabhängig vom noch
laufenden HA-Prozess. Erst der beobachtete Abschluss entfernt die Repair-Meldung.

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
| GET `/compatibility` | HA-Version und kürzlich geprüfte Receiver; nur für Administratoren |

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
| 426 | `protocol_mismatch`, `unidentified_peer` |
| 500 | `service_failed`, beim Speichern `storage_failed` |
| 503 | Integration nicht geladen oder bereits entladen |

Die fachlichen Fehlerantworten haben die Form `{"error": "code"}`;
`invalid_menu` enthält zusätzlich `detail`. HTTP-Fehler aus Authentifizierung,
Verfügbarkeits- und Eingangsprüfung können davon abweichen. Anfragen über 1 MiB
werden mit HTTP 413 abgewiesen. Keine Tokens, Tracebacks oder internen URLs
an den Receiver zurückgeben. Der Client zeigt nur aus dem HTTP-Status
abgeleitete Fehler sowie geprüfte Komponenten-/Versionsheader an und verwirft
den Antworttext bei Fehlern.

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
