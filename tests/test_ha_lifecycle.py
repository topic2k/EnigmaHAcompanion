"""Setup/unload and flow import checks with minimal HA interfaces."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_setup_registers_once_and_unload_disables_runtime(self):
        await self.check_setup()

    async def test_setup_migrates_published_menu_and_reloads_without_repeating_migration(self):
        saved = json.loads((ROOT / "protocol/menu.example.json").read_text(encoding="utf-8"))
        migrated = await self.check_setup(saved)
        await self.check_setup(migrated)

    async def test_setup_removes_legacy_update_entity_by_registry_identity(self):
        unrelated = [
            types.SimpleNamespace(entity_id="update.marketplace", domain="update", platform="marketplace",
                                  unique_id="enigmaha_companion_integration_update", config_entry_id="entry"),
            types.SimpleNamespace(entity_id="update.hacs", domain="update", platform="hacs",
                                  unique_id="enigmaha_companion_integration_update", config_entry_id="entry"),
            types.SimpleNamespace(entity_id="update.other_unique_id", domain="update", platform="enigmaha_companion",
                                  unique_id="other", config_entry_id="entry"),
            types.SimpleNamespace(entity_id="sensor.legacy", domain="sensor", platform="enigmaha_companion",
                                  unique_id="enigmaha_companion_integration_update", config_entry_id="entry"),
            types.SimpleNamespace(entity_id="update.other_entry", domain="update", platform="enigmaha_companion",
                                  unique_id="enigmaha_companion_integration_update", config_entry_id="other-entry"),
        ]
        for entity_id, disabled_by in (("update.enigmaha_companion", None),
                                       ("update.custom_companion_name", None),
                                       ("update.disabled_companion", "user")):
            with self.subTest(entity_id=entity_id, disabled_by=disabled_by):
                legacy = types.SimpleNamespace(
                    entity_id=entity_id, domain="update", platform="enigmaha_companion",
                    unique_id="enigmaha_companion_integration_update", config_entry_id="entry",
                    disabled_by=disabled_by)
                await self.check_setup(registry_entries=[legacy, *unrelated], expected_removed=[entity_id])

    async def check_setup(self, saved=None, registry_entries=(), expected_removed=()):
        fake = {}
        for name in ("homeassistant", "homeassistant.components", "homeassistant.components.frontend",
                     "homeassistant.components.panel_custom", "homeassistant.components.http", "homeassistant.components.persistent_notification",
                     "homeassistant.helpers", "homeassistant.helpers.storage", "homeassistant.auth",
                     "homeassistant.auth.permissions", "homeassistant.auth.permissions.const",
                     "homeassistant.core", "homeassistant.const", "homeassistant.exceptions", "homeassistant.helpers.icon",
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
        fake["homeassistant.components.persistent_notification"].async_dismiss = lambda *args: None
        fake["homeassistant.helpers.entity_registry"].async_get = lambda hass: hass.registry
        store = types.SimpleNamespace(async_load=AsyncMock(side_effect=[saved, None, None]), async_save=AsyncMock())
        fake["homeassistant.helpers.storage"].Store = lambda *args: store
        views = []
        registry = types.SimpleNamespace(entities={item.entity_id: item for item in registry_entries}, removed=[])
        def remove_entity(entity_id):
            registry.removed.append(entity_id)
            registry.entities.pop(entity_id)
        registry.async_remove = remove_entity
        hass = types.SimpleNamespace(data={}, config_entries=types.SimpleNamespace(
            async_forward_entry_setups=AsyncMock(), async_unload_platforms=AsyncMock(return_value=True)),
            http=types.SimpleNamespace(
            async_register_static_paths=AsyncMock(), register_view=lambda view: views.append(view)), registry=registry)
        spec = importlib.util.spec_from_file_location("eha_lifecycle_test", BUNDLE / "__init__.py",
                                                      submodule_search_locations=[str(BUNDLE)])
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {**fake, "eha_lifecycle_test": module}):
            spec.loader.exec_module(module)
            self.assertTrue(await module.async_setup(hass, {}))
            self.assertTrue(await module.async_setup(hass, {}))
            self.assertEqual(len(views), 11)
            self.assertEqual(sum(view.url.endswith("/info") for view in views), 1)
            hass.http.async_register_static_paths.assert_awaited_once()
            entry = types.SimpleNamespace(options={}, entry_id="entry")
            self.assertTrue(await module.async_setup_entry(hass, entry))
            hass.config_entries.async_forward_entry_setups.assert_not_awaited()
            self.assertEqual(registry.removed, list(expected_removed))
            if expected_removed:
                module._remove_legacy_update_entity(hass, entry)
                self.assertEqual(registry.removed, list(expected_removed))
            self.assertEqual(panels[0]["module_url"], module._panel_module_url(BUNDLE / "panel.js"))
            with tempfile.TemporaryDirectory() as directory:
                first_panel = Path(directory) / "first.js"
                second_panel = Path(directory) / "second.js"
                first_panel.write_text("custom panel build one", encoding="utf-8")
                second_panel.write_text("custom panel build two", encoding="utf-8")
                first_url = module._panel_module_url(first_panel)
                second_url = module._panel_module_url(second_panel)
                self.assertNotEqual(first_url, second_url)
                self.assertTrue(first_url.startswith(f"/enigmaha_companion/panel.js?v={module.VERSION}-"))
                self.assertTrue(second_url.startswith(f"/enigmaha_companion/panel.js?v={module.VERSION}-"))
            runtime = hass.data[module.DOMAIN]["runtime"]
            self.assertIs(runtime.config_entry, entry)
            self.assertEqual(runtime.menu["schema_version"], 2)
            if saved is None:
                self.assertEqual(runtime.menu["menus"][0]["children"], [])
                store.async_save.assert_not_awaited()
            elif saved["schema_version"] == 1:
                self.assertEqual(module.validate_configuration(saved), runtime.menu)
                store.async_save.assert_awaited_once_with(runtime.menu)
            else:
                self.assertEqual(runtime.menu, saved)
                store.async_save.assert_not_awaited()
            self.assertTrue(panels[0]["require_admin"])
            self.assertTrue(await module.async_unload_entry(hass, entry))
            hass.config_entries.async_unload_platforms.assert_not_awaited()
            self.assertFalse(runtime.active)
            self.assertNotIn("runtime", hass.data[module.DOMAIN])
            self.assertEqual(removed, [module.DOMAIN])
            return runtime.menu

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
            def async_abort(self, **kwargs):
                return {"type": "abort", **kwargs}
        ha = types.ModuleType("homeassistant")
        ha.config_entries = types.SimpleNamespace(ConfigFlow=Flow, OptionsFlow=Flow)
        core = types.SimpleNamespace(callback=lambda function: function)
        selectors = types.SimpleNamespace(SelectSelector=lambda config: config)
        schema = types.SimpleNamespace(Schema=lambda value: value,
                                       Required=lambda key, **kwargs: (key, kwargs["default"]))
        package = types.ModuleType("eha_flow_test")
        package.__path__ = [str(BUNDLE)]
        spec = importlib.util.spec_from_file_location("eha_flow_test.config_flow", BUNDLE / "config_flow.py")
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"homeassistant": ha, "eha_flow_test": package,
                                     "homeassistant.core": core,
                                     "homeassistant.exceptions": types.SimpleNamespace(HomeAssistantError=RuntimeError),
                                     "homeassistant.helpers.selector": selectors, "probatio": schema}):
            spec.loader.exec_module(module)
            flow = module.CompanionConfigFlow()
            self.assertEqual((await flow.async_step_user())["type"], "form")
            created = await flow.async_step_user({})
            self.assertEqual(created, {"type": "create_entry", "title": "EnigmaHA Companion",
                                       "data": {}, "options": {"language": "auto"}})
            self.assertEqual(flow.unique_id, "enigmaha_companion")
            entry = types.SimpleNamespace(options={"future_option": "preserved"})
            options = flow.async_get_options_flow(entry)
            options.config_entry = entry
            runtime = types.SimpleNamespace(active=True, menu={"display": {"font_family": "MySkinFont", "font_size": 31}},
                                            async_set_display=AsyncMock())
            options.hass = types.SimpleNamespace(data={module.DOMAIN: {"runtime": runtime}})
            form = await options.async_step_init()
            self.assertEqual(form["step_id"], "init")
            self.assertEqual(form["errors"], {})
            self.assertEqual(entry.options, {"future_option": "preserved"})
            self.assertEqual(form["data_schema"][("language", "de")]["options"], ["de", "en", "auto"])
            self.assertEqual(form["data_schema"][("language", "de")]["translation_key"], "language")
            self.assertEqual(len(form["data_schema"]), 1)
            for language in ("auto", "en", "de"):
                result = await options.async_step_init({"language": language})
                self.assertEqual(result, {"type": "create_entry", "title": "", "data": {
                    "language": language, "future_option": "preserved"}})
                entry.options = result["data"]
                self.assertIn(("language", language), (await options.async_step_init())["data_schema"])
                runtime.async_set_display.assert_not_awaited()
                self.assertEqual(runtime.menu["display"], {"font_family": "MySkinFont", "font_size": 31})
            for invalid in ("fr", "", None, [], {}):
                with self.subTest(language=invalid):
                    result = await options.async_step_init({"language": invalid})
                    self.assertEqual(result["type"], "form")
                    self.assertEqual(result["errors"], {"language": "invalid_language"})
                    self.assertEqual(entry.options["language"], "de")
            entry.options = {"language": "fr"}
            self.assertIn(("language", "de"), (await options.async_step_init())["data_schema"])
            # Newly created entries retain auto when their options are opened.
            entry.options = created["options"]
            self.assertIn(("language", "auto"), (await options.async_step_init())["data_schema"])
            # A stale form must not change the retained legacy display data or
            # write menu storage when saving the editor language.
            runtime.async_set_display.side_effect = OSError("disk full")
            result = await options.async_step_init({"language": "en", "font_family": "Fixed", "font_size": "36"})
            self.assertEqual(result["data"], {"language": "en"})
            runtime.async_set_display.assert_not_awaited()
            runtime.active = False
            self.assertEqual(await options.async_step_init(), {"type": "abort", "reason": "integration_unavailable"})
