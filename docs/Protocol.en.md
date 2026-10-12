# Menu and receiver protocol v1

[Deutsch](Protokoll-v1.md) · **English**

The HA integration and Enigma2 extension use this protocol for menus, state
retrieval and actions. `schema_version: 1` identifies the data format independently
of the package version. See [update implementation and limitations](Development.en.md#update-implementation-and-limitations).

## Component and version checks

Receiver requests to `/menu`, `/states` and `/actions` send
`X-EnigmaHA-Component: receiver`, `X-EnigmaHA-Version: MAJOR.MINOR.PATCH`
and `X-EnigmaHA-Protocol: 1`.
HA checks these headers after authentication and before reading data or executing
an action. Companion view responses include `X-EnigmaHA-Component: homeassistant`
and the local `X-EnigmaHA-Version` and `X-EnigmaHA-Protocol`. The receiver checks
successful responses and HTTP 426 before processing their payload. Protocol versions
are independent of releases and increase only for incompatible protocol changes.
Matching protocols allow different releases; `version_mismatch` is an informational
notice with release-note links. Matching menu `schema_version` values alone are insufficient.

HTTP 426 reports `protocol_mismatch` for different or unknown protocols or `unidentified_peer`
for missing/invalid identity or version headers. Its JSON response also includes
the HA `version` and `protocol_version`. This identity check does not replace HA authentication or TLS.

Administrator-only GET `/compatibility` returns
`{"version": "1.0.2", "protocol_version": 1, "receivers": [], "updates": {...}}` with HA's actually
loaded package version. Receiver entries contain `id` (possibly `null`),
`address`, `version`, `protocol_version` (each possibly `null`) and `status`
(`compatible`, `version_mismatch`, `protocol_mismatch`, `unidentified_peer`). HA keeps at most 64 entries
from the last five minutes in memory, grouped by HA user and
`X-EnigmaHA-Receiver-ID` (32 lowercase hexadecimal characters), falling back to
source address without a valid ID. The receiver persists its identity.
There is no active scan; the recent list is not persisted.

Protocol problems for identified receivers with valid IDs are additionally persisted
in `.storage/enigmaha_companion.repairs` and offered as native HA repairs. The repair
flow uses the existing update coordinator, installs only after confirmation and resumes
unfinished jobs. Release differences alone never create repairs. Published releases
1.0.0 through 1.0.2 without a protocol header are known to implement protocol 1;
unknown releases never receive an assumed protocol. Those old components still require
matching releases themselves; update both sides once to enable the new checks.

## Confirmed release update

`updates` contains `hacs` (update entity or `null`), `candidate` (verified release
with random `id` or `null`) and `job` (persisted transaction or `null`). HACS is
accessed through its registered update entity with `INSTALL | SPECIFIC_VERSION`.
Administrator POST requests to `/updates` return the updated `updates` snapshot;
application errors return HTTP 409.

| Request | Effect |
| --- | --- |
| `{"action":"check"}` | Verify the latest stable GitHub release and assets; selection valid for ten minutes |
| `{"action":"start","candidate_id":"…","receiver_ids":["…"]}` | Pin confirmed release and recently seen receiver identities |
| `{"action":"retry","job_id":"…"}` | Offer failed steps or declined updates again for the same release |
| `{"action":"restart","job_id":"…"}` | Request HA restart only after all participants run the target |

A release descriptor contains exactly `version`, `ipk_url`, `ipk_sha256` and
`ipk_size`. URLs must match the fixed repository, `v<Version>` tag and expected
IPK filename. Only published stable releases with HACS ZIP, IPK and checksums
are offered. HACS receives `update.install` with explicit `version: v<Version>`
and the confirming administrator's context. The native administrator-only repair
flow uses HA's system context. The release and participant list
remain fixed throughout a transaction.

GET/POST `/receiver_update` require an authenticated active HA user, receiver
component header, valid version and receiver identity. Different versions are
explicitly allowed here, as are different protocols. Protocol mismatches block
normal receiver routes. Receivers only
receive transactions bound to both their identity **and** their HA user.

GET returns `{"job":null}` or `{"job":{"id":"…","release":{...},
"status":"pending","attempt":1}}`. After local confirmation, POST reports
`{"job_id":"…","attempt":1,"status":"installing","error":null}`.
Other reports are `declined`, `restart_required` or `failed` with fixed,
non-sensitive error codes. Success returns `{"accepted":true}`. Stale jobs or
attempts return `stale_update`. A `completed` report is rejected; only a GET
reporting the actually loaded target version and protocol completes that receiver.

Job phases: `ha_installing`, `receivers`, `ha_restart_required`, `completed`,
`failed`. Receiver statuses: `pending`, `installing`, `restart_required`,
`completed`, `declined`, `failed`. HA stores progress separately from the menu.
The receiver persists local consent before invoking the package manager, checks
size, SHA-256 and package metadata, then verifies `opkg status`. An uncertain
installation is never automatically repeated. GitHub downloads and package
commands never receive the HA token. Restarts require separate confirmation.
Completion requires HA and every participant to actually run the target version and
protocol. The target protocol is read from source files installed by HACS, independently
of the still-running HA process. Repair issues clear only after observed completion.

## Menu

`protocol/enigmaha_protocol/menu.py` is the authoritative validator.
`protocol/menu.example.json` provides a complete example.

- `schema_version`: exactly integer 1; unknown versions are rejected.
- `revision`: positive integer up to 2147483647. HA increments it on each saved
  change and persists it; restarting does not reset it.
- `display`: `font_family` (1–64 characters) and `font_size` (16–64). Size is in
  pixels at a reference height of 720 for older renderers, which scale it to the
  display and fall back to `Regular`. These fields remain for compatibility with
  older receivers. Current receivers still validate the document but render using
  local font settings only: auto follows the skin or receiver profile, while
  explicit choices take precedence.
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

## Menu collections and user access

Admin/storage configuration uses `schema_version: 2`, `revision`, `display` and
`menus`, an ordered array of complete menu roots. Receiver transport remains
`schema_version: 1` with `root`. Each menu or entity node may additionally
contain `access`:

| Rule | Meaning |
| --- | --- |
| `{"mode":"all"}` | All users; complete menu roots only |
| `{"mode":"inherit"}` | Inherit from parent; child nodes only |
| `{"mode":"users","users":["ha-user-id"]}` | Listed users; an empty list grants nobody access |
| `{"mode":"none"}` | Disabled for all users |

Missing `access` defaults to `all` on roots and `inherit` on children. Only
`users` mode can contain `users`. User IDs are unique and contain 1–64 ASCII
letters, digits, `_` or `-`. Missing/inactive user IDs may remain stored. Every
ancestor restriction and HA entity permissions also apply, including to
administrator receiver tokens. These rules do not change other HA API permissions.

Entry IDs are unique across the collection. Existing receiver size/depth limits
include the additional selection root for multiple menus: at most 500 nodes
and eight levels below the receiver root. Display settings and revision are
shared by all menus. Empty collections are valid.

PUT `/configuration` shares the action lock, increments the revision and returns
the saved collection. A stale revision returns HTTP 409 `stale_menu`; an exhausted
counter returns `revision_limit`. Invalid input returns HTTP 400 `invalid_menu`;
storage failures return HTTP 500 `storage_failed` without changing live data.
v1 documents are also accepted and converted into a collection. Stored v1 menus
are automatically converted on load under the same storage key, preserving IDs,
appearance and revision. No reconfiguration is required. GET/PUT `/config` remain
available only for exactly one unrestricted menu; otherwise they return HTTP 409
`configuration_upgrade_required`.

POST `/preview` accepts `{"configuration": {...}, "user_id": "…"}` and filters
the draft using the active user's current HA permissions without saving it.
Missing, inactive or system-generated users return HTTP 404 `user_not_found`.

Menus, previews, states and actions use the same user projection. One available
root is returned directly; multiple roots are grouped beneath a generated
selection root. With no available menu, an empty root with ID
`__enigmaha_no_menu` is returned. Menus emptied by filtering disappear;
originally empty menus remain. Access rules and user IDs are never sent to
receivers. Invisible action IDs return HTTP 404 `entry_not_found`.
See the [user guide](User-menus.en.md) for editor instructions.

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
| GET `/config` | Unrestricted single menu in the original format; administrators only |
| PUT `/config` | Save an unrestricted single menu; administrators only |
| GET `/configuration` | Complete menu collection with access rules; administrators only |
| PUT `/configuration` | Validate and save the collection; administrators only |
| GET `/users` | Active, non-system HA users as `{"users":[{"id":"…","name":"…"}]}`; administrators only |
| POST `/preview` | Draft user view as a v1 menu; administrators only |
| GET `/compatibility` | HA version and recently checked receivers; administrators only |

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
| 426 | `protocol_mismatch`, `unidentified_peer` |
| 500 | `service_failed`, or `storage_failed` when saving |
| 503 | Integration not loaded or already unloaded |

Application errors use `{"error": "code"}`; `invalid_menu` additionally includes
`detail`. Authentication, availability and request-validation HTTP errors may
differ. Requests over 1 MiB return HTTP 413. Do not return tokens, tracebacks or
internal URLs. The client discards error response bodies and displays messages
derived from HTTP status and validated component/version headers.

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
