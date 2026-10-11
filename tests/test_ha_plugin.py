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
from unittest.mock import AsyncMock, patch

from aiohttp import ClientSession, web

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]
from companion.client import CompanionClient


def load_api():
    package = types.ModuleType("ha_plugin_test")
    package.__path__ = [str(BUNDLE)]
    sys.modules[package.__name__] = package
    fake = {}
    for name in ("homeassistant", "homeassistant.auth", "homeassistant.auth.permissions",
                 "homeassistant.auth.permissions.const", "homeassistant.components",
                 "homeassistant.components.http", "homeassistant.core", "homeassistant.exceptions",
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
        @web.middleware
        async def test_auth(request, handler):
            token = request.headers.get("Authorization", "").removeprefix("Bearer ")
            if token in self.users:
                request["hass_user"] = self.users[token]
            return await handler(request)
        app = web.Application(middlewares=[test_auth])
        for cls in (API.MenuView, API.StatesView, API.ActionsView, API.ConfigView):
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

    async def request(self, method, route, user="admin", body=None):
        return await self.session.request(method, self.url + API.BASE + route,
                                          headers={"Authorization": "Bearer " + user}, json=body)

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
            self.assertEqual(menu["root"]["children"][0]["children"][0]["type"], "menu")
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
        self.assertEqual(self.store.data, saved)
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


if __name__ == "__main__":
    unittest.main()
