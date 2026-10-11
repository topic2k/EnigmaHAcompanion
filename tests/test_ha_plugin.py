"""Real aiohttp route tests; HA runtime services are narrow test doubles."""
import asyncio
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]
from companion.client import CompanionClient, ClientError
from enigmaha_protocol.compatibility import COMPONENT_HEADER, VERSION_HEADER, VERSION, PROTOCOL_HEADER, PROTOCOL_VERSION


def load_api():
    package = types.ModuleType("ha_plugin_test")
    package.__path__ = [str(BUNDLE)]
    sys.modules[package.__name__] = package
    fake = {}
    for name in ("homeassistant", "homeassistant.auth", "homeassistant.auth.permissions",
                 "homeassistant.auth.permissions.const", "homeassistant.components",
                 "homeassistant.components.http", "homeassistant.components.persistent_notification", "homeassistant.core", "homeassistant.exceptions",
                 "homeassistant.helpers", "homeassistant.helpers.entity_registry", "homeassistant.helpers.icon"):
        fake[name] = types.ModuleType(name)
    fake["homeassistant.auth.permissions.const"].POLICY_READ = "read"
    fake["homeassistant.auth.permissions.const"].POLICY_CONTROL = "control"
    fake["homeassistant.components.http"].KEY_HASS_USER = "hass_user"
    class View:
        @staticmethod
        def json(data, status=200, headers=None):
            return web.json_response(data, status=status, headers=headers)
    fake["homeassistant.components.http"].HomeAssistantView = View
    fake["homeassistant.components.persistent_notification"].async_create = Mock()
    fake["homeassistant.components.persistent_notification"].async_dismiss = Mock()
    fake["homeassistant.core"].Context = lambda **kwargs: types.SimpleNamespace(**kwargs)
    fake["homeassistant.exceptions"].HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    fake["homeassistant.helpers.entity_registry"].async_get = lambda hass: hass.registry
    fake["homeassistant.helpers.icon"].async_get_icons = AsyncMock(return_value={})
    spec = importlib.util.spec_from_file_location(package.__name__ + ".api", BUNDLE / "api.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, fake):
        spec.loader.exec_module(module)
    return module


API = load_api()
ICON_GLOBALS = API.IconResolver.resolve.__globals__


class Store:
    def __init__(self):
        self.data = None
        self.fail = False

    async def async_save(self, data):
        if self.fail:
            raise OSError("simulated storage failure")
        self.data = copy.deepcopy(data)


class Permissions:
    def __init__(self, read=True, control=True):
        self.read, self.control = read, control

    def check_entity(self, entity, policy):
        return self.read if policy == "read" else self.control


class HAPluginTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        API.persistent_notification.async_create.reset_mock()
        API.persistent_notification.async_dismiss.reset_mock()
        # Tiny stand-in for HA's installed frontend assets, not a shipped catalogue.
        self.frontend_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.frontend_dir.cleanup)
        mdi = Path(self.frontend_dir.name) / "static/mdi"
        mdi.mkdir(parents=True)
        names = ("lightbulb", "lightbulb-off", "ceiling-light", "ceiling-light-outline",
                 "lamp", "desk-lamp", "power-plug", "power-plug-off")
        (mdi / "test-chunk.json").write_text(json.dumps({name: "M0,0H24V24H0Z" for name in names}))
        (mdi / "iconMetadata.json").write_text(json.dumps({"parts": [{"file": "test-chunk"}]}))
        self.menu = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.state = types.SimpleNamespace(entity_id="light.wohnzimmer", state="off", attributes={"friendly_name": "Wohnzimmer"})
        self.calls = []
        async def service(domain, service, data, blocking, context):
            self.calls.append((domain, service, data, context.user_id))
            self.state.state = "on" if self.state.state == "off" else "off"
        self.hass = types.SimpleNamespace(data={},
            registry=types.SimpleNamespace(async_get=lambda entity: None),
            async_add_executor_job=lambda func, *args: asyncio.to_thread(func, *args),
            states=types.SimpleNamespace(get=lambda entity: self.state if entity == self.state.entity_id else None,
                                        async_all=lambda: [self.state]),
            services=types.SimpleNamespace(async_call=service))
        self.store = Store()
        self.runtime = API.CompanionRuntime(self.hass, self.store, self.menu)
        self.runtime.icons.frontend.root = Path(self.frontend_dir.name)
        self.hass.data[API.DOMAIN] = {"runtime": self.runtime}
        self.users = {
            "admin": types.SimpleNamespace(id="admin-id", is_admin=True, is_active=True, permissions=Permissions()),
            "receiver": types.SimpleNamespace(id="receiver-id", is_admin=False, is_active=True, permissions=Permissions()),
            "reader": types.SimpleNamespace(id="reader-id", is_admin=False, is_active=True, permissions=Permissions(control=False)),
            "denied": types.SimpleNamespace(id="denied-id", is_admin=False, is_active=True, permissions=Permissions(read=False, control=False)),
        }
        for name, user in self.users.items():
            user.name, user.system_generated = name, False
        self.hass.auth = types.SimpleNamespace(
            async_get_users=AsyncMock(side_effect=lambda: list(self.users.values())),
            async_get_user=AsyncMock(side_effect=lambda user_id: next(
                (user for user in self.users.values() if user.id == user_id), None)))
        @web.middleware
        async def test_auth(request, handler):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if token in self.users:
                request["hass_user"] = self.users[token]
            return await handler(request)
        app = web.Application(middlewares=[test_auth])
        for cls in (API.MenuView, API.StatesView, API.ActionsView, API.ConfigView, API.ConfigurationView,
                    API.UsersView, API.PreviewView, API.CompatibilityView, API.UpdateAdminView, API.ReceiverUpdateView):
            view = cls(self.hass)
            self.assertTrue(view.requires_auth)
            for method in ("get", "post", "put"):
                if hasattr(view, method):
                    app.router.add_route(method.upper(), view.url, getattr(view, method))
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.url = "http://127.0.0.1:" + str(site._server.sockets[0].getsockname()[1])
        self.session = ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()

    async def request(self, method, route, user="admin", body=None, peer_headers=None):
        return await self.session.request(method, self.url + API.BASE + route,
            headers={"Authorization": "Bearer " + user,
                     **({COMPONENT_HEADER: "receiver", VERSION_HEADER: VERSION, PROTOCOL_HEADER: str(PROTOCOL_VERSION)}
                        if peer_headers is None else peer_headers)}, json=body)

    async def test_mismatched_or_unidentified_receivers_are_blocked_on_all_routes(self):
        for headers, reason in [({COMPONENT_HEADER: "receiver", VERSION_HEADER: "99.0.0", PROTOCOL_HEADER: "99"}, "protocol_mismatch"),
                                ({}, "unidentified_peer"),
                                ({COMPONENT_HEADER: "other", VERSION_HEADER: VERSION}, "unidentified_peer"),
                                ({COMPONENT_HEADER: "receiver", VERSION_HEADER: "invalid"}, "unidentified_peer")]:
            for method, route in [("GET", "/menu"), ("GET", "/states"), ("POST", "/actions")]:
                async with await self.request(method, route, "receiver", self.command() if method == "POST" else None,
                                              peer_headers=headers) as response:
                    self.assertEqual(response.status, 426)
                    self.assertEqual((await response.json())["error"], reason)
                    self.assertEqual(response.headers[VERSION_HEADER], VERSION)
                    self.assertEqual(response.headers[COMPONENT_HEADER], "homeassistant")
            async with await self.request("GET", "/compatibility") as response:
                status = await response.json()
                self.assertEqual(status["version"], VERSION)
                self.assertEqual(status["receivers"][0]["status"], reason)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.store.data)

    async def test_compatibility_status_recovers_expires_and_requires_admin(self):
        async with await self.request("GET", "/menu", "receiver", peer_headers={}) as response:
            self.assertEqual(response.status, 426)
        async with await self.request("GET", "/menu", "receiver") as response:
            self.assertEqual(response.status, 200)
        async with await self.request("GET", "/compatibility") as response:
            status = await response.json()
            self.assertEqual(len(status["receivers"]), 1)
            self.assertEqual(status["receivers"][0]["status"], "compatible")
            self.assertNotIn("seen", status["receivers"][0])
        for user, expected in [("receiver", 403), ("none", 401)]:
            async with await self.request("GET", "/compatibility", user) as response:
                self.assertEqual(response.status, expected)
        for receiver in self.runtime.receivers.values():
            receiver["seen"] -= 301
        async with await self.request("GET", "/compatibility") as response:
            self.assertEqual((await response.json())["receivers"], [])

    async def test_editor_language_reads_live_options_without_changing_menu(self):
        original = copy.deepcopy(self.runtime.menu)
        async with await self.request("GET", "/compatibility") as response:
            self.assertIsNone((await response.json())["editor_language"])
        entry = self.runtime.config_entry = types.SimpleNamespace(options={})
        for options, expected in [({}, None), ({"language": "en"}, "en"),
                                  ({"language": "de"}, "de"), ({"language": "auto"}, "auto"),
                                  ({"language": "fr"}, None)]:
            with self.subTest(options=options):
                entry.options = options
                async with await self.request("GET", "/compatibility") as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual((await response.json())["editor_language"], expected)
                self.assertEqual(self.runtime.menu, original)
                self.assertIsNone(self.store.data)

    async def test_appearance_options_preserve_menus_and_invalidate_stale_editor_saves(self):
        self.runtime.menu = API.validate_configuration(self.runtime.menu)
        before = copy.deepcopy(self.runtime.menu)
        display = {"font_family": "MySkinFont", "font_size": 36}
        await self.runtime.async_set_display(display)
        self.assertEqual(self.runtime.menu["menus"], before["menus"])
        self.assertEqual(self.runtime.menu["revision"], before["revision"] + 1)
        self.assertEqual(self.store.data, self.runtime.menu)
        async with await self.request("GET", "/menu", "receiver") as response:
            self.assertEqual((await response.json())["display"], display)
        async with await self.request("PUT", "/configuration", body=before) as response:
            self.assertEqual(response.status, 409)
            self.assertEqual((await response.json())["error"], "stale_menu")
        after = copy.deepcopy(self.runtime.menu)
        await self.runtime.async_set_display(display)
        self.assertEqual(self.runtime.menu, after, "Unchanged options do not increment the revision")

    async def test_appearance_option_failures_do_not_change_live_or_stored_configuration(self):
        self.runtime.menu = API.validate_configuration(self.runtime.menu)
        before = copy.deepcopy(self.runtime.menu)
        await self.runtime.async_set_display(before["display"])
        self.assertIsNone(self.store.data)
        self.store.fail = True
        with self.assertRaises(OSError):
            await self.runtime.async_set_display({"font_family": "Fixed", "font_size": 36})
        self.assertEqual(self.runtime.menu, before)
        self.assertIsNone(self.store.data)
        self.store.fail = False
        self.runtime.menu["revision"] = 2147483647
        with self.assertRaisesRegex(API.HomeAssistantError, "revision_limit"):
            await self.runtime.async_set_display({"font_family": "Fixed", "font_size": 36})
        self.runtime.active = False
        with self.assertRaisesRegex(API.HomeAssistantError, "integration_unavailable"):
            await self.runtime.async_set_display({"font_family": "Fixed", "font_size": 36})
        self.assertEqual(self.runtime.menu["display"], before["display"])
        self.assertIsNone(self.store.data)
    async def test_editor_status_is_debug_only_deduplicated_and_removes_old_notices(self):
        create = API.persistent_notification.async_create
        dismiss = API.persistent_notification.async_dismiss
        self.runtime.updates = types.SimpleNamespace(snapshot=AsyncMock(return_value={"hacs": None}))
        with patch.object(API._LOGGER, "isEnabledFor", return_value=False):
            self.runtime.log_editor_status([], {"hacs": None}, "de")
        self.assertEqual(self.runtime.editor_status_messages, {}, "Enabling DEBUG later must still log the current status")
        with self.assertLogs(API._LOGGER, level="DEBUG") as logs:
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual(response.status, 200)
        self.assertEqual(len(logs.records), 3)
        self.assertTrue(all(record.levelname == "DEBUG" for record in logs.records))
        self.assertIn("HA-Integration", logs.records[0].getMessage())
        self.assertIn("Noch keine Receiver-Anfrage", logs.records[1].getMessage())
        self.assertIn("HACS-Update nicht verfügbar", logs.records[2].getMessage())
        self.assertEqual({call.args[1] for call in dismiss.call_args_list},
                         {"enigmaha_companion_version", "enigmaha_companion_no_receiver", "enigmaha_companion_hacs"})
        with self.assertNoLogs(API._LOGGER, level="DEBUG"):
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual(response.status, 200)
        self.assertEqual(dismiss.call_count, 3, "Old notices are cleaned only once per runtime")
        async with await self.request("GET", "/menu", "receiver") as response:
            self.assertEqual(response.status, 200)
        self.runtime.updates.snapshot.return_value = {"hacs": {"entity_id": "update.enigmaha"}}
        with self.assertNoLogs(API._LOGGER, level="DEBUG"):
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual(response.status, 200)
        self.runtime.config_entry = types.SimpleNamespace(options={"language": "en"})
        with self.assertLogs(API._LOGGER, level="DEBUG") as logs:
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual(response.status, 200)
        self.assertEqual(len(logs.records), 1)
        self.assertIn("HA integration", logs.records[0].getMessage())
        create.assert_not_called()

    async def test_automatic_debug_language_follows_ha_system_language(self):
        self.runtime.config_entry = types.SimpleNamespace(options={"language": "auto"})
        self.hass.config = types.SimpleNamespace(language="en-GB")
        with self.assertLogs(API._LOGGER, level="DEBUG") as logs:
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual((await response.json())["editor_language"], "auto")
        self.assertIn("HA integration", logs.records[0].getMessage())
        self.hass.config.language = "de_DE"
        with self.assertLogs(API._LOGGER, level="DEBUG") as logs:
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual(response.status, 200)
        self.assertIn("HA-Integration", logs.records[0].getMessage())

    async def test_receiver_tracking_is_bounded(self):
        user = self.users["receiver"]
        for index in range(70):
            request = types.SimpleNamespace(remote=str(index), headers={COMPONENT_HEADER: "receiver", VERSION_HEADER: VERSION})
            await self.runtime.check_receiver(request, user)
        self.assertEqual(len(self.runtime.receivers), 64)

    def command(self, **changes):
        return dict({"schema_version": 1, "revision": 1, "entry_id": "ceiling", "action": "toggle"}, **changes)

    async def test_receiver_client_calls_actual_plugin_views(self):
        client = CompanionClient(self.url, "receiver")
        menu = await asyncio.to_thread(client.get_menu)
        states = await asyncio.to_thread(client.get_states, menu)
        self.assertEqual(states["light.wohnzimmer"]["state"], "off")
        self.assertEqual(states["light.wohnzimmer"]["icon"]["name"], "mdi:lightbulb-off")
        await asyncio.to_thread(client.execute, self.command())
        self.assertEqual(self.calls, [("light", "toggle", {"entity_id": "light.wohnzimmer"}, "receiver-id")])
        states = await asyncio.to_thread(client.get_states, menu)
        self.assertEqual(states["light.wohnzimmer"]["icon"]["name"], "mdi:lightbulb")

    async def test_receiver_reports_changed_ha_protocol_without_sending_an_action(self):
        client = CompanionClient(self.url, "receiver")
        await asyncio.to_thread(client.get_menu)
        with patch.object(API, "VERSION", "99.0.0"), patch.object(API, "PROTOCOL_VERSION", 99), patch.object(API, "peer_status", return_value="protocol_mismatch"):
            for operation, args in [(client.get_menu, ()), (client.get_states, (self.menu,)),
                                    (client.execute, (self.command(),))]:
                with self.assertRaises(ClientError) as caught:
                    await asyncio.to_thread(operation, *args)
                self.assertEqual(caught.exception.code, "protocol_mismatch")
                self.assertEqual(caught.exception.peer_version, "99.0.0")
                self.assertEqual(caught.exception.peer_protocol, 99)
        self.assertEqual(self.calls, [])

    async def test_different_release_same_protocol_allows_menu_states_and_action(self):
        headers = {COMPONENT_HEADER: "receiver", VERSION_HEADER: "99.0.0", PROTOCOL_HEADER: str(PROTOCOL_VERSION)}
        for method, route in [("GET", "/menu"), ("GET", "/states"), ("POST", "/actions")]:
            async with await self.request(method, route, "receiver", self.command() if method == "POST" else None,
                                          peer_headers=headers) as response:
                self.assertEqual(response.status, 200)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.runtime.recent_receivers()[0]["status"], "version_mismatch")

    async def test_current_entity_icons_follow_overrides_platform_states_and_device_class(self):
        entry = types.SimpleNamespace(icon=None, platform="test_lamp", translation_key="ceiling")
        self.hass.registry.async_get = lambda entity: entry
        resources = {
            "entity": {"test_lamp": {"light": {"ceiling": {
                "default": "mdi:ceiling-light", "state": {"off": "mdi:ceiling-light-outline"}}}}},
            "entity_component": {"light": {"_": {"default": "mdi:lightbulb", "state": {"off": "mdi:lightbulb-off"}},
                "outlet": {"default": "mdi:power-plug", "state": {"off": "mdi:power-plug-off"}}}},
        }
        async def get_icons(hass, category, integrations):
            return resources[category]
        with patch.dict(ICON_GLOBALS, async_get_icons=get_icons):
            for state, expected in (("off", "mdi:ceiling-light-outline"), ("on", "mdi:ceiling-light")):
                self.state.state = state
                async with await self.request("GET", "/states", "receiver") as response:
                    body = await response.json()
                self.assertEqual(body["states"][self.state.entity_id]["icon"], expected)
                self.assertTrue(body["icons"][expected].startswith("M"))
            self.state.attributes["icon"] = "mdi:lamp"
            self.assertEqual((await self.runtime.icons.resolve(self.state))["name"], "mdi:lamp")
            entry.icon = "mdi:desk-lamp"
            self.assertEqual((await self.runtime.icons.resolve(self.state))["name"], "mdi:desk-lamp")
            entry.icon = None
            self.state.attributes.pop("icon")
            entry.translation_key = None
            self.state.attributes["device_class"] = "outlet"
            self.state.state = "off"
            self.assertEqual((await self.runtime.icons.resolve(self.state))["name"], "mdi:power-plug-off")
            self.state.attributes["icon"] = "custom:browser-only"
            self.assertEqual((await self.runtime.icons.resolve(self.state))["name"], "mdi:lightbulb-off")
            self.state.state = "unavailable"
            self.assertIsNone(await self.runtime.icons.resolve(self.state))

    async def test_denied_and_unavailable_entities_do_not_ship_icons(self):
        async with await self.request("GET", "/states", "denied") as response:
            body = await response.json()
        self.assertEqual(body["icons"], {})
        self.state.state = "unavailable"
        async with await self.request("GET", "/states", "receiver") as response:
            body = await response.json()
        self.assertEqual(body["icons"], {})
        self.assertIsNone(body["states"][self.state.entity_id]["icon"])

    async def test_missing_frontend_assets_keep_states_and_actions_available(self):
        self.runtime.icons.frontend.root = Path(self.frontend_dir.name) / "missing"
        async with await self.request("GET", "/states", "receiver") as response:
            self.assertEqual(response.status, 200)
            body = await response.json()
        self.assertEqual(body["icons"], {})
        self.assertEqual(body["states"][self.state.entity_id]["state"], "off")
        self.assertIsNone(body["states"][self.state.entity_id]["icon"])
        async with await self.request("POST", "/actions", "receiver", self.command()) as response:
            self.assertEqual(response.status, 200)

    async def test_icon_resolution_keeps_snapshot_revision_if_menu_changes_while_awaiting(self):
        async def resolve(state):
            self.runtime.menu = dict(self.runtime.menu, revision=2)
            return {"name": "mdi:lightbulb", "path": "M0,0H24V24H0Z"}
        self.runtime.icons.resolve = resolve
        async with await self.request("GET", "/states", "receiver") as response:
            body = await response.json()
        self.assertEqual(body["revision"], 1)
        self.assertEqual(self.runtime.menu["revision"], 2)

    async def test_auth_and_admin_boundary(self):
        for method, route, user, expected in [("GET", "/menu", "none", 401),
                ("GET", "/config", "receiver", 403),
                ("PUT", "/config", "receiver", 403)]:
            async with await self.request(method, route, user, self.menu if method == "PUT" else None) as response:
                self.assertEqual(response.status, expected)

    async def test_menu_and_states_filter_permissions(self):
        async with await self.request("GET", "/menu", "denied") as response:
            menu = await response.json()
            self.assertEqual(menu["root"]["children"], [])
        async with await self.request("GET", "/states", "denied") as response:
            self.assertEqual((await response.json())["states"], {})
        async with await self.request("GET", "/menu", "reader") as response:
            self.assertEqual((await response.json())["root"]["children"][0]["children"][0]["actions"], [])
        async with await self.request("POST", "/actions", "reader", self.command()) as response:
            self.assertEqual(response.status, 403)
        self.assertEqual(self.calls, [])

    async def test_save_increments_revision_and_rejects_stale_actions(self):
        changed = copy.deepcopy(self.menu)
        changed["root"]["label"] = "Mein Zuhause"
        async with await self.request("PUT", "/config", body=changed) as response:
            self.assertEqual(response.status, 200)
            saved = await response.json()
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(self.store.data, API.validate_configuration(saved))
        async with await self.request("POST", "/actions", "receiver", self.command()) as response:
            self.assertEqual(response.status, 409)
        async with await self.request("PUT", "/config", body=changed) as response:
            self.assertEqual(response.status, 409)
        self.assertEqual(self.calls, [])

    async def test_bad_payloads_cannot_call_service_or_replace_menu(self):
        async with await self.request("POST", "/actions", "receiver", self.command(entity_id="light.other")) as response:
            self.assertEqual(response.status, 400)
        self.menu["schema_version"] = 9
        async with await self.request("PUT", "/config", body=self.menu) as response:
            self.assertEqual(response.status, 400)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.store.data)

    async def test_storage_failure_keeps_previous_revision(self):
        self.store.fail = True
        async with await self.request("PUT", "/config", body=self.menu) as response:
            self.assertEqual(response.status, 500)
        self.assertEqual(self.runtime.menu["revision"], 1)

    async def test_unloaded_integration_is_unavailable(self):
        self.runtime.active = False
        async with await self.request("GET", "/menu", "receiver") as response:
            self.assertEqual(response.status, 503)

    async def test_unavailable_entity_rejected(self):
        self.state.state = "unavailable"
        async with await self.request("POST", "/actions", "receiver", self.command()) as response:
            self.assertEqual(response.status, 409)
        self.assertEqual(self.calls, [])


    async def test_collection_filters_ancestors_states_actions_and_admin_tokens(self):
        config = API.validate_configuration(self.menu)
        root = config["menus"][0]
        root["access"] = {"mode": "users", "users": ["receiver-id", "reader-id"]}
        root["children"][0]["access"] = {"mode": "users", "users": ["reader-id"]}
        # A child cannot grant access through a denied ancestor.
        root["children"][0]["children"][0]["access"] = {"mode": "users", "users": ["receiver-id"]}
        self.runtime.menu = API.validate_configuration(config)
        for token in ("receiver", "admin", "reader"):
            async with await self.request("GET", "/states", token) as response:
                self.assertEqual((await response.json())["states"], {})
            async with await self.request("POST", "/actions", token, self.command()) as response:
                self.assertEqual(response.status, 404)
        async with await self.request("GET", "/menu", "admin") as response:
            self.assertEqual((await response.json())["root"]["id"], "__enigmaha_no_menu")
        self.assertEqual(self.calls, [])

    async def test_multiple_menus_duplicate_entity_and_same_user_tokens(self):
        config = API.validate_configuration(self.menu)
        first = config["menus"][0]
        first["access"] = {"mode": "users", "users": ["reader-id"]}
        second = {"type": "menu", "id": "shared", "label": "Gemeinsam", "access": {"mode": "all"},
                  "children": [{"type": "entity", "id": "shared-light", "label": "Licht",
                                "entity_id": "light.wohnzimmer", "actions": ["toggle"]}]}
        config["menus"].append(second)
        self.runtime.menu = API.validate_configuration(config)
        self.users["another-token"] = self.users["receiver"]
        for token in ("receiver", "another-token"):
            async with await self.request("GET", "/menu", token) as response:
                body = await response.json()
                self.assertEqual(body["root"]["id"], "shared")
                self.assertNotIn("access", json.dumps(body))
                self.assertNotIn("reader-id", json.dumps(body))
            async with await self.request("POST", "/actions", token, self.command(entry_id="ceiling")) as response:
                self.assertEqual(response.status, 404)
            async with await self.request("POST", "/actions", token, self.command(entry_id="shared-light")) as response:
                self.assertEqual(response.status, 200)
        async with await self.request("GET", "/menu", "reader") as response:
            body = await response.json()
            self.assertEqual([node["id"] for node in body["root"]["children"]], ["home", "shared"])
            self.assertEqual(body["root"]["children"][1]["children"][0]["actions"], [])
        self.assertEqual(len(self.calls), 2)

    async def test_configuration_saving_and_legacy_editor_cannot_erase_acl(self):
        async with await self.request("GET", "/configuration") as response:
            config = await response.json()
        config["menus"][0]["access"] = {"mode": "users", "users": ["receiver-id", "deleted-user"]}
        async with await self.request("PUT", "/configuration", body=config) as response:
            self.assertEqual(response.status, 200)
            saved = await response.json()
        self.assertEqual(saved["revision"], 2)
        self.assertEqual(self.store.data, saved)
        for method in ("GET", "PUT"):
            async with await self.request(method, "/config", body=self.menu if method == "PUT" else None) as response:
                self.assertEqual(response.status, 409)
                self.assertEqual((await response.json())["error"], "configuration_upgrade_required")
        async with await self.request("PUT", "/configuration", body=config) as response:
            self.assertEqual(response.status, 409)
        async with await self.request("POST", "/actions", "receiver", self.command()) as response:
            self.assertEqual(response.status, 409)
        self.store.fail = True
        async with await self.request("PUT", "/configuration", body=saved) as response:
            self.assertEqual(response.status, 500)
        self.assertEqual(self.runtime.menu, saved)

    async def test_preview_uses_unsaved_configuration_without_writing_and_rejects_missing_users(self):
        config = API.validate_configuration(self.menu)
        config["menus"][0]["access"] = {"mode": "users", "users": []}
        body = {"configuration": config, "user_id": "receiver-id"}
        async with await self.request("POST", "/preview", body=body) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual((await response.json())["root"]["children"], [])
        config["menus"][0]["access"]["users"] = ["receiver-id"]
        async with await self.request("POST", "/preview", body=body) as response:
            self.assertEqual(await response.json(), API.filtered_menu(config, self.users["receiver"]))
        for user_id in ("deleted-user", "reader-id"):
            self.users["reader"].is_active = False
            async with await self.request("POST", "/preview", body=dict(body, user_id=user_id)) as response:
                self.assertEqual(response.status, 404)
        self.assertEqual(self.runtime.menu, self.menu)
        self.assertIsNone(self.store.data)
        self.assertEqual(self.calls, [])

    async def test_user_list_and_new_routes_are_admin_only(self):
        self.users["reader"].is_active = False
        self.users["denied"].system_generated = True
        async with await self.request("GET", "/users") as response:
            self.assertEqual(await response.json(), {"users": [{"id": "admin-id", "name": "admin"},
                                                              {"id": "receiver-id", "name": "receiver"}]})
        for method, route in (("GET", "/users"), ("GET", "/configuration"),
                              ("PUT", "/configuration"), ("POST", "/preview")):
            for token, status in (("receiver", 403), ("none", 401)):
                async with await self.request(method, route, token, {}) as response:
                    self.assertEqual(response.status, status)

    async def test_revoked_menu_rejects_cached_action_and_hides_states(self):
        config = API.validate_configuration(self.menu)
        self.runtime.menu = config
        async with await self.request("GET", "/menu", "receiver") as response:
            self.assertTrue((await response.json())["root"]["children"])
        config["menus"][0]["access"] = {"mode": "none"}
        async with await self.request("POST", "/actions", "receiver", self.command()) as response:
            self.assertEqual(response.status, 404)
        async with await self.request("GET", "/states", "receiver") as response:
            self.assertEqual((await response.json())["states"], {})
        self.assertEqual(self.calls, [])


class MenuConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.legacy = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        self.config = API.validate_configuration(self.legacy)

    def test_migration_is_lossless_detached_and_idempotent(self):
        self.assertEqual(API.legacy_menu(self.config), self.legacy)
        self.assertEqual(API.validate_configuration(self.config), self.config)
        self.config["menus"][0]["children"].clear()
        self.assertTrue(self.legacy["root"]["children"])

    def test_empty_selected_users_and_missing_users_never_grant_access(self):
        for access in ({"mode": "none"}, {"mode": "users", "users": []},
                       {"mode": "users", "users": ["deleted-user"]}):
            self.config["menus"][0]["access"] = access
            user = types.SimpleNamespace(id="receiver-id", permissions=Permissions())
            self.assertEqual(API.filtered_menu(self.config, user)["root"]["children"], [])
            self.assertIsNone(API.legacy_menu(self.config))

    def test_invalid_access_payloads_and_unknown_fields_are_rejected(self):
        for access in ({"mode": "inherit"}, {"mode": []}, {"mode": "users"},
                       {"mode": "users", "users": ["a", "a"]}, {"mode": "users", "users": [None]},
                       {"mode": "users", "users": "a"}, {"mode": "all", "users": []},
                       {"mode": "all", "extra": True}):
            with self.subTest(access=access):
                self.config["menus"][0]["access"] = access
                with self.assertRaises(API.ProtocolError):
                    API.validate_configuration(self.config)
        self.config = API.validate_configuration(self.legacy)
        self.config["menus"][0]["children"][0]["access"] = {"mode": "all"}
        with self.assertRaises(API.ProtocolError):
            API.validate_configuration(self.config)

    def test_cross_menu_ids_and_receiver_depth_limits_are_enforced(self):
        self.config["menus"].append(copy.deepcopy(self.config["menus"][0]))
        with self.assertRaises(API.ProtocolError):
            API.validate_configuration(self.config)
        self.config = API.validate_configuration(self.legacy)
        root = self.config["menus"][0]
        root["children"] = []
        for i in range(8):
            child = {"type": "menu", "id": "deep" + str(i), "label": "Deep", "children": []}
            root["children"].append(child)
            root = child
        API.validate_configuration(self.config)
        self.config["menus"].append({"type": "menu", "id": "extra", "label": "Extra", "children": []})
        with self.assertRaises(API.ProtocolError):
            API.validate_configuration(self.config)

    def test_selection_root_collision_and_empty_collection(self):
        self.config["menus"][0]["id"] = "__enigmaha_menus"
        self.config["menus"].append({"type": "menu", "id": "extra", "label": "Extra", "children": []})
        user = types.SimpleNamespace(id="receiver-id", permissions=Permissions())
        menu = API.filtered_menu(self.config, user)
        self.assertEqual(menu["root"]["id"], "__enigmaha_menus_1")
        self.config["menus"] = []
        self.assertEqual(API.filtered_menu(self.config, user)["root"]["id"], "__enigmaha_no_menu")


if __name__ == "__main__":
    unittest.main()
