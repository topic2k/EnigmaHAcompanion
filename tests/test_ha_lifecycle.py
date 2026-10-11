"""Setup/unload and flow import checks with minimal HA interfaces."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_registers_once_and_unload_disables_runtime(self):
        fake = {}
        for name in ("homeassistant", "homeassistant.components", "homeassistant.components.frontend",
                     "homeassistant.components.panel_custom", "homeassistant.components.http",
                     "homeassistant.helpers", "homeassistant.helpers.storage", "homeassistant.auth",
                     "homeassistant.auth.permissions", "homeassistant.auth.permissions.const",
                     "homeassistant.core", "homeassistant.exceptions", "homeassistant.helpers.icon",
                     "homeassistant.helpers.entity_registry", "homeassistant.helpers.issue_registry"):
            fake[name] = types.ModuleType(name)
        panels = []
        async def register_panel(hass, **kwargs):
            panels.append(kwargs)
        removed = []
        fake["homeassistant.components.frontend"].async_remove_panel = lambda hass, domain: removed.append(domain)
        fake["homeassistant.components.panel_custom"].async_register_panel = register_panel
        fake["homeassistant.components.http"].StaticPathConfig = lambda *args: args
        fake["homeassistant.components.http"].HomeAssistantView = object
        fake["homeassistant.components.http"].KEY_HASS_USER = "hass_user"
        fake["homeassistant.auth.permissions.const"].POLICY_READ = "read"
        fake["homeassistant.auth.permissions.const"].POLICY_CONTROL = "control"
        fake["homeassistant.core"].Context = lambda **kwargs: kwargs
        fake["homeassistant.exceptions"].HomeAssistantError = RuntimeError
        fake["homeassistant.helpers.icon"].async_get_icons = AsyncMock(return_value={})
        fake["homeassistant.helpers.issue_registry"].async_delete_issue = lambda *args: None
        store = types.SimpleNamespace(async_load=AsyncMock(return_value=None), async_save=AsyncMock())
        fake["homeassistant.helpers.storage"].Store = lambda *args: store
        views = []
        hass = types.SimpleNamespace(data={}, http=types.SimpleNamespace(
            async_register_static_paths=AsyncMock(), register_view=lambda view: views.append(view)))
        spec = importlib.util.spec_from_file_location("eha_lifecycle_test", BUNDLE / "__init__.py",
                                                      submodule_search_locations=[str(BUNDLE)])
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {**fake, "eha_lifecycle_test": module}):
            spec.loader.exec_module(module)
            self.assertTrue(await module.async_setup(hass, {}))
            self.assertTrue(await module.async_setup(hass, {}))
            self.assertEqual(len(views), 7)
            hass.http.async_register_static_paths.assert_awaited_once()
            self.assertTrue(await module.async_setup_entry(hass, object()))
            runtime = hass.data[module.DOMAIN]["runtime"]
            self.assertEqual(runtime.menu["root"]["children"], [])
            self.assertTrue(panels[0]["require_admin"])
            self.assertTrue(await module.async_unload_entry(hass, object()))
            self.assertFalse(runtime.active)
            self.assertNotIn("runtime", hass.data[module.DOMAIN])
            self.assertEqual(removed, [module.DOMAIN])

    async def test_config_flow_creates_single_named_entry(self):
        class Flow:
            def __init_subclass__(cls, **kwargs):
                pass
            async def async_set_unique_id(self, unique_id):
                self.unique_id = unique_id
            def _abort_if_unique_id_configured(self):
                pass
            def async_show_form(self, **kwargs):
                return {"type": "form", **kwargs}
            def async_create_entry(self, **kwargs):
                return {"type": "create_entry", **kwargs}
        ha = types.ModuleType("homeassistant")
        ha.config_entries = types.SimpleNamespace(ConfigFlow=Flow)
        package = types.ModuleType("eha_flow_test")
        package.__path__ = [str(BUNDLE)]
        spec = importlib.util.spec_from_file_location("eha_flow_test.config_flow", BUNDLE / "config_flow.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"homeassistant": ha, "eha_flow_test": package}):
            spec.loader.exec_module(module)
            flow = module.CompanionConfigFlow()
            self.assertEqual((await flow.async_step_user())["type"], "form")
            self.assertEqual(await flow.async_step_user({}),
                             {"type": "create_entry", "title": "EnigmaHA Companion", "data": {}})
            self.assertEqual(flow.unique_id, "enigmaha_companion")
