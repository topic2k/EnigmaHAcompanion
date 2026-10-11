# Menu and receiver protocol v1

[Deutsch](Protokoll-v1.md) · **English**

The HA integration and Enigma2 extension use this protocol for menus, state
retrieval and actions. `schema_version: 1` identifies the data format independently
of the package version. See [test status](Development.en.md#test-status-and-limitations).

## Menu

`protocol/enigmaha_protocol/menu.py` is the authoritative validator.
`protocol/menu.example.json` provides a complete example.

- `schema_version`: exactly integer 1; unknown versions are rejected.
- `revision`: positive integer up to 2147483647. HA increments it on each saved
  change and persists it; restarting does not reset it.
- `display`: `font_family` (1–64 characters) and `font_size` (16–64). Size is in
  pixels at a reference height of 720. The renderer scales it to the receiver
  display and falls back to `Regular`. Skin profiles may supply their own fonts;
  the portable core validates values and applies local overrides.
- `root`: menu with `type`, `id`, `label` and `children`.
- Entity entry: `type: entity`, `id`, `label`, `entity_id` and `actions`.
- `children` defines ordering and may mix menus and entities.
- IDs are unique throughout the document: 1–64 ASCII letters, digits, `_` or `-`.
- Labels contain 1–120 characters without control characters. The limit is
  500 nodes including the root and eight levels below the root.
- Unknown fields, duplicate IDs and unsupported actions are errors.
- The same HA entity may appear in several menus with different entry IDs.
- Empty menus are valid. Entities are selected in HA; subsequently deleted
  entities remain visible as missing entries.

v1 supports `toggle` for `light`, `switch` and `input_boolean`. Empty action
lists mean display only. Other domains are read-only. The editor derives actions
when adding and saving; the protocol also permits empty lists for toggleable
domains. Dimming, scenes and scripts are unsupported.

UI languages are local presentation choices. Labels are user content and are
not translated. Entity IDs, raw states, action names and error codes remain
language-independent; switching languages does not change the menu or revision.

## HTTP contract

Base: configured HA origin plus `/api/enigmaha_companion/v1`.
UTF-8 JSON; all routes require HA bearer authentication. The client limits
responses to 8 MiB including icon paths and rejects redirects. HTTPS uses system
certificate verification. HTTP is supported for local installations and
transmits the token without encryption. Store credentials only on the receiver.

| Method / route | Response / purpose |
| --- | --- |
| GET `/menu` | Validated menu including `revision` |
| GET `/states` | `schema_version`, `revision`, `states`, `icons` as in the example |
| POST `/actions` | Validate entry/action and call the corresponding HA service |
| GET `/config` | Complete menu; administrators only |
| PUT `/config` | Validate and save menu; administrators only |

PUT `/config` accepts the complete menu with its current revision. Validation
and saving share the action lock; revision increases by one. The response
contains the saved menu. A stale revision returns HTTP 409 (`stale_menu`).
Failed persistence leaves the current menu and revision unchanged.

`states` maps selected `entity_id` values to objects with `state` (string,
up to 255 characters), `unit_of_measurement` (string up to 64 characters or null),
and `icon` (MDI name or null). `icons` maps referenced MDI names to SVG `path`
data for a 24 × 24 viewBox. Duplicate icons are sent once per response. Names
consist of `mdi:` and 1–100 lowercase letters, digits or hyphens. Paths contain
at most 16384 characters and only SVG path commands, numbers and separators.
Arbitrary SVG/XML, URLs and executable content are excluded.

Icons are sent only for `on`/`off`. Nonexistent entities are omitted. `unknown`
and `unavailable` are actual HA states. Only selected entities readable by the
authenticated user are returned. A revision mismatch requires reloading the
menu before further actions.

Example command:

```json
{"schema_version": 1, "revision": 1, "entry_id": "ceiling", "action": "toggle"}
```

The receiver cannot choose arbitrary services, entity IDs or service data.
HA validates revision, entry, action list, control permission and current state.
`prepare_action` uses injected state and permission lookups; the HA adapter
supplies them and calls the service with user context. Menus do not grant permissions.

HTTP 200 with `{"accepted": true}` means the service call was accepted; it does
not guarantee the physical state. Reload states afterwards. On timeout, the
outcome is uncertain: check state and never repeat a toggle automatically.
The receiver blocks further actions while a request or command runs.

| HTTP | HA error codes |
| --- | --- |
| 400 | `invalid_request`, or `invalid_menu` for menu validation |
| 401 | `unauthorized` (HTTP authentication) |
| 403 | `forbidden`, `action_not_allowed` |
| 404 | `entry_not_found` |
| 409 | `stale_menu`, `entity_unavailable`, or `revision_limit` when saving |
| 500 | `service_failed`, or `storage_failed` when saving |
| 503 | Integration not loaded or already unloaded |

Application errors use `{"error": "code"}`; `invalid_menu` additionally includes
`detail`. Authentication, availability and request-validation HTTP errors may
differ. Requests over 1 MiB return HTTP 413. Do not return tokens, tracebacks or
internal URLs. The client discards error response bodies and displays messages
derived from HTTP status.

## Implementation

The HA integration provides entity selection, nested menus, revisioned storage,
authenticated routes, permissions and atomic revision checks before service calls.
The menu endpoint removes unreadable entities and clears actions without control
permission. Empty submenus are retained. Menu editing requires an administrator.

The Enigma2 extension provides screens, ActionMap, threaded HTTP, GUI callbacks,
refresh while open, stale-response rejection, offline status, font resolution,
local configuration and packaging. The synchronous client runs through Twisted
`deferToThread` outside the GUI thread.

References: [HA REST API](https://developers.home-assistant.io/docs/api/rest/),
[HA authentication](https://developers.home-assistant.io/docs/auth_api/),
[integration structure](https://developers.home-assistant.io/docs/creating_integration_file_structure/).
The custom routes and menu format are project decisions, separate from HA's
official API. The build includes the shared protocol in both packages.
