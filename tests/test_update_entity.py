"""Release indicator behavior with narrow HA platform interfaces."""

import asyncio
from datetime import timedelta
from enum import IntFlag
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "dist/unpacked/homeassistant/custom_components/enigmaha_companion"


class Coordinator:
    def __init__(self, hass, logger, **kwargs):
        self.hass = hass
        self.options = kwargs
        self.data = None
        self.last_update_success = True


class Entity:
    def __init__(self, coordinator):
        self.coordinator = coordinator


package = types.ModuleType("eha_update_entity_test")
package.__path__ = [str(BUNDLE)]
spec = importlib.util.spec_from_file_location(package.__name__ + ".update", BUNDLE / "update.py")
UPDATE = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    package.__name__: package,
    "homeassistant.components.update": types.SimpleNamespace(
        UpdateEntity=type("UpdateEntity", (), {}), UpdateEntityFeature=IntFlag("UpdateEntityFeature", {"INSTALL": 1})),
    "homeassistant.helpers.update_coordinator": types.SimpleNamespace(
        DataUpdateCoordinator=Coordinator, CoordinatorEntity=Entity, UpdateFailed=type("UpdateFailed", (Exception,), {})),
}):
    spec.loader.exec_module(UPDATE)


def release(version="2.0.0"):
    return {"version": version, "ipk_url": UPDATE.REPOSITORY_URL + "/releases/download/v" + version + "/receiver.ipk",
            "ipk_sha256": "a" * 64, "ipk_size": 8}


class UpdateEntityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # No registry, services, HACS or receiver runtime is needed to check releases.
        self.hass = types.SimpleNamespace(async_add_executor_job=AsyncMock(
            side_effect=lambda func: func()))
        self.entry = object()
        self.coordinator = UPDATE.ReleaseCoordinator(self.hass, self.entry)
        self.entity = UPDATE.CompanionUpdateEntity(self.coordinator)

    async def test_checks_complete_stable_release_without_hacs_and_caches_properties(self):
        with patch.object(UPDATE, "fetch_latest_release", return_value=release()) as fetch:
            self.coordinator.data = await self.coordinator._async_update_data()
            for _ in range(3):
                self.assertEqual(self.entity.latest_version, "2.0.0")
                self.assertEqual(self.entity.release_url, UPDATE.REPOSITORY_URL + "/releases/tag/v2.0.0")
                self.assertEqual(self.entity.installed_version, UPDATE.VERSION)
            fetch.assert_called_once_with()
        self.assertEqual(self.coordinator.options["update_interval"], timedelta(hours=12))
        self.assertIs(self.coordinator.options["config_entry"], self.entry)
        self.assertFalse(self.coordinator.options["always_update"])

    async def test_failed_check_becomes_update_failed_and_subsequent_check_recovers(self):
        for code in ("release_check_failed", "invalid_release"):
            with self.subTest(code=code), patch.object(UPDATE, "fetch_latest_release", side_effect=UPDATE.UpdateError(code)):
                with self.assertRaises(UPDATE.UpdateFailed) as caught:
                    await self.coordinator._async_update_data()
                self.assertIn(code, str(caught.exception))
        with patch.object(UPDATE, "fetch_latest_release", return_value=release()):
            self.coordinator.data = await self.coordinator._async_update_data()
        self.assertEqual(self.entity.latest_version, "2.0.0")

    async def test_setup_adds_entity_even_when_initial_check_failed(self):
        self.coordinator.last_update_success = False
        self.coordinator.async_refresh = AsyncMock()
        add = Mock()
        with patch.object(UPDATE, "ReleaseCoordinator", return_value=self.coordinator):
            await UPDATE.async_setup_entry(self.hass, self.entry, add)
        self.coordinator.async_refresh.assert_awaited_once_with()
        entity = add.call_args.args[0][0]
        self.assertIs(entity.coordinator, self.coordinator)
        self.assertIsNone(entity.latest_version)
        self.assertIsNone(entity.release_url)
        self.assertEqual(entity.installed_version, UPDATE.VERSION)

    async def test_cancelled_release_check_is_not_converted_to_failure(self):
        self.hass.async_add_executor_job.side_effect = asyncio.CancelledError
        with self.assertRaises(asyncio.CancelledError):
            await self.coordinator._async_update_data()

    def test_downloaded_release_does_not_replace_running_version_or_offer_install(self):
        self.coordinator.data = release("99.0.0")
        self.assertEqual(self.entity.installed_version, UPDATE.VERSION)
        self.assertEqual(self.entity.latest_version, "99.0.0")
        self.assertEqual(self.entity._attr_supported_features, 0)
        self.assertIsInstance(self.entity._attr_supported_features, IntFlag)
        self.assertEqual(self.entity._attr_unique_id, UPDATE.DOMAIN + "_integration_update")
        self.assertEqual(self.entity._attr_name, "EnigmaHA Companion")

