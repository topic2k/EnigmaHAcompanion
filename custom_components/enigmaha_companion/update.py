"""Informational integration updates, independent of HACS installation."""

from datetime import timedelta
import logging

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
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
    """Show available releases; installation stays in the confirmed panel flow."""

    _attr_name = "EnigmaHA Companion"
    _attr_title = "EnigmaHA Companion"
    _attr_unique_id = DOMAIN + "_integration_update"
    _attr_supported_features = UpdateEntityFeature(0)

    @property
    def installed_version(self):
        # Downloaded files may already be newer while HA still needs a restart.
        return VERSION

    @property
    def latest_version(self):
        if self.coordinator.data is None:
            return None
        return self.coordinator.data["version"]

    @property
    def release_url(self):
        if self.latest_version is None:
            return None
        return REPOSITORY_URL + "/releases/tag/v" + self.latest_version
