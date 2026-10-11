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

See [test status and limitations](Development.en.md#test-status-and-limitations).

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

The HA integration and receiver plugin must use exactly the same release.
Both sides check the EnigmaHA identity and package version on every receiver
request. Different versions or a missing/invalid identity block data requests
and actions. The receiver displays an explanation with the versions; the HA
editor shows requests from the last five minutes and refreshes this status every
30 seconds. A receiver must connect before it can be checked.

The [coordinated update](#coordinated-update-through-hacs-and-ipk) brings HA and
participating receivers to the same release after confirmation. Menus, receiver
settings and tokens are retained; no reconfiguration is required.

Choose **English** under **Sprache**. German is the default and first option.
The choice is saved in this browser. HA setup dialogs and the internal texts of
native selectors follow your HA profile language.

1. Add and open submenus as needed.
2. Search for an HA entity, select it and choose **Add entity**. Filter by entity
   type, area or device class to narrow the selection.
3. Edit display names and reorder entries with the drag handle or up/down arrows.
   Drag near the list's edge to scroll automatically.
4. Choose the font family and size under **Receiver appearance**.
5. Choose **Save**.

Lights, switches and `input_boolean` helpers are configured as toggleable.
Other entities are read-only. The receiver user still needs HA permissions.
Your own menu and entity names are never automatically translated.

All receivers use the same menu. HA manages it in
`.storage/enigmaha_companion.menu`; do not edit that file while HA is running.

## Coordinated update through HACS and IPK

Both components must first run a version containing this update workflow. Update
older installations through HACS and the IPK from the same release, then restart
HA and the receiver GUI. For an existing ZIP installation, configure EnigmaHA in
HACS first.

Requirements: an active HACS update entity for this repository, GitHub internet
access from HA and each receiver, and root permissions for OpenATV's `opkg`.
The receiver still uses its regular HA user token. HTTPS certificate verification
remains enabled; no SSH credentials are required.

1. Open the plugin on all participating receivers. The HA editor lists receiver
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
another local confirmation. Different versions continue to block menu requests
and actions; the update channel remains available. HA stores progress in
`.storage/enigmaha_companion.update`. Receiver identity and installation journal
are stored in `/etc/enigma2/enigmaha_companion_receiver_id` and
`/etc/enigma2/enigmaha_companion_update.json`. Do not edit these during an update.

Lost connections do not cause a second IPK installation. If an `opkg` result is
uncertain, inspect package status on the receiver; uncertain installations are
not retried automatically. A missing GUI restart is offered again. Downgrades
are blocked. Do not install another version through HACS or `opkg` during the
transaction. Update receivers not included in the transaction to the same release
later; otherwise they remain blocked. Manual installation of both packages from
the same release remains available.

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
The initial language is German. Choose **English** under **Sprache**, press
**Green**, then close and reopen the plugin to apply the language.

| Setting | Meaning |
| --- | --- |
| Language | **Deutsch** (default) or **English**; applies on next opening |
| Home Assistant address | For example `http://192.168.1.20:8123` or your HTTPS address; do not append `/api` or a subpath |
| Long-lived HA access token | The complete token |
| Refresh interval | Interval while the plugin is open; default 10 seconds |
| Skin profile | **Automatic**, **Standard (active skin)**, or **GradientFHD**; automatic by default |
| Font family | A registered receiver font or **Use HA setting** |
| Font size | A local value from 16 to 64 or **Use HA setting** |
| Connection timeout | Default 5 seconds |
| Show in main menu | Direct entry in the Enigma2 main menu; off by default |
| Reverse Ch+/− | Reverse page navigation; off by default |

**Green** saves. **OK/Yellow** opens the keyboard for text fields and a choice
list for language, fonts and skin profile. **Left/Right** changes values.
The main-menu entry is updated the next time the Enigma2 main menu opens.

Language and skin profile changes apply when the plugin is reopened.
**Automatic** detects the active skin and uses the standard profile for unknown
skins. A manual profile overrides detection and skin-provided plugin screens;
it changes only the plugin's appearance.

In the standard profile, local font choices override HA settings. Profiles such
as GradientFHD use their own font settings. Missing fonts fall back to `Regular`.
OpenATV system dialogs and fixed text in external skins follow their own language.

### Enter the token through a file

You can use an editor or SFTP for a long token. Close the plugin before editing
`/etc/enigma2/enigmaha_companion.json`:

```json
{
  "url": "http://192.168.1.20:8123",
  "token": "ENTER_YOUR_OWN_TOKEN_HERE",
  "refresh_seconds": 10,
  "language": "en",
  "skin_profile": "auto",
  "font_family": "",
  "font_size": 0,
  "timeout": 5,
  "show_in_mainmenu": false,
  "reverse_channel_paging": false
}
```

`language` accepts `de` (German, default) and `en` (English). An empty font
family and font size `0` mean **Use HA setting**. `skin_profile` accepts `auto`,
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
| Right | Open selected submenu |
| Left / Exit | Go to parent menu; close the plugin at the root |
| OK / Green | Open submenu or toggle a light/switch |
| Menu / Blue | Open settings |
| Yellow | Reload menu and states |
| Channel + / − | Page up / down; reversible through **Reverse Ch+/−** |
| Red | Close immediately |
| Help | Show keys and the configured channel-key direction |

On/off states use HA entity icons: yellow for on, grey for off. If an icon
cannot be displayed, the state appears as text. Sensors show values with units.
Dimming, scenes and scripts are unsupported.

On connection failure, the last display remains visible with **OFFLINE**.
Toggling is blocked until a successful refresh. Commands are never automatically
repeated, even if their response was lost.

## Functional check

1. In HA, save a “Test” submenu containing a light and sensor.
2. Open the plugin, press Right to open “Test”, and check both states.
3. Toggle the light with OK and check the refreshed state.
4. Press OK on the sensor: it must not send a command.
5. Press Left to return, then Exit at the root to close.
6. Rename an entry in HA, save it and press Yellow on the receiver.
7. Check both languages in the editor and receiver, including help and error
   messages. Confirm your own names remain unchanged.

## Updating

Use the [coordinated update](#coordinated-update-through-hacs-and-ipk), or install
the HA and receiver packages from the same release manually and restart both.
Check release notes for required reconfiguration and back up configuration before changes.

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
