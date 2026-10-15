"""Release indicator behavior with narrow HA platform interfaces."""

import asyncio
from datetime import timedelta
from enum import IntFlag
import importlib.util
from pathlib import Path
import sys
from time import monotonic
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
        self.hass = coordinator.hass
        self._context = types.SimpleNamespace(user_id=None)
        self.async_write_ha_state = Mock()
        self.removers = []

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, remover):
        self.removers.append(remover)


class HomeAssistantError(Exception):
    def __init__(self, **kwargs):
        self.translation_key = kwargs["translation_key"]
        self.translation_placeholders = kwargs["translation_placeholders"]
        super().__init__(str(self.translation_placeholders))


package = types.ModuleType("eha_update_entity_test")
package.__path__ = [str(BUNDLE)]
spec = importlib.util.spec_from_file_location(package.__name__ + ".update", BUNDLE / "update.py")
UPDATE = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    package.__name__: package,
    "homeassistant.components.update": types.SimpleNamespace(
        UpdateEntity=type("UpdateEntity", (), {}),
        UpdateEntityFeature=IntFlag("UpdateEntityFeature", {"INSTALL": 1, "PROGRESS": 4})),
    "homeassistant.exceptions": types.SimpleNamespace(HomeAssistantError=HomeAssistantError),
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
        self.hass = types.SimpleNamespace(data={}, async_add_executor_job=AsyncMock(
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

    def test_downloaded_release_does_not_replace_running_version_and_offers_install(self):
        self.coordinator.data = release("99.0.0")
        self.assertEqual(self.entity.installed_version, UPDATE.VERSION)
        self.assertEqual(self.entity.latest_version, "99.0.0")
        self.assertEqual(self.entity._attr_supported_features,
                         UPDATE.UpdateEntityFeature.INSTALL | UPDATE.UpdateEntityFeature.PROGRESS)
        self.assertIsInstance(self.entity._attr_supported_features, IntFlag)
        self.assertEqual(self.entity._attr_unique_id, UPDATE.DOMAIN + "_integration_update")
        self.assertEqual(self.entity._attr_name, "EnigmaHA Companion")


import test_updates as updates


class CoordinatedInstallTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await updates.CoordinatorTests.asyncSetUp(self)
        error_patch = patch.object(UPDATE, "UpdateError", updates.UPDATES.UpdateError)
        error_patch.start()
        self.addCleanup(error_patch.stop)
        self.user.is_admin = self.user.is_active = True
        self.hass.auth = types.SimpleNamespace(async_get_user=AsyncMock(return_value=self.user))
        self.runtime = types.SimpleNamespace(active=True, updates=self.manager,
            receivers={r["id"]: dict(r, seen=monotonic()) for r in self.receivers})
        self.runtime.recent_receivers = lambda: updates.API.CompanionRuntime.recent_receivers(self.runtime)
        self.hass.data = {UPDATE.DOMAIN: {"runtime": self.runtime}}
        self.coordinator = UPDATE.ReleaseCoordinator(self.hass, object())
        self.coordinator.data = updates.release()
        self.coordinator.async_request_refresh = AsyncMock()
        self.entity = UPDATE.CompanionUpdateEntity(self.coordinator)
        self.entity._context = types.SimpleNamespace(user_id="admin")
        await self.entity.async_added_to_hass()

    async def install(self):
        await self.entity.async_install(None, False)

    async def test_native_install_updates_only_ha_and_keeps_restart_separate(self):
        await self.install()
        self.assertEqual(self.calls, [("update", "install", {
            "entity_id": "update.custom_name", "version": "v2.0.0"}, "admin")])
        self.assertEqual(self.manager.job["receivers"], [])
        self.assertEqual(self.manager.job["phase"], "ha_restart_required")
        self.assertFalse(self.entity.in_progress)
        self.entity.async_write_ha_state.assert_called()
        self.coordinator.data = updates.release("3.0.0")
        self.assertEqual(self.entity.latest_version, "2.0.0")
        self.assertTrue(self.entity.release_url.endswith("/v2.0.0"))
        self.assertEqual(await self.manager.receiver_plan("a" * 32, "receiver-user", "1.0.0"), {"job": None})
        self.assertEqual(len(self.calls), 1)
        with patch.object(updates.UPDATES, "VERSION", "2.0.0"):
            await self.manager.snapshot()
        self.assertEqual(self.manager.job["phase"], "completed")
        self.assertEqual(self.entity.latest_version, "3.0.0")

    async def test_ha_install_does_not_require_receivers(self):
        self.runtime.receivers = {}
        await self.install()
        self.assertEqual(self.manager.job["receivers"], [])
        self.assertEqual(self.manager.job["phase"], "ha_restart_required")

    async def test_old_offline_or_unidentified_receivers_never_join_ha_install(self):
        self.runtime.receivers["offline"] = dict(self.receivers[0], id="c" * 32, seen=monotonic() - 301)
        self.runtime.receivers["unidentified"] = dict(self.receivers[0], id=None, status="unidentified_peer")
        await self.install()
        self.assertEqual(self.manager.job["receivers"], [])
        self.assertEqual(len(self.calls), 1)

    async def test_missing_hacs_or_stale_hacs_version_blocks_install(self):
        self.state.attributes["installed_version"] = "v1.1.2"
        with self.assertRaises(HomeAssistantError) as caught:
            await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "hacs_version_changed")
        self.hass.registry.async_get = lambda entity: None
        with self.assertRaises(HomeAssistantError) as caught:
            await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "hacs_unavailable")
        self.assertEqual(self.calls, [])

    async def test_replaced_candidate_cannot_install_a_different_release(self):
        check = self.manager.check
        async def replaced():
            candidate = await check()
            await check()
            return candidate
        with patch.object(self.manager, "check", side_effect=replaced):
            with self.assertRaises(HomeAssistantError) as caught:
                await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "release_check_required")
        self.assertEqual(self.calls, [])

    async def test_newer_release_requires_review_and_never_installs_silently(self):
        with patch.object(updates.UPDATES, "fetch_latest_release", return_value=updates.release("3.0.0")):
            with self.assertRaises(HomeAssistantError) as caught:
                await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "release_check_required")
        self.coordinator.async_request_refresh.assert_awaited_once()
        self.assertEqual(self.calls, [])

    async def test_repeated_request_does_not_repeat_hacs_or_replace_participants(self):
        await self.install()
        job = self.manager.public_job()
        with self.assertRaises(HomeAssistantError) as caught:
            await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "update_in_progress")
        self.assertEqual(self.manager.public_job(), job)
        self.assertEqual(len(self.calls), 1)

    async def test_hacs_failure_is_reported_to_native_service_and_persisted(self):
        self.hass.services.async_call = AsyncMock(side_effect=updates.API.HomeAssistantError())
        with self.assertRaises(HomeAssistantError) as caught:
            await self.install()
        self.assertEqual(caught.exception.translation_placeholders["error"], "hacs_install_failed")
        self.assertEqual(self.store.data["phase"], "failed")
        self.assertFalse(self.entity.in_progress)

    async def test_non_admin_inactive_or_missing_user_cannot_install(self):
        with patch.object(self.manager, "check", new_callable=AsyncMock) as check:
            for user in (None, types.SimpleNamespace(is_admin=False, is_active=True),
                         types.SimpleNamespace(is_admin=True, is_active=False)):
                self.hass.auth.async_get_user.return_value = user
                with self.assertRaises(HomeAssistantError) as caught:
                    await self.install()
                self.assertEqual(caught.exception.translation_placeholders["error"], "admin_required")
            check.assert_not_awaited()
        self.assertEqual(self.calls, [])

    async def test_system_context_keeps_existing_automation_support(self):
        self.entity._context = types.SimpleNamespace(user_id=None)
        await self.install()
        self.assertIsNone(self.calls[0][3])
        self.hass.auth.async_get_user.assert_not_awaited()

    async def test_unsupported_options_or_unloaded_runtime_never_install(self):
        for version, backup in (("2.0.0", False), (None, True)):
            with self.assertRaises(HomeAssistantError):
                await self.entity.async_install(version, backup)
        self.runtime.active = False
        with self.assertRaises(HomeAssistantError):
            await self.install()
        self.assertEqual(self.calls, [])

    async def test_cancelled_service_does_not_cancel_durable_installation(self):
        began, finish = asyncio.Event(), asyncio.Event()
        call = self.hass.services.async_call
        async def delayed(*args, **kwargs):
            began.set()
            await finish.wait()
            await call(*args, **kwargs)
        self.hass.services.async_call = delayed
        service_task = asyncio.create_task(self.install())
        try:
            await asyncio.wait_for(began.wait(), 5)
        except TimeoutError:
            if service_task.done():
                service_task.result()
            service_task.cancel()
            raise
        service_task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await service_task
        self.assertFalse(self.manager.task.cancelled())
        finish.set()
        await self.manager.task
        self.assertEqual(self.manager.job["phase"], "ha_restart_required")
        self.assertEqual(len(self.calls), 1)

    async def test_entity_unload_removes_listener_and_keeps_repairs_callback(self):
        repair_sync = self.manager.on_change = AsyncMock()
        await self.install()
        repair_sync.assert_awaited()
        self.entity.async_write_ha_state.reset_mock()
        for remove in self.entity.removers:
            remove()
        await self.manager.save(self.manager.job)
        self.entity.async_write_ha_state.assert_not_called()

