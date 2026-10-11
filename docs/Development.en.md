# Developing EnigmaHA Companion

[Deutsch](Entwicklung.md) · **English**

The project consists of a Home Assistant integration with a menu editor and
an Enigma2 extension. HA stores the shared menu and exposes states and actions
through authenticated HTTP routes. The receiver displays a remote-controlled menu.

Development and receiver testing target **OpenATV only**.
See [installation](Installation.en.md), [protocol](Protocol.en.md),
[releases](Releases.en.md), and [receiver skins](../enigma2/README.en.md).

## Project structure

| Path | Purpose |
| --- | --- |
| `custom_components/enigmaha_companion/` | HA integration, HTTP API, icon resolution and editor |
| `enigma2/Plugins/Extensions/EnigmaHACompanion/` | Enigma2 screens, settings, layout and icons |
| `enigma2/companion/` | GUI-independent navigation, translations and synchronous HTTP client |
| `protocol/enigmaha_protocol/` | Shared menu and command validation |
| `protocol/*.example.json` | Example menu and state response |
| `tests/` | Python and frontend tests |
| `tools/build.py` | Complete HA and receiver packages |
| `.github/workflows/release.yml` | Build, test and release workflow |

## Build and test locally

Release CI uses Python 3.13 and Node.js 24. Shipped receiver code must retain
Python 3.13-compatible syntax; Python 3.13 is the minimum receiver version.
Building requires only the Python standard library;
tests also need aiohttp and the npm dependencies in `package-lock.json`.

From the project root:

```console
python -m pip install -r requirements-test.txt
npm ci
python tools/build.py
python -m unittest discover -s tests -v
npm test
```

Build before running package and receiver tests. `dist/` contains both HA ZIPs,
the receiver IPK, an alternative TAR, checksums and unpacked package trees under
`dist/unpacked/`. Use these packages for installations: source folders alone do
not contain the bundled protocol modules.

Frontend dependencies may also be installed under `.work/node_modules/`.
Copy `package.json` and `package-lock.json` to `.work/`, then run
`npm ci --prefix .work --ignore-scripts`. Refresh the copies when dependencies
change. Tests prefer root `node_modules/`, falling back to `.work/node_modules/`.

## Development rules

[AGENTS.md](../AGENTS.md) contains the project rules. The project is published.
Consider backward compatibility with published versions and existing installations
when changing APIs, menu formats, stored configuration or internal interfaces.
Provide required migrations and briefly document them and any necessary
reconfiguration. Do not delete user data without authorization. Maintain support
for the current OpenATV and HA targets.

Do not commit credentials, `.local_info/`, `.work/` or `.temp/`. Keep files intended
for permanent local retention in `.local_info/` and leave existing files there.
Use `.work/` for disposable files created during work, including new update and
functional test reports. Reports intended for permanent local retention belong
in `.local_info/`. Run appropriate tests before delivery. Do not include reports
of executed tests or their results in changelogs, documentation or release notes.
Release notes describe user-visible changes first, followed by a brief account
of other changes without extensive technical detail.
Use native HA selectors with filters for entity selection.

## Home Assistant integration

The domain is `enigmaha_companion`. One configuration entry manages the menu for
all receivers. HA's `Store` persists it in `.storage/enigmaha_companion.menu`.
Saving validates the menu and permanently increments its revision.

Receiver access and administration are separate. Menu and state responses are
filtered by the authenticated user's read permissions. Missing control
permissions remove actions from an entry. Each command is checked again for
revision, entry, action, state and permissions, then executed with HA user context.
Menu updates and actions share a lock. Failed storage preserves the current
menu and revision. The editor and GET/PUT `/config` require administrator access.
Receiver credentials are not stored in the editor.

### Translations

German is the default and first choice. `panel.js` contains the English catalog;
`t()` translates German source messages and substitutes named placeholders.
The browser stores its choice under `enigmaha_companion.language`. Switching
preserves menu edits, navigation, drafts and filters. Storage failure leaves the
editor usable, but the choice cannot be persisted.

