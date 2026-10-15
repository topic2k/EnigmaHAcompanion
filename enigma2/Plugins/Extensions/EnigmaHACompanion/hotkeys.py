"""OpenATV button actions loaded when settings open, with a private local cache."""

import hashlib
import json
import os
import tempfile

from Plugins.Plugin import PluginDescriptor
from Screens.MessageBox import MessageBox
from twisted.internet.threads import deferToThread

from .companion.client import ClientError, CompanionClient, MAX_RESPONSE_BYTES
from .companion.i18n import translate
from .companion.updater import load_receiver_id
from .enigmaha_protocol.menu import index_nodes, validate_menu
from .settings import load_settings


def connection(config):
    return config["url"].rstrip("/"), config["token"]


class HotkeyCache:
    def __init__(self, path="/etc/enigma2/enigmaha_companion_hotkeys.json"):
        self.path = path

    @staticmethod
    def identity(config):
        return hashlib.sha256(json.dumps(connection(config)).encode("utf-8")).hexdigest()

    def load(self, config):
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.loads(handle.read(MAX_RESPONSE_BYTES + 1))
            if (not isinstance(data, dict) or set(data) != {"schema_version", "identity", "menu"}
                    or type(data["schema_version"]) is not int or data["schema_version"] != 1
                    or data["identity"] != self.identity(config)):
                return None
            return validate_menu(data["menu"])
        except (OSError, ValueError, RecursionError):
            return None

    def save(self, menu, config):
        data = {"schema_version": 1, "identity": self.identity(config), "menu": validate_menu(menu)}
        directory = os.path.dirname(self.path)
        os.makedirs(directory, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".enigmaha-hotkeys-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                os.chmod(temporary, 0o600)
                json.dump(data, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def switch_entries(menu):
    """Keep every actionable menu occurrence, including repeated entities."""
    menu = validate_menu(menu)
    result = []

    def visit(node, parents):
        path = parents + [node["label"]]
        if node["type"] == "menu":
            for child in node["children"]:
                visit(child, path)
        elif "toggle" in node["actions"]:
            result.append((node["id"], node["entity_id"], " > ".join(path)))

    visit(menu["root"], [])
    return result


class Hotkeys:
    def __init__(self, session, registry, button_setup=None, cache=None):
        self.session, self.registry = session, registry
        self.cache = cache or HotkeyCache()
        self.descriptors = {}
        self.identity = None
        self.closed = self.refreshing = self.switching = False
        self.waiters = []
        self.button_setup = button_setup
        try:
            config = load_settings()
            menu = self.cache.load(config)
            if menu is not None:
                self.identity = connection(config)
                self.sync(menu, config)
        except (ValueError, OSError):
            pass
        if button_setup is not None:
            self.install_setup_hook()

    def install_setup_hook(self):
        native = self.button_setup
        original = self.original_init = native.ButtonSetup.__init__

        def initialize(screen, *args, **kwargs):
            original(screen, *args, **kwargs)
            active = [True]
            screen.onClose.append(lambda: active.__setitem__(0, False))

            def updated():
                if self.closed or not active[0]:
                    return
                screen.ButtonSetupFunctions = native.getButtonSetupFunctions()
                screen.getFunctions()
                # A key can be selected while HTTP is still in flight. Refresh
                # that open chooser as well, without discarding unsaved edits.
                chooser = getattr(screen.session, "current_dialog", None)
                if isinstance(chooser, native.ButtonSetupSelect):
                    chooser.ButtonSetupFunctions = screen.ButtonSetupFunctions
                    chooser["list"].setList(chooser.getFunctionList())

            screen.onFirstExecBegin.append(lambda: self.refresh(updated))

        self.setup_init = initialize
        native.ButtonSetup.__init__ = initialize

    def clear(self):
        registered = self.registry.getPlugins(PluginDescriptor.WHERE_BUTTONSETUP)
        for descriptor in self.descriptors.values():
            if descriptor in registered:
                self.registry.removePlugin(descriptor)
        self.descriptors.clear()

    def stop(self):
        self.closed = True
        if self.button_setup is not None and self.button_setup.ButtonSetup.__init__ is self.setup_init:
            self.button_setup.ButtonSetup.__init__ = self.original_init
        self.waiters.clear()
        self.clear()

    def current(self, identity):
        try:
            return not self.closed and connection(load_settings()) == identity
        except (ValueError, OSError):
            return False

    @staticmethod
    def client(config):
        return CompanionClient(config["url"], config["token"], config["timeout"],
                               receiver_id=load_receiver_id())

    def notify_waiters(self):
        waiters, self.waiters = self.waiters, []
        for callback in waiters:
            callback()

    def refresh(self, callback=None):
        if self.closed:
            return
        if callback is not None:
            self.waiters.append(callback)
        if self.refreshing:
            return
        try:
            config = load_settings()
            identity = connection(config)
            if identity != self.identity:
                self.clear()
                self.identity = identity
            if not all(identity):
                self.notify_waiters()
                return
        except (ValueError, OSError):
            self.clear()
            self.notify_waiters()
            return
        self.refreshing = True

        def work():
            menu = self.client(config).get_menu()
            if self.current(identity):
                try:
                    self.cache.save(menu, config)
                except OSError:
                    raise ClientError("hotkey_storage_failed") from None
            return menu

        def done(menu):
            self.refreshing = False
            if self.current(identity):
                if menu is not None:
                    self.sync(menu, config)
            else:
                self.clear()
            self.notify_waiters()

        # Keep bindings available through a temporary outage; execution always
        # checks a fresh server menu and never sends a cached command.
        def failed(failure):
            if self.current(identity) and getattr(failure.value, "code", None) in {"unauthorized", "forbidden"}:
                self.clear()
                # Persist the empty list so a revoked login cannot restore the
                # previously shared menu on the next GUI start.
                try:
                    self.cache.save({"schema_version": 1, "revision": 1,
                        "display": {"font_family": "Regular", "font_size": 28},
                        "root": {"type": "menu", "id": "empty", "label": "Home Assistant", "children": []}}, config)
                except OSError:
                    pass
            done(None)
            if self.current(identity):
                self.show_error(self.session, getattr(failure.value, "code", "failed"), config["language"])

        deferToThread(work).addCallbacks(done, failed)

    def sync(self, menu, config):
        wanted, names = {}, set()
        for entry_id, entity_id, path in sorted(switch_entries(menu)):
            name = translate("EnigmaHA: {path} – Umschalten", config["language"], path=path)
            # OpenATV deduplicates actions by name, even across plugin paths.
            while name in names:
                name += " [" + entry_id + "]"
            names.add(name)
            # ButtonSetup persists a plugin path plus an ordinal. Each action
            # gets its own stable namespace so alphabetic insertion, renaming
            # or removal cannot silently redirect a saved key to another item.
            key = hashlib.sha256((config["url"].rstrip("/") + "\n" + entry_id + "\n" + entity_id).encode("utf-8")).hexdigest()
            wanted[key] = (entry_id, entity_id, name)
        registered = self.registry.getPlugins(PluginDescriptor.WHERE_BUTTONSETUP)
        for key, descriptor in list(self.descriptors.items()):
            if key not in wanted or descriptor.name != wanted[key][2]:
                if descriptor in registered:
                    self.registry.removePlugin(descriptor)
                del self.descriptors[key]
        for key, (entry_id, entity_id, name) in wanted.items():
            if key not in self.descriptors:
                identity = connection(config)

                def action(session, entry_id=entry_id, entity_id=entity_id, identity=identity, **kwargs):
                    self.activate(session, entry_id, entity_id, identity)

                descriptor = PluginDescriptor(name=name, description=name,
                    where=PluginDescriptor.WHERE_BUTTONSETUP, fnc=action,
                    needsRestart=False, internal=True)
                # This is an identifier consumed by ButtonSetup, not an on-disk
                # plugin directory. Register at runtime so updateIcon cannot
                # replace it with the parent plugin's shared path.
                descriptor.path = os.path.join(os.path.dirname(__file__), "hotkeys", key)
                self.descriptors[key] = descriptor
            descriptor = self.descriptors[key]
            if descriptor not in self.registry.getPlugins(PluginDescriptor.WHERE_BUTTONSETUP):
                self.registry.addPlugin(descriptor)

    def activate(self, session, entry_id, entity_id, identity):
        if self.closed or self.switching:
            return
        try:
            config = load_settings()
            if connection(config) != identity:
                raise ClientError("hotkey_changed")
        except (ValueError, OSError, ClientError):
            self.show_error(session, "hotkey_changed", "auto")
            return
        self.switching = True

        def work():
            client = self.client(config)
            menu = client.get_menu()
            node = index_nodes(menu).get(entry_id)
            if (not node or node["type"] != "entity" or node["entity_id"] != entity_id
                    or "toggle" not in node["actions"] or not self.current(identity)):
                raise ClientError("hotkey_changed")
            # No automatic retry: an uncertain response must not toggle twice.
            client.execute({"schema_version": menu["schema_version"], "revision": menu["revision"],
                            "entry_id": entry_id, "action": "toggle"})

        def done(result):
            self.switching = False

        def failed(failure):
            done(None)
            if not self.closed:
                self.show_error(session, getattr(failure.value, "code", "failed"), config["language"])

        deferToThread(work).addCallbacks(done, failed)

    @staticmethod
    def show_error(session, code, language):
        message = {
            "hotkey_changed": "Hotkey-Eintrag nicht mehr freigegeben oder geändert. Hotkeys neu zuordnen.",
            "unauthorized": "Token ungültig oder abgelaufen. Menü: Einstellungen",
            "forbidden": "Keine Berechtigung für diesen Eintrag.",
            "connection_failed": "Home Assistant nicht erreichbar. Adresse/Netzwerk prüfen.",
            "hotkey_storage_failed": "Hotkey-Liste konnte nicht gespeichert werden. Dateirechte und freien Speicher prüfen.",
        }.get(code, "Hotkey konnte nicht geschaltet werden. Zustand und Verbindung in EnigmaHA Companion prüfen.")
        session.open(MessageBox, translate(message, language), type=MessageBox.TYPE_ERROR)
