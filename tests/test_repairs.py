"""Native wizard transitions against the real, persisted update coordinator."""

import asyncio
import copy
import importlib
import sys
import types
import unittest
from unittest.mock import patch

import test_updates as updates

API, UPDATES, Store = updates.API, updates.UPDATES, updates.Store


class NativeFlow:
    def async_show_form(self, **kwargs):
        return {"type": "form", **kwargs}

    def async_create_entry(self, **kwargs):
        return {"type": "create_entry", **kwargs}

    def async_abort(self, **kwargs):
        return {"type": "abort", **kwargs}

    def async_show_progress(self, **kwargs):
        return {"type": "progress", **kwargs}

    def async_show_progress_done(self, **kwargs):
        return {"type": "progress_done", **kwargs}


ISSUES = types.SimpleNamespace(
    IssueSeverity=types.SimpleNamespace(ERROR="error"),
    async_create_issue=lambda hass, domain, issue, **data: hass.issues.update({(domain, issue): data}),
    async_delete_issue=lambda hass, domain, issue: hass.issues.pop((domain, issue), None),
)
with patch.dict(sys.modules, {
    "homeassistant.helpers": types.SimpleNamespace(issue_registry=ISSUES),
    "homeassistant.exceptions": types.SimpleNamespace(HomeAssistantError=API.HomeAssistantError),
    "homeassistant.components.repairs": types.SimpleNamespace(RepairsFlow=NativeFlow),
    "probatio": types.SimpleNamespace(Schema=lambda value: value),
}):
    REPAIRS = importlib.import_module(API.__package__ + ".repairs")
    ISSUES_MODULE = importlib.import_module(API.__package__ + ".repair_issues")


class RepairTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await updates.CoordinatorTests.asyncSetUp(self)
        # The existing fixture imports isolated HA bundles under patch.dict;
        # bind their exception type as it would be shared in a real HA process.
        error_patch = patch.object(REPAIRS, "UpdateError", UPDATES.UpdateError)
        error_patch.start()
        self.addCleanup(error_patch.stop)
        issue_error_patch = patch.object(ISSUES_MODULE, "UpdateError", UPDATES.UpdateError)
        issue_error_patch.start()
        self.addCleanup(issue_error_patch.stop)
        self.hass.issues = {}
        self.runtime = types.SimpleNamespace(active=True, updates=self.manager)
        self.repair_store = Store()
        self.repairs = self.runtime.repairs = ISSUES_MODULE.RepairCoordinator(
            self.hass, self.repair_store, self.runtime)
        self.manager.on_change = self.repairs.sync
        self.hass.data = {API.DOMAIN: {"runtime": self.runtime}}
        self.peer = dict(self.receivers[0], protocol_version=2, status="protocol_mismatch")
        self.protocol_issue = (API.DOMAIN, ISSUES_MODULE.PROTOCOL_ISSUE)
        self.update_issue = (API.DOMAIN, ISSUES_MODULE.UPDATE_ISSUE)
        self.flows = []

    async def asyncTearDown(self):
        for flow in self.flows:
            if flow.poll_task:
                flow.poll_task.cancel()
                await asyncio.gather(flow.poll_task, return_exceptions=True)

    def flow(self):
        flow = REPAIRS.CompanionRepairFlow()
        flow.hass = self.hass
        self.flows.append(flow)
        return flow

    async def begin(self):
        await self.repairs.observe(self.peer)
        flow = self.flow()
        self.assertEqual((await flow.async_step_init())["step_id"], "confirm")
        self.assertEqual(self.calls, [])
        self.assertEqual((await flow.async_step_confirm({}))["type"], "progress")
        await self.manager.task
        return flow

    async def test_release_difference_creates_no_issue_or_update(self):
        await self.repairs.observe(dict(self.peer, version="9.0.0", protocol_version=1, status="version_mismatch"))
        self.assertEqual(self.hass.issues, {})
        self.assertIsNone(self.repair_store.data)
        self.assertIsNone(self.manager.job)
        self.assertEqual(self.calls, [])

    async def test_protocol_issue_survives_restart_and_other_user_cannot_clear_it(self):
        await self.repairs.observe(self.peer)
        issue = self.hass.issues[self.protocol_issue]
        self.assertTrue(issue["is_persistent"])
        self.assertTrue(issue["is_fixable"])
        restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                                                   copy.deepcopy(self.repair_store.data))
        await restored.sync()
        await restored.observe(dict(self.peer, user_id="other", protocol_version=1, status="compatible"))
        self.assertIn(self.protocol_issue, self.hass.issues)
        self.assertEqual(len(restored.receivers), 1)
        await restored.observe(dict(self.peer, protocol_version=1, status="version_mismatch"))
        self.assertNotIn(self.protocol_issue, self.hass.issues)

    async def test_confirm_uses_existing_hacs_job_and_cancelling_observer_does_not_cancel_install(self):
        flow = await self.begin()
        self.assertEqual(self.calls, [("update", "install", {"entity_id": "update.custom_name", "version": "v2.0.0"}, None)])
        self.assertEqual(self.repairs.job_id, self.manager.job["id"])
        flow.poll_task.cancel()
        await asyncio.gather(flow.poll_task, return_exceptions=True)
        self.assertFalse(self.manager.task.cancelled())
        self.assertIn(self.protocol_issue, self.hass.issues)

    async def test_decline_retry_restart_and_only_observed_completion_clears_issues(self):
        flow = await self.begin()
        job_id = self.manager.job["id"]
        await self.manager.report(self.peer["id"], self.peer["user_id"],
            {"job_id": job_id, "attempt": 1, "status": "declined", "error": None})
        self.assertEqual((await flow.async_step_resume())["step_id"], "retry")
        await flow.async_step_retry()
        self.assertEqual(self.manager.job["receivers"][0]["attempt"], 1)
        await flow.async_step_retry({})
        self.assertEqual(self.manager.job["receivers"][0]["attempt"], 2)
        self.assertEqual(self.manager.job["release"]["version"], "2.0.0")
        self.assertEqual(len(self.calls), 1)
        await self.manager.receiver_plan(self.peer["id"], self.peer["user_id"], "2.0.0", protocol=99)
        self.assertEqual(self.manager.job["receivers"][0]["status"], "pending")
        await self.repairs.observe(dict(self.peer, version="2.0.0", protocol_version=1, status="version_mismatch"))
        await self.manager.receiver_plan(self.peer["id"], self.peer["user_id"], "2.0.0", protocol=1)
        self.assertEqual((await flow.async_step_resume())["step_id"], "restart")
        self.assertIn(self.protocol_issue, self.hass.issues)
        self.assertIn(self.update_issue, self.hass.issues)
        self.assertEqual((await flow.async_step_restart({}))["reason"], "restart_requested")
        await self.manager.restart_task
        self.assertEqual(self.calls[-1][:2], ("homeassistant", "restart"))
        self.assertIn(self.update_issue, self.hass.issues)
        restored = UPDATES.UpdateManager(self.hass, self.store, copy.deepcopy(self.store.data))
        self.runtime.updates = restored
        restored_repairs = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                                                          copy.deepcopy(self.repair_store.data))
        self.runtime.repairs = restored_repairs
        restored.on_change = restored_repairs.sync
        with patch.object(UPDATES, "VERSION", "2.0.0"):
            self.assertEqual((await self.flow().async_step_init())["type"], "create_entry")
        self.assertEqual(self.hass.issues, {})

    async def test_uncertain_installation_offers_manual_check_without_retry(self):
        flow = await self.begin()
        await self.manager.report(self.peer["id"], self.peer["user_id"],
            {"job_id": self.manager.job["id"], "attempt": 1, "status": "failed", "error": "install_uncertain"})
        self.assertEqual((await flow.async_step_resume())["step_id"], "manual")
        self.assertEqual((await flow.async_step_manual({}))["step_id"], "manual")
        self.assertEqual(self.manager.job["receivers"][0]["attempt"], 1)
        self.assertEqual(len(self.calls), 1)

    async def test_expired_check_requires_fresh_confirmation(self):
        await self.repairs.observe(self.peer)
        flow = self.flow()
        await flow.async_step_init()
        original = flow.candidate["id"]
        self.manager.checked_at -= 601
        self.assertEqual((await flow.async_step_confirm({}))["step_id"], "confirm")
        self.assertNotEqual(flow.candidate["id"], original)
        self.assertEqual(self.calls, [])

    async def test_failed_repair_storage_does_not_mutate_history(self):
        self.repair_store.fail = True
        with self.assertRaises(UPDATES.UpdateError) as caught:
            await self.repairs.observe(self.peer)
        self.assertEqual(caught.exception.code, "update_storage_failed")
        self.assertEqual(self.repairs.receivers, [])
        self.assertEqual(self.hass.issues, {})

    async def test_new_ha_protocol_reconciles_persisted_receiver_observation(self):
        await self.repairs.observe(self.peer)
        with patch.object(ISSUES_MODULE, "PROTOCOL_VERSION", 2):
            await self.repairs.sync()
        self.assertEqual(self.repairs.receivers, [])
        self.assertEqual(self.hass.issues, {})

    async def test_protocol_changing_release_waits_for_new_protocol_on_both_sides(self):
        with patch.object(UPDATES, "downloaded_protocol_version", return_value=2):
            await self.manager.check()
            await self.manager.start(self.manager.candidate["id"], self.receivers, self.user)
            await self.manager.task
            await self.manager.receiver_plan(self.peer["id"], self.peer["user_id"], "2.0.0", protocol=1)
            self.assertEqual(self.manager.job["receivers"][0]["status"], "pending")
            await self.manager.receiver_plan(self.peer["id"], self.peer["user_id"], "2.0.0", protocol=2)
            with patch.object(UPDATES, "VERSION", "2.0.0"):
                self.assertEqual((await self.manager.snapshot())["job"]["phase"], "ha_restart_required")
                with patch.object(UPDATES, "PROTOCOL_VERSION", 2):
                    self.assertEqual((await self.manager.snapshot())["job"]["phase"], "completed")

    async def test_existing_failed_job_resumes_without_checking_another_release(self):
        await self.begin()
        job = copy.deepcopy(self.manager.job)
        job.update(phase="failed", error="hacs_install_failed")
        await self.manager.save(job)
        flow = self.flow()
        self.assertEqual((await flow.async_step_init())["step_id"], "retry")
        self.assertEqual(flow.job_id, job["id"])
        self.assertEqual(len(self.calls), 1)

    async def test_factory_only_accepts_our_issue_ids(self):
        for issue in (ISSUES_MODULE.PROTOCOL_ISSUE, ISSUES_MODULE.UPDATE_ISSUE):
            self.assertIsInstance(await REPAIRS.async_create_fix_flow(self.hass, issue, None), REPAIRS.CompanionRepairFlow)
        with self.assertRaises(ValueError):
            await REPAIRS.async_create_fix_flow(self.hass, "other", None)
