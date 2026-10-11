"""EnigmaHA Companion custom integration."""

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.helpers.storage import Store

from .api import CompanionRuntime, register_views
from .const import DOMAIN, VERSION, empty_menu
from .menus import validate_configuration
from .updates import UpdateManager
from .repair_issues import RepairCoordinator

PLATFORMS = [Platform.UPDATE]


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
    runtime.updates.on_change = runtime.repairs.sync
    hass.data[DOMAIN]["runtime"] = runtime
    async with runtime.updates.lock:
        await runtime.updates.refresh()
    await runtime.repairs.sync()
    await panel_custom.async_register_panel(
        hass, frontend_url_path=DOMAIN, webcomponent_name="enigmaha-panel",
        sidebar_title="EnigmaHA Companion", sidebar_icon="mdi:remote-tv",
        module_url="/enigmaha_companion/panel.js?v=" + VERSION,
        require_admin=True,
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = hass.data[DOMAIN].get("runtime")
    if runtime is not None:
        await runtime.updates.close()
        runtime.repairs.close()
        runtime.clear_editor_notifications()
        async with runtime.lock:
            runtime.active = False
            hass.data[DOMAIN].pop("runtime", None)
    frontend.async_remove_panel(hass, DOMAIN)
    return True
