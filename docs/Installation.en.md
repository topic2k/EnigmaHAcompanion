# Installation and usage

[Deutsch](Installation.md) · **English**

EnigmaHA Companion connects Home Assistant to your Enigma2 receiver. Configure
the menu in HA and use it on your TV with the remote. Install both the integration
and the receiver plugin from the same release. The packages include all
project-specific modules; no additional server or MQTT broker is required.

## Requirements

- Home Assistant with administrator access for installation and the menu editor.
- For the recommended installation: HACS and a published
  [EnigmaHA release](https://github.com/topic2k/EnigmaHAcompanion/releases).
- OpenATV with Enigma2, Python 3.13 or newer, and Twisted. Python 2 images are
  unsupported. Use an HD or Full HD skin.
- Network access from the receiver to the HA address.
- A long-lived HA access token belonging to an active user with read and control
  permissions for the selected entities. A regular user is sufficient for the
  receiver; the menu editor requires an administrator.

See [update implementation and limitations](Development.en.md#update-implementation-and-limitations).

## 1. Install Home Assistant integration

### Through HACS (recommended)

1. Open **HACS → ⋮ → Custom repositories**.
2. Add `https://github.com/topic2k/EnigmaHAcompanion` with category **Integration**.
3. Find and download **EnigmaHA Companion**.
4. Restart Home Assistant.
5. Open **Settings → Devices & services → Add integration → EnigmaHA Companion**.
6. Open **EnigmaHA Companion** in the sidebar.

### Manually through ZIP

Download `enigmaha-companion-ha-<Version>.zip` from the
[releases](https://github.com/topic2k/EnigmaHAcompanion/releases).
The separate `enigmaha_companion.zip` is intended for HACS.

1. Extract the versioned ZIP.
2. Copy its `custom_components/enigmaha_companion` folder into your HA
   configuration directory. The resulting path must be
   `<HA configuration>/custom_components/enigmaha_companion/manifest.json`.
   On HA OS, the configuration directory is usually `/config`.
3. Restart HA and add the integration under **Settings → Devices & services**.
4. Open **EnigmaHA Companion** in the sidebar.

## 2. Build the menu

Both sides check the EnigmaHA identity, release and protocol version on every
receiver request. Different releases work when their protocols match; the HA
editor displays an informational notice and release-note links. Different or
unknown protocols and missing/invalid identities block requests and actions.
The receiver displays an explanation; the HA
editor shows requests from the last five minutes and refreshes this status every
30 seconds. A receiver must connect before it can be checked.

The [coordinated update](#coordinated-update-through-hacs-and-ipk) brings HA and
participating receivers to the same release after confirmation. Menus, receiver
settings and tokens are retained; no reconfiguration is required.

A protocol conflict also creates an issue under **Settings → System → Repairs**.
The wizard shows the target release and affected receivers and uses the same
IPK workflow after confirmation. Older receivers update to the running HA version;
HA itself is neither updated nor restarted. Issues survive HA restarts and clear
only after successful verification. Older receivers with compatible protocols
get an optional **Receiver update available** repair. Choose **Fix** to open the
update wizard; communication remains available. Compatible receivers running
the same or a newer release do not get an update offer. Published versions through 1.0.2 still enforce matching
releases themselves; update both components once to enable independent protocol checks.

Open **Settings → Devices & services → EnigmaHA Companion → Configure** and
choose **English** under **Menu editor language**. New installations default to **Automatic**;
existing language preferences are retained.
**Automatic** follows the HA profile language, falling back to the first supported
browser language. Regional variants such as `en-GB` are recognized; German is
used if no supported language is available.
The choice applies to all browsers. An open editor picks it up within 30 seconds
and preserves unsaved edits. On existing installations, until this option is first saved, a browser
language preference remains in use. No reconfiguration is required and menu names
remain unchanged. HA setup dialogs and the internal texts of
native selectors follow your HA profile language.

The integration options contain only this language setting. Set the font family
and size on each receiver; these choices are not available in HA.

1. Add and open submenus as needed.
2. Search for an HA entity, select it and choose **Add entity**. Filter by entity
   type, area or device class to narrow the selection.
3. Edit display names and reorder entries with the drag handle or up/down arrows.
   Drag near the list's edge to scroll automatically.
4. Edit menu titles directly in the menu overview. Set the font family and size
   only on each receiver.
5. Choose **Save**.

Lights, switches and `input_boolean` helpers are configured as toggleable.
Other entities are read-only. The receiver user still needs HA permissions.
Your own menu and entity names are never automatically translated.

Use **Manage menus** to create shared and personal menus. **Access** restricts
complete menus, submenus or individual entries to selected HA users. The user
of the receiver token determines its view. See [user-specific menus](User-menus.en.md)
for setup, preview and automatic conversion of existing menus. HA manages the configuration in
`.storage/enigmaha_companion.menu`; do not edit that file while HA is running.

## Update indicator in Home Assistant

The integration provides the `update.enigmaha_companion` update entity. It shows
the integration version actually running, the latest complete stable release and
a link to its release information. It checks when the integration loads and every
twelve hours afterwards. Use `homeassistant.update_entity` to request a manual
check. The indicator needs GitHub internet access but does not require HACS.
If a check fails, the entity becomes unavailable while the local receiver menu
remains usable. A later successful check restores the indicator.

Use **Install** on this entity or `update.install` to update only Home Assistant.
Receivers do not participate and do not need to be connected. Administrator
privileges and an active HACS update entity are required. Automations can call
the service in the system context.
This entity does not support selecting a specific version or the backup option.

HA updates to the offered release through HACS. Use the EnigmaHA editor to follow
progress, retry steps and confirm the final HA restart. The entity indicates an
ongoing update and keeps its target version fixed. If a newer release is published
between displaying and installing the update, review and confirm the refreshed
offer. Until HA restarts, it continues to show the loaded version even if newer
files are already installed. Existing configurations and update jobs need no
migration or setup changes. The existing HACS update entity remains separate.
After restarting HA, older receivers are detected on their next request.
Incompatible protocols create an error repair; compatible protocols create an
optional update repair. HA persistent notifications do not provide arbitrary
action buttons, so **Fix** in the repair opens the wizard. It offers the release
running in HA without requiring HACS. Open EnigmaHA Companion on each
participating receiver and keep it open. Update jobs are retrieved only while
the plugin is open; no installation prompt appears while watching TV. Confirm
IPK installation in the plugin, then confirm the GUI restart.

For compatible protocols, the repair dialog also offers **Ignore for version …**.
This completes the repair without updating the receiver. The decision survives
HA restarts and applies only to the offered HA version and the receiver versions
shown. A new version offer creates another notice; incompatible protocols still
require repair. Ignoring ends an existing job whose installation has not started.
Running or uncertain installations and pending GUI restarts must be resolved or
completed first. Existing configurations need no migration or setup changes.

## Update directly from a version conflict

When the receiver reports a version or protocol conflict and HA runs a newer
release, the dialog offers **Update receiver to …**. Select it, confirm the
verified package installation, then confirm the GUI restart. The receiver
downloads the exact published stable release running in HA and checks package
metadata, size and SHA-256. An incomplete or unavailable release cannot be
installed. Downgrades remain blocked.

An update already offered by HA continues through the existing coordinated
workflow. Without such a job, only the receiver is updated; GitHub access and
root permissions on OpenATV are required. A pending GUI restart is offered
again when reopening the plugin, even when HA is unavailable. This also applies
to updates started through HA. The receiver checks its local package state and
does not install the package again. Once HA is reachable, the version actually
running is reconciled. Existing settings and update journals remain
usable; no migration or setup changes are required.

## Coordinated update through HACS and IPK

Both components must first run a version containing this update workflow. Update
older installations through HACS and the IPK from the same release, then restart
HA and the receiver GUI. For an existing ZIP installation, configure EnigmaHA in
HACS first.

Requirements: an active HACS update entity for this repository, GitHub internet
access from HA and each receiver, and root permissions for OpenATV's `opkg`.
The receiver still uses its regular HA user token. HTTPS certificate verification
remains enabled; no SSH credentials are required.

1. Open the plugin on all participating receivers and keep it open until
   confirming installation. The HA editor lists receiver
   requests from the last five minutes. Offline receivers are not discovered or
   included automatically.
2. Choose **Check for updates** in the HA editor. It offers the latest published
   stable release containing the HACS ZIP, IPK and `SHA256SUMS.txt`.
3. Choose **Update both to …** and confirm the target version and receiver list.
   The selection expires after ten minutes. HACS installs that exact version;
   the release and participating receivers stay fixed for this transaction.
4. Confirm IPK installation on each receiver. The plugin downloads the matching
   package, checks size, SHA-256, package name and version, then installs through
   `opkg`. Nothing is installed on the receiver before this confirmation.
5. Confirm the offered **GUI restart** on each receiver. OpenATV's native restart
   check considers active recordings. After restarting, the plugin reports its
   actual loaded version to HA.
6. Once every participating receiver reports the target, confirm **Restart Home
   Assistant** in the HA editor. Save unsaved menu changes first, then reload the
   HA page after restarting. Completion requires HA itself to run the target too.

A declined receiver update can be offered again in the HA editor and requires
another local confirmation. Different protocols continue to block menu requests
and actions; the update channel remains available. HA stores progress in
`.storage/enigmaha_companion.update`. Receiver identity and installation journal
are stored in `/etc/enigma2/enigmaha_companion_receiver_id` and
`/etc/enigma2/enigmaha_companion_update.json`. Do not edit these during an update.

Lost connections do not cause a second IPK installation. If an `opkg` result is
uncertain, inspect package status on the receiver; uncertain installations are
not retried automatically. A missing GUI restart is offered again. Downgrades
are blocked. Do not install another version through HACS or `opkg` during the
transaction. Update other receivers later; mismatched protocols keep them blocked.
Manual installation of both packages from
the same release remains available.

The repair wizard resumes unfinished update jobs and offers failed steps again
after renewed confirmation. Uncertain installation results require manual inspection.
Confirm HA restart separately. Every participant must report the target release
and its protocol before the repair completes. Additional repair data is kept
separately from the menu in `.storage/enigmaha_companion.repairs`.

## Create a long-lived access token

The receiver authenticates with a **long-lived access token** and uses the
permissions of the user who created it.

1. Sign in to HA as the intended receiver user, who needs read permissions and,
   for toggleable entities, control permissions.
2. Click the **username or profile picture** at the bottom of the HA sidebar.
3. Open **Security**, scroll to **Long-lived access tokens**, and choose **Create token**.
4. Enter a recognizable name such as **EnigmaHA Living Room** and confirm.
5. Copy the complete token immediately and store it securely. You cannot display
   it again after closing the dialog.
6. Enter it in the receiver settings or its configuration file. The HA menu
   editor does not need it.

If you lose the token, create a new one. To revoke receiver access, delete the
corresponding token in HA. See [HA authentication](https://www.home-assistant.io/docs/authentication/)
and [long-lived tokens](https://developers.home-assistant.io/docs/auth_api/#long-lived-access-token).

## 3. Install the receiver plugin

Download `enigma2-plugin-extensions-enigmahacompanion_<Version>_all.ipk` from
the same release as the HA integration.

### Install the IPK through OpenWebif

1. Open the powered-on receiver in your browser, for example at
   `http://192.168.1.30`. Use your own receiver address and sign in if required.
2. On the receiver, open **Plugins → OpenWebif**, enable **Allow IPK upload**
   if necessary, and save.
3. Reload OpenWebif in the browser and open **Packages**. Depending on the view,
   it may be under **Extras**.
4. Open the upload function and upload the downloaded EnigmaHA IPK.
5. Select the uploaded package and choose **Install**. Uploading alone does not
   install the plugin.
6. Wait for successful installation. Resolve any error before continuing.
7. **Restart the user interface/GUI** from the receiver menu, then open
   **Plugins → EnigmaHA Companion**.

If your OpenWebif version has no upload function, use SSH below. The
[OpenATV manual](https://openatv.github.io/enigma2-doku/de/netzwerk/openwebif/werkzeuge/)
also documents package management and upload permissions (in German).

### Install the IPK over SSH

Copy the IPK to `/tmp` on the receiver. Keep only the intended EnigmaHA IPK
there, then run over SSH:

```sh
opkg install /tmp/enigma2-plugin-extensions-enigmahacompanion_*_all.ipk
```

Restart the GUI and open **Plugins → EnigmaHA Companion**. The plugin also
appears in the extensions menu where supported by the image.

Install missing dependencies from the image's feed. The IPK requires `enigma2`,
`python3-core (>= 3.13)`, `python3-json`, `python3-netclient`, `python3-io`, and
`python3-twisted-core`. Do not bypass dependencies with `--force-depends`.

### Alternative: manual TAR package

First check the required modules on the receiver:

```sh
python3 -c "import json, ssl, urllib.request; from twisted.internet.threads import deferToThread"
```

Copy `enigmaha-companion-enigma2-<Version>.tar.gz` to `/tmp`, replace `<Version>`
with the downloaded version, and run:

```sh
tar -xzf /tmp/enigmaha-companion-enigma2-<Version>.tar.gz -C /
```

The archive contains only
`/usr/lib/enigma2/python/Plugins/Extensions/EnigmaHACompanion/`.
Restart the GUI afterwards.

## 4. Configure the receiver

Settings open automatically on first launch. Later, press **Menu/Blue**.
New installations default to **Automatic**. Existing language choices are retained;
older configuration files without `language` keep German. Choose **English** under **Sprache**, press
**Green**, then close and reopen the plugin to apply the language.

| Setting | Meaning |
| --- | --- |
| Language | **Deutsch**, **English** or **Automatic** (default for new installations, OpenATV system language); applies on next opening |
| Home Assistant address | For example `http://192.168.1.20:8123` or your HTTPS address; do not append `/api` or a subpath |
| Long-lived HA access token | The complete token |
| Refresh interval | Interval while the plugin is open; default 10 seconds |
| Skin profile | **Automatic**, **Standard (active skin)**, or **GradientFHD**; automatic by default |
| Font family | A registered receiver font or **Auto (skin/receiver default)** |
| Font size | A local value from 16 to 64 or **Auto (skin/receiver default)** |
| Connection timeout | Default 5 seconds |
| Show in main menu | Direct entry in the Enigma2 main menu; off by default |
| Reverse Ch+/− | Reverse page navigation; off by default |
| Remember menu position on exit | Restore the last menu level and selection on next opening; on by default |

**Green** saves. **OK/Yellow** opens the keyboard for text fields and a choice
list for language, fonts and skin profile. **Left/Right** changes values.
The main-menu entry is updated the next time the Enigma2 main menu opens.

Language and skin profile changes apply when the plugin is reopened.
**Automatic** detects the active skin and uses the standard profile for unknown
skins. A manual profile overrides detection and skin-provided plugin screens;
it changes only the plugin's appearance.

OpenATV system dialogs and fixed text in external skins follow their own language.

### Font family and size

Press **Menu/Blue** in the receiver plugin and choose **Font family** or
**Font size**. Save with **Green**. These choices apply to all menus on that
receiver; other receivers keep their own settings.

| Setting | Choice | Behavior |
| --- | --- | --- |
| Font family | **Auto (skin/receiver default)** | Use the skin or receiver profile font |
| Font family | Registered font | Use this font instead of the skin/receiver default; fall back to `Regular` if unavailable |
| Font size | **Auto (skin/receiver default)** | Use the skin or receiver profile size |
| Font size | Number from 16 to 64 | Ignore the skin/receiver default and use the selected size |

The settings are independent: for example, keep the family on **Auto** and
select a fixed size. Explicit choices take precedence in every profile,
including GradientFHD. Fixed sizes retain their resolution scaling: values
refer to 1280 × 720, so `32` corresponds to 48 pixels at Full HD. Row height
adjusts to the size used.

### Existing font settings

Existing local font values are retained. The former **Use HA setting** choice
is now shown as **Auto (skin/receiver default)** and uses the skin/receiver
default. Its stored values remain an empty font family and size `0`.

Previous HA font settings remain stored for older receivers; updated receivers
ignore them. To keep a font previously selected in HA, select it on each receiver.
There is no automatic transfer from HA. Menus, access rules and connection
settings are retained; no migration or reconfiguration is required.

### Enter the token through a file

You can use an editor or SFTP for a long token. Close the plugin before editing
`/etc/enigma2/enigmaha_companion.json`:

```json
{
  "url": "http://192.168.1.20:8123",
  "token": "ENTER_YOUR_OWN_TOKEN_HERE",
  "refresh_seconds": 10,
  "language": "auto",
  "skin_profile": "auto",
  "font_family": "",
  "font_size": 0,
  "timeout": 5,
  "show_in_mainmenu": false,
  "reverse_channel_paging": false,
  "remember_menu_position": true
}
```

`language` accepts `de` (German), `en` (English) and `auto` (default for new installations,
OpenATV system language, falling back to German for unsupported languages). An existing
file without this value keeps German. No migration or reconfiguration is required.
An empty font family and font size `0` mean **Auto (skin/receiver default)**.
`skin_profile` accepts `auto`,
`native` and `gradient`. If you create the file manually, set its permissions
with `chmod 600 /etc/enigma2/enigmaha_companion.json`; the plugin saves it with
these permissions itself.

Keep tokens out of logs, screenshots and the repository. Tokens entered through
the on-screen keyboard are visible on the TV. HTTPS verifies certificates;
verification cannot be disabled. HTTP transmits the token without encryption.

## Remote keys

| Key | Action |
| --- | --- |
| Up / Down | Select previous / next entry |
| Left / Right | Page up / down through the list |
| Recall | Go back one menu level; no action at the root |
| OK / Green | Open submenu or toggle a light/switch |
| Menu / Blue | Open settings |
| Yellow | Reload menu and states |
| Channel + / − | Page up / down; reversible through **Reverse Ch+/−** |
| Red / Exit | Close the entire menu from any level |
| Info | Version on the receiver, version in Home Assistant, logged-in user and counts of visible menus, submenus and entities |
| Help | Show keys and the configured channel-key direction |

On/off states use HA entity icons: yellow for on, grey for off. If an icon
cannot be displayed, the state appears as text. Sensors show values with units.
Dimming, scenes and scripts are unsupported.

On connection failure, the last display remains visible with **OFFLINE**.
Toggling is blocked until a successful refresh. Commands are never automatically
repeated, even if their response was lost.

## Functional check

1. In HA, save a “Test” submenu containing a light and sensor.
2. Open the plugin, press OK to open “Test”, and check both states.
3. Toggle the light with OK and check the refreshed state.
4. Press OK on the sensor: it must not send a command.
5. Press Recall to return, and Red or Exit at any level to close.
6. Rename an entry in HA, save it and press Yellow on the receiver.
7. Check both languages in the editor and receiver, including help and error
   messages. Confirm your own names remain unchanged.

## Updating

Use the [coordinated update](#coordinated-update-through-hacs-and-ipk), or install
the HA and receiver packages from the same release manually and restart both.
Check release notes for migrations and any required reconfiguration. Back up
configuration before changes.

The bilingual update requires no reconfiguration. Without a saved preference,
the editor and receiver start in German. Existing menus and credentials remain.

## Troubleshooting and removal

- **Integration missing:** Check the folder structure, restart HA and reload the browser.
- **Token rejected:** Check the token, active user and permissions.
- **HTTP 404:** Check the HA component installation and address.
- **HTTP 503:** Check that the integration is configured and loaded under Devices & services.
- **Missing font:** Choose `Regular` or a registered receiver font.
- **Plugin missing:** Check Python and dependencies; inspect Enigma2 startup logs
  for import errors. Do not include tokens in reports.
- **Remove IPK:** Run `opkg remove enigma2-plugin-extensions-enigmahacompanion`,
  then restart the GUI.
- **Remove manual receiver installation:** Remove only the plugin folder named
  above. The separate private configuration is retained.
- **Remove HA integration:** Remove it under Devices & services, optionally remove
  the custom component folder, and restart HA. The stored menu is retained.
