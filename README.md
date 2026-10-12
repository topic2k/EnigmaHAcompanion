<sup> [Deutsch](#deutsch) &nbsp; | &nbsp; [English](#english) </sup>

<a id="my-anchor"></a>

# EnigmaHA Companion [^1]

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/enigmaha_companion/brand/dark_logo@2x.png">
  <img src="custom_components/enigmaha_companion/brand/logo@2x.png" alt="EnigmaHA Companion – Receiver, Fernbedienung und Zuhause" width="900">
</picture>

Home Assistant auf deinem Receiver: Mit EnigmaHA Companion siehst du die Zustände
deines Zuhauses auf dem Fernseher und schaltest Lampen und Schalter mit der
Fernbedienung. Das unabhängige Projekt verbindet Home Assistant mit
Enigma2-Receivern unter OpenATV.

Dein Menü stellst du in Home Assistant zusammen: Entitäten auswählen, in
Untermenüs ordnen und nach Wunsch benennen. Am Receiver kannst du durch dieses
Menü navigieren, Sensorwerte ablesen und Lampen, Schalter sowie
`input_boolean` ein- und ausschalten. Ein zusätzlicher Server oder MQTT-Broker
ist nicht nötig.

Gemeinsame und persönliche Menüs können nebeneinander verwendet werden.
Ganze Menüs, Untermenüs und einzelne Einträge lassen sich für HA-Benutzer
freigeben; der Token am Receiver bestimmt die Ansicht.
Siehe [benutzerabhängige Menüs](docs/Benutzermenues.md).

## Voraussetzungen

- Home Assistant und eingerichtetes HACS.
- Ein Enigma2-Receiver mit OpenATV und Python 3.13 oder neuer.
- Der Receiver muss Home Assistant im Netzwerk erreichen können.

Hinweise zum Updateablauf und seinen Grenzen findest du in der [Entwicklerdokumentation](docs/Entwicklung.md#updateablauf-und-grenzen).

## Installation

Du installierst eine Integration in Home Assistant und ein Plugin auf dem Receiver.
Verwende dafür die Pakete aus demselben [Release](https://github.com/topic2k/EnigmaHAcompanion/releases).

### 1. Home Assistant über HACS

1. In HACS **⋮ → Benutzerdefinierte Repositories** öffnen.
2. `https://github.com/topic2k/EnigmaHAcompanion` als **Integration** hinzufügen.
3. **EnigmaHA Companion** herunterladen und Home Assistant neu starten.
4. Unter **Einstellungen → Geräte & Dienste → Integration hinzufügen**
   **EnigmaHA Companion** auswählen.
5. In der Seitenleiste **EnigmaHA Companion** öffnen, Entitäten und Untermenüs
   hinzufügen und **Speichern** wählen.

Für HACS muss ein veröffentlichtes Release vorhanden sein.

### 2. Receiver über IPK

Das IPK aus dem [Release](https://github.com/topic2k/EnigmaHAcompanion/releases)
herunterladen. Du kannst es direkt im Browser über **OpenWebif** installieren:

1. Die Receiver-Adresse im Browser öffnen, z. B. `http://192.168.1.30`.
2. Unter **Pakete/Packages** den IPK-Upload öffnen, die heruntergeladene Datei
   hochladen und anschließend deren Installation starten. Falls der Upload fehlt,
   in den OpenWebif-Einstellungen am Receiver **IPK Upload erlauben** aktivieren.
3. Nach erfolgreicher Installation die **Benutzeroberfläche/GUI neu starten**.

Alternativ das IPK nach `/tmp` auf den Receiver kopieren und dort per SSH
installieren (nur das gewünschte EnigmaHA-IPK in `/tmp` ablegen):

```sh
opkg install /tmp/enigma2-plugin-extensions-enigmahacompanion_*_all.ipk
```

Auch danach die **Benutzeroberfläche/GUI neu starten**. Das Plugin findest du unter
**Erweiterungen/Plugins → EnigmaHA Companion**.

Die [ausführliche OpenWebif-Anleitung](docs/Installation.md#ipk-ueber-openwebif)
beschreibt Upload und Installation Schritt für Schritt.

### 3. Verbinden und loslegen

In Home Assistant einen **langlebigen Zugriffstoken** erstellen:

1. Unten in der Seitenleiste auf deinen Benutzernamen klicken und **Sicherheit** öffnen.
2. Unter **Langlebige Zugriffstoken** auf **Token erstellen** klicken und einen
   Namen wie „EnigmaHA Receiver“ vergeben.
3. Den angezeigten Token vollständig kopieren und sicher aufbewahren.
   Er wird nur einmal angezeigt.

Beim ersten Pluginstart am Receiver die HA-Adresse (z. B.
`http://192.168.1.20:8123`, ohne `/api`) und den Token eingeben.
Mit **Grün** speichern.

Mit **Auf/Ab** einen Eintrag wählen, mit **OK** ein Untermenü öffnen oder schalten
und mit **Links/Exit** zurückgehen. **Menü/Blau** öffnet die Einstellungen.

Die [ausführliche Anleitung](docs/Installation.md) erklärt die manuelle
Installation ohne HACS, alle Tasten, Einstellungen und die Fehlerbehebung.

## Lizenz

Der eigene Projektcode und die Dokumentation stehen unter
**GNU GPL Version 2 oder später** (`GPL-2.0-or-later`), siehe [LICENSE](LICENSE)
und [NOTICE](NOTICE).

Branding-Grafiken und das Exportskript behalten **Apache 2.0**; die
Poppins-Schrift behält **SIL OFL 1.1**. Die vollständigen Herkunfts- und
Lizenzhinweise stehen in [assets/branding/NOTICE](assets/branding/NOTICE).
Die Schriftdatei gehört nur zu den Entwicklungsquellen.

Alle Installationspakete enthalten `LICENSE` und `NOTICE`. Die HA-Pakete
enthalten zusätzlich die Apache-Lizenz und Herkunftshinweise unter `brand/`.

## Für Entwickler

[Entwicklung und Tests](docs/Entwicklung.md) ·
[Protokoll](docs/Protokoll-v1.md) ·
[Pakete und Releases](docs/Releases.md)

[^1]: Mit Unterstützung generativer KI entwickelt.

---

<sup> [Deutsch](#deutsch) &nbsp; | &nbsp; [English](#english) </sup>

<a id="my-anchor"></a>

# EnigmaHA Companion [^1]

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="custom_components/enigmaha_companion/brand/dark_logo@2x.png">
  <img src="custom_components/enigmaha_companion/brand/logo@2x.png" alt="EnigmaHA Companion – Receiver, Fernbedienung und Zuhause" width="900">
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
and **Left/Exit** to go back. **Menu/Blue** opens settings.

The [installation and usage guide](docs/Installation.en.md) covers manual
installation without HACS, all settings, remote keys and troubleshooting.

## For developers

[Development and tests](docs/Development.en.md) ·
[Protocol](docs/Protocol.en.md) ·
[Packages and releases](docs/Releases.en.md) ·
[Receiver skins](enigma2/README.en.md)

[^1]: Developed with assistance from generative AI.
