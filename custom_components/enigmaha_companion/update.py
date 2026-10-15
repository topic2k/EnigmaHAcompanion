"""Release checks and coordinated HA/receiver installation from HA updates."""

import asyncio
import copy
from datetime import timedelta
import logging

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity, DataUpdateCoordinator, UpdateFailed,
)

from .const import DOMAIN, VERSION
from .enigmaha_protocol.releases import REPOSITORY_URL, UpdateError, fetch_latest_release

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = ReleaseCoordinator(hass, entry)
    # A failed public release check must not prevent local menu setup.
    await coordinator.async_refresh()
    async_add_entities([CompanionUpdateEntity(coordinator)])


class ReleaseCoordinator(DataUpdateCoordinator):
    """Cache the latest complete stable release for twelve hours."""

    def __init__(self, hass, entry):
        super().__init__(
            hass, _LOGGER, name=DOMAIN + " release", config_entry=entry,
            update_interval=timedelta(hours=12), always_update=False,
        )

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(fetch_latest_release)
        except UpdateError as error:
            raise UpdateFailed("Release check failed: " + error.code) from error


class CompanionUpdateEntity(CoordinatorEntity, UpdateEntity):
    """Install HA through HACS; receiver updates have their own repair flow."""

    _attr_name = "EnigmaHA Companion"
    _attr_title = "EnigmaHA Companion"
    _attr_unique_id = DOMAIN + "_integration_update"
    # Keep the published entity identity; HA attaches its existing registry entry.
    _attr_device_info = DeviceInfo(
        identifiers={(DOMAIN, DOMAIN)},
        name="EnigmaHA Companion",
        entry_type=DeviceEntryType.SERVICE,
        sw_version=VERSION,
    )
    _attr_supported_features = UpdateEntityFeature.INSTALL | UpdateEntityFeature.PROGRESS

    @property
    def runtime(self):
        return self.hass.data.get(DOMAIN, {}).get("runtime")

    @property
    def update_job(self):
        runtime = self.runtime
        return runtime.updates.job if runtime and runtime.updates else None

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        runtime = self.runtime
        if runtime and runtime.updates:
            self.async_on_remove(runtime.updates.add_listener(self.async_write_ha_state))

    @property
    def in_progress(self):
        job = self.update_job
        return bool(job and job["phase"] in {"ha_installing", "receivers"})

    async def async_install(self, version, backup, **kwargs):
        """Pin the displayed release and update only Home Assistant."""
        context = self._context
        offered_release = copy.deepcopy(self.coordinator.data)
        try:
            if version is not None or backup:
                raise UpdateError("invalid_update")
            runtime = self.runtime
            if runtime is None or not runtime.active or runtime.updates is None:
                raise UpdateError("update_unavailable")
            user = None
            if context.user_id is not None:
                user = await self.hass.auth.async_get_user(context.user_id)
                if user is None or not user.is_active or not user.is_admin:
                    raise UpdateError("admin_required")
            manager = runtime.updates
            # Check without installing. A newer release published after the user
            # opened the dialog must not silently replace the displayed target.
            candidate = await manager.check()
            if offered_release is None or candidate["release"] != offered_release:
                await self.coordinator.async_request_refresh()
                raise UpdateError("release_check_required")
            await manager.start(candidate["id"], [], user)
            # Installation belongs to UpdateManager and survives a cancelled
            # service call. HA restart still requires a separate confirmation.
            await asyncio.shield(manager.task)
            if manager.job["phase"] == "failed":
                raise UpdateError(manager.job["error"] or "hacs_install_failed")
        except UpdateError as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="update_install_failed",
                translation_placeholders={"error": error.code},
            ) from error

    @property
    def installed_version(self):
        # Downloaded files may already be newer while HA still needs a restart.
        return VERSION

    @property
    def latest_version(self):
        job = self.update_job
        if job and job["phase"] not in {"completed", "failed", "cancelled"}:
            return job["release"]["version"]
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["version"]

    @property
    def release_url(self):
        if self.latest_version is None:
            return None
        return REPOSITORY_URL + "/releases/tag/v" + self.latest_version
