# Isoliertes HA-Testlabor / Isolated HA test lab

## Deutsch

Voraussetzungen: Docker mit Compose und Python 3. Auf Windows muss Docker Desktop
Linux-Container ausführen. Im Projektstamm:

```console
python tools/ha_dev.py start
python tools/ha_dev.py check
python tools/ha_dev.py logs
python tools/ha_dev.py stop
```

`start` baut das Projekt, stoppt die Testinstanz, ersetzt ihre Integrationsdateien
vollständig und startet HA **2026.10.1** unter **http://127.0.0.1:18123**.
Die mitgelieferte `configuration.yaml` wird bei jedem Start wieder eingespielt.
Anschließend wartet der Befehl auf HA, erledigt das Onboarding und richtet
**EnigmaHA Companion** samt Testmenü automatisch ein. Beim ersten Start ist
keine Einrichtung im Browser nötig. Danach den Menüeditor über die Seitenleiste
öffnen.
Benutzer, Menü und Datenbank bleiben im Volume `enigmaha-dev_config` erhalten.
`stop` löscht keine Daten. Für eine andere HA-Version das Image in `compose.yaml`
gezielt ändern und erneut prüfen.

Frische Labore verwenden den öffentlichen Testbenutzer **`enigma2ha`** mit dem
Testpasswort **`notsecret`**. Diese festen Testwerte sind ausschließlich für das
isolierte Labor vorgesehen. Lokale Anmeldedaten und HA-Tokens werden in der
ignorierten Datei `.work/ha-dev-access.json` gespeichert; echte Zugangsdaten
und Tokens gehören nicht ins Repository.

Weitere Starts setzen unterbrochenes Onboarding fort und erzeugen keine zweite
Integration. Ein Testmenü wird nur bei einem unveränderten, leeren Ausgangsmenü
angelegt; bearbeitete oder bewusst geleerte Menüs bleiben erhalten. Die Vorlage
steht in `menu.json`.

Bereits manuell eingerichtete Labore behalten ihre Benutzer und Passwörter.
Vorhandene lokale Anmeldedaten werden wiederverwendet. Fehlt die Zugangsdatei
und wurde ein anderer Benutzer verwendet, lokal `.work/ha-dev-access.json` mit
`url`, `username` und `password` des bestehenden Labors anlegen. Für `url` den
Wert `http://127.0.0.1:18123` verwenden. Benutzer werden nicht zurückgesetzt und
das Docker-Volume muss nicht neu angelegt werden.

Enthalten sind ein Testschalter, eine virtuelle Lampe und ein veränderbarer
Temperatursensor. Es gibt keine Geräteerkennung und keine übernommenen
Produktivzugänge. Der Port ist ausschließlich an Windows-Loopback gebunden;
ein physischer Receiver kann diese Instanz deshalb nicht direkt erreichen.
Für einen Receiver-Test muss die Erreichbarkeit gesondert geplant werden.

Der Container eignet sich für API-, Berechtigungs-, Editor- und Integrationstests.
Er ersetzt weder OpenATV-Hardwaretests noch HAOS-/Supervisor-/Add-on-Tests.
Unter Windows Docker Desktop mit Linux-Containern verwenden; die offizielle
[Container-Installationsanleitung](https://www.home-assistant.io/installation/linux/)
bezieht sich auf Docker Engine. Eine IDE-Devcontainer-Hülle ist für die
Custom-Integration nicht erforderlich.

## English

Requires Python 3 and Docker with Compose (Linux containers on Windows).
Run the commands above from the repository root. `start` builds the complete
integration, replaces its installed files and starts HA **2026.10.1** at
**http://127.0.0.1:18123**. It reapplies the supplied `configuration.yaml`.
The command waits for HA, completes onboarding and configures **EnigmaHA
Companion** with a test menu automatically. No browser setup is required on
first use; open the menu editor from the sidebar afterwards.
Users, menu and database persist in `enigmaha-dev_config`; `stop` preserves them.

Fresh labs use the public test login **`enigma2ha` / `notsecret`**, exclusively
for this isolated environment. Local credentials and HA tokens are stored in
the ignored `.work/ha-dev-access.json`; never commit real credentials or tokens.
Reruns resume incomplete onboarding without duplicating the integration and
seed `menu.json` only into a pristine empty menu. Edited or deliberately emptied
menus are preserved.

Existing manually configured labs retain their users and passwords. Saved
credentials are reused. If the access file is missing and the login differs,
create `.work/ha-dev-access.json` locally with `url`, `username` and `password`
for the existing lab (`url`: `http://127.0.0.1:18123`). No account reset or volume
recreation is needed.

Fixtures include a switch, virtual light and adjustable temperature sensor.
No discovery or production credentials are configured. Loopback binding prevents
direct access from a physical receiver. This environment covers software testing,
not OpenATV hardware, HAOS, Supervisor or add-ons. An IDE devcontainer wrapper
is optional for custom integration development.