HA config dialogs use `translations/de.json` and `translations/en.json`,
following the HA profile language. Both catalogs are present in source and
packages, as required by [HA custom integration localization](https://developers.home-assistant.io/docs/internationalization/custom_integration/).
Native HA selector internals follow the HA profile language as well.

The receiver uses `companion/i18n.py` and local `language` (`de` or `en`, default
`de`). This covers navigation, help, settings and built-in skin text. Changes
apply on the next opening so the generated skin footer uses the same language.
Keep custom labels, entity IDs, raw protocol states and error codes unchanged.
Add new UI messages to the relevant catalog and retain the same placeholders in
both languages. The language update requires no reconfiguration.

### Menu editor

Entity selection uses native `ha-selector` components. Domain, area and device
class filters combine. An entity's own area takes precedence over its device's
area. Before adding, the entity must exist and match the filters. Filters never
modify saved entries.

The editor uses native HA cards, fields, buttons, state icons, dropdowns and
sorting. `ha-sortable` sorts within the current submenu; arrow buttons provide
the same action. The list scrolls near the edge during dragging. Wide screens
have separate menu and settings scroll areas; narrow screens use one view.
Preserve focus and scroll positions during updates.

The model changes ordering only after drop. Added entries are revealed while
respecting reduced-motion preferences. Confirmation dialogs protect unsaved
edits and nonempty submenus. Cancel, Escape and close cancel the pending action.
The editor derives `toggle` for `light`, `switch` and `input_boolean` when adding
and saving. Other domains remain read-only; server permissions remain authoritative.

### Entity icons

HA resolves MDI icons from its installed frontend, including state-dependent
icons and entity overrides. The response sends validated SVG path data rather
than arbitrary XML or URLs. The receiver renders temporary SVG files and removes
them after loading; up to 128 pixmaps are cached per screen. On is yellow and
off is grey. If rendering fails, state text remains visible. No MDI catalog is
bundled with the packages.

## Enigma2 extension

The synchronous HTTP client runs outside the GUI thread through Twisted
`deferToThread`. Callbacks update the display. Further actions are blocked while
a request or command runs. Closing or changing the connection invalidates older
responses. Periodic refresh runs only while the plugin is open.

Connection failure retains the last display marked OFFLINE. Toggle commands are
never automatically repeated, including after lost responses. HTTPS uses system
certificate verification, and redirects are rejected.

Local configuration is stored outside the plugin directory in
`/etc/enigma2/enigmaha_companion.json` with permissions `0600`.
[Receiver documentation](../enigma2/README.en.md) covers layout, font priorities,
skin interfaces and keys. Register further profiles once in `skin/__init__.py`'s
`PROFILES`; `skin/base.py` provides the common interface and `appearance.py` the layout.

## Update implementation and limitations

`PROTOCOL_VERSION` in `protocol/enigmaha_protocol/compatibility.py` is independent
of the release version and increases only for incompatible protocol changes.
Both packages receive the same protocol identity. Matching protocols with different
releases produce only an informational notice; normal communication remains allowed.

`repair_issues.py` manages persistent protocol issues and their confirmed update
job. The native HA wizard in `repairs.py` delegates installation, retry and restart
to the existing update coordinator. Closing the dialog only stops its progress
observer. HA's native repair API requires administrator access but does not pass
a user ID to flows; the wizard therefore uses the system context for HA services.

Update coordination lives in `updates.py`, portable release verification in
`protocol/enigmaha_protocol/releases.py`, and OpenATV installation in
`enigma2/companion/updater.py`. It uses the public
[HACS update entity](https://github.com/hacs/integration/blob/main/custom_components/hacs/update.py),
OpenATV's [`opkg`](https://github.com/openatv/enigma2/blob/master/lib/python/Components/Opkg.py)
and [`TryQuitMainloop`](https://github.com/openatv/enigma2/blob/master/lib/python/Screens/Standby.py).
Existing Python package dependencies also cover hashing, UUID and subprocesses;
`python3-netclient` pulls in `python3-crypt`.

The IPK's `postinst` recompiles the plugin's Python files with checked source
hashes at all optimization levels. Reproducible tar timestamps alone cannot
invalidate cached bytecode when a source change keeps the same file size:
the next GUI start can otherwise load the previous release.

### Testing guidance

Update tests cover pinned HACS versions, user/receiver binding, confirmation,
declines, checksums, package metadata, lost responses, storage failures,
interrupted installations and completion only after both sides run the target.
These automated tests replace HACS services and `opkg`. 

Automated tests cover menu validation, commands, real HTTP requests against test
servers, HA lifecycle and permissions, icon resolution, navigation, layouts,
package contents and metadata. HA services and receiver APIs use test doubles.
Receiver packages are checked for Python 3.13 syntax. Profile tests cover automatic
and manual selection, persistence, cancellation, reopening and missing resources.

Language tests check German defaults, English text, placeholders, persisted
preferences, state display and preservation of unsaved edits.

Frontend tests use jsdom and native-component doubles. They cover filters,
model changes, sorting, scroll calls and dialogs. They do not replace browser
checks for rendering, gestures and modal focus handling.

Before release, run the [functional check](Installation.en.md#functional-check)
on the OpenATV targets with HA. Record the steps and results under `.work/`.

## Separate HA test instance

With Docker and Compose, `python tools/ha_dev.py start` builds and installs the
complete integration in a separate HA instance at **http://127.0.0.1:18123**.
It completes HA onboarding and configures the integration and test menu
automatically. Fresh labs use the test login `enigma2ha:notsecret`.
Users, menu and database persist in a dedicated Docker volume. Virtual test
entities require no production credentials or devices.

Use `python tools/ha_dev.py check` to validate configuration, `logs` for logs and
`stop` to stop without deleting data. See the bilingual
[Docker setup guide](../dev/ha/README.md). HA Core development itself can use the
[official devcontainer environment](https://developers.home-assistant.io/docs/development_environment/);
this custom integration needs only the smaller HA Container setup.
