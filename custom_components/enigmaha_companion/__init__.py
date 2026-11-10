"""EnigmaHA Companion custom integration."""

import hashlib
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.storage import Store

from .api import CompanionRuntime, register_views
from .const import DOMAIN, VERSION, empty_menu
from .menus import validate_configuration
from .updates import UpdateManager
from .repair_issues import RepairCoordinator
from .entity_issues import EntityIssueCoordinator

LEGACY_UPDATE_UNIQUE_ID = DOMAIN + "_integration_update"


def _remove_legacy_update_entity(hass, entry):
    registry = async_get_entity_registry(hass)
    for entity in tuple(registry.entities.values()):
        if (entity.domain == "update" and entity.platform == DOMAIN
                and entity.unique_id == LEGACY_UPDATE_UNIQUE_ID
                and entity.config_entry_id == entry.entry_id):
            registry.async_remove(entity.entity_id)


def _register_device(hass, entry):
    registry = async_get_device_registry(hass)
    device = registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, DOMAIN)},
        name="EnigmaHA Companion",
        sw_version=VERSION,
    )
    if device.sw_version != VERSION:
        registry.async_update_device(device.id, sw_version=VERSION)


def _panel_module_url(panel_path):
    content_hash = hashlib.sha256(panel_path.read_bytes()).hexdigest()
    return f"/enigmaha_companion/panel.js?v={VERSION}-{content_hash}"


async def async_setup(hass, config):
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig("/enigmaha_companion/panel.js",
                             str(Path(__file__).parent / "panel.js"), False)
        ])
        register_views(hass)
        data["registered"] = True
    return True


async def async_setup_entry(hass, entry):
    _remove_legacy_update_entity(hass, entry)
    _register_device(hass, entry)
    store = Store(hass, 1, DOMAIN + ".menu")
    saved = await store.async_load()
    menu = validate_configuration(saved if saved is not None else empty_menu())
    if saved is not None and saved.get("schema_version") == 1:
        # Keep the storage envelope/key; the payload migration is idempotent and
        # preserves menu IDs, display settings and the persisted revision.
        await store.async_save(menu)
    runtime = CompanionRuntime(hass, store, menu, entry)
    update_store = Store(hass, 1, DOMAIN + ".update")
    runtime.updates = UpdateManager(hass, update_store, await update_store.async_load())
    repair_store = Store(hass, 1, DOMAIN + ".repairs")
    runtime.repairs = RepairCoordinator(hass, repair_store, runtime, await repair_store.async_load())
    runtime.entity_issues = EntityIssueCoordinator(hass, runtime)
    runtime.updates.on_change = runtime.repairs.sync
    hass.data[DOMAIN]["runtime"] = runtime
    await runtime.entity_issues.async_start()
    async with runtime.updates.lock:
        await runtime.updates.refresh()
    await runtime.repairs.sync()
    await panel_custom.async_register_panel(
        hass, frontend_url_path=DOMAIN, webcomponent_name="enigmaha-panel",
        sidebar_title="EnigmaHA Companion", sidebar_icon="mdi:remote-tv",
        module_url=_panel_module_url(Path(__file__).parent / "panel.js"),
        require_admin=True,
    )
    return True


async def async_unload_entry(hass, entry):
    runtime = hass.data[DOMAIN].get("runtime")
    if runtime is not None:
        await runtime.updates.close()
        runtime.repairs.close()
        runtime.entity_issues.close()
        runtime.clear_editor_notifications()
        async with runtime.lock:
            runtime.active = False
            hass.data[DOMAIN].pop("runtime", None)
    frontend.async_remove_panel(hass, DOMAIN)
    return True
