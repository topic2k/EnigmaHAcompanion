# EnigmaHA Companion

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

## Voraussetzungen

- Home Assistant und eingerichtetes HACS.
- Ein Enigma2-Receiver mit OpenATV und Python 3.8 oder neuer.
- Der Receiver muss Home Assistant im Netzwerk erreichen können.

Hinweise zu getesteten Geräten und bekannten Grenzen findest du in der [Entwicklerdokumentation](docs/Entwicklung.md#teststand-und-grenzen).

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

## Für Entwickler

[Entwicklung und Tests](docs/Entwicklung.md) ·
[Protokoll](docs/Protokoll-v1.md) ·
[Pakete und Releases](docs/Releases.md)
