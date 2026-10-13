# EnigmaHA Companion

[Deutsch](README.md) · **English**

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/enigmaha_companion/brand/dark_logo@2x.png">
  <img src="custom_components/enigmaha_companion/brand/logo@2x.png" alt="EnigmaHA Companion – receiver, remote and home" width="900">
</picture>

Home Assistant on your receiver: view your home's states on the TV and toggle
lights and switches with your remote. EnigmaHA Companion is an independent project
connecting Home Assistant to Enigma2 receivers running OpenATV.

Build your menu in Home Assistant: select entities, organize submenus and choose
display names. On the receiver, browse the menu, read sensors and toggle lights,
switches and `input_boolean` helpers. No additional server or MQTT broker is required.

Shared and personal menus can coexist. Share complete menus, submenus and
individual entries with selected HA users; the receiver token determines its
view. See [user-specific menus](docs/User-menus.en.md).

## Requirements

- Home Assistant and HACS.
- An Enigma2 receiver running OpenATV with Python 3.13 or newer.
- A network connection from the receiver to Home Assistant.

See [development](docs/Development.en.md#update-implementation-and-limitations)
for the update implementation and its limitations.

## Installation

Install the HA integration and receiver plugin from the same
[release](https://github.com/topic2k/EnigmaHAcompanion/releases).

### 1. Home Assistant through HACS

1. In HACS, open **⋮ → Custom repositories**.
2. Add `https://github.com/topic2k/EnigmaHAcompanion` with category **Integration**.
3. Download **EnigmaHA Companion** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → EnigmaHA Companion**.
5. Open **EnigmaHA Companion** in the sidebar, switch to **English**, add entities
   and submenus, then choose **Save**.

HACS installation requires a published release.

### 2. Receiver through IPK

Download the IPK from the [release](https://github.com/topic2k/EnigmaHAcompanion/releases).
You can install it in your browser through **OpenWebif**:

1. Open the receiver's address, for example `http://192.168.1.30`.
2. Open **Packages**, upload the IPK and start its installation. If uploading is
   unavailable, enable **Allow IPK upload** in the receiver's OpenWebif settings.
3. Once installation succeeds, **restart the user interface/GUI**.

Alternatively, copy the IPK to `/tmp` on the receiver and install it over SSH.
Keep only the intended EnigmaHA IPK in `/tmp`:

```sh
opkg install /tmp/enigma2-plugin-extensions-enigmahacompanion_*_all.ipk
```

Restart the GUI afterwards. Open **Plugins → EnigmaHA Companion**.
See the [detailed OpenWebif instructions](docs/Installation.en.md#install-the-ipk-through-openwebif)
for the upload and installation steps.

### 3. Connect and start

Create a **long-lived access token** in Home Assistant:

1. Click your username at the bottom of the sidebar and open **Security**.
2. Under **Long-lived access tokens**, choose **Create token** and enter a name
   such as “EnigmaHA Receiver”.
3. Copy the entire token and store it securely. It is displayed only once.

On the receiver's first plugin launch, enter the HA address (for example
`http://192.168.1.20:8123`, without `/api`) and token. Choose **English** under
**Sprache** and press **Green** to save. Close and reopen the plugin to apply
the language.

Use **Up/Down** to select entries, **OK** to open a submenu or toggle an entity,
and **Recall** to go back one level. **Red/Exit** closes the menu.
**Left/Right** pages through the list; **Info** shows program, user and menu information. **Menu/Blue** opens settings.

The [installation and usage guide](docs/Installation.en.md) covers manual
installation without HACS, all settings, remote keys and troubleshooting.

## For developers

[Development and tests](docs/Development.en.md) ·
[Protocol](docs/Protocol.en.md) ·
[Packages and releases](docs/Releases.en.md) ·
[Receiver skins](enigma2/README.en.md)
