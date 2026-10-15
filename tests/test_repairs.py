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
    def async_show_menu(self, **kwargs):
        return {"type": "menu", **kwargs}

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
    IssueSeverity=types.SimpleNamespace(ERROR="error", WARNING="warning"),
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
        # Keep coverage of the published recovery path for a receiver newer
        # than HA. Old receivers get the separate, receiver-only path below.
        self.peer = dict(self.receivers[0], version="1.9.0", protocol_version=2, status="protocol_mismatch")
        self.protocol_issue = (API.DOMAIN, ISSUES_MODULE.PROTOCOL_ISSUE)
        self.update_issue = (API.DOMAIN, ISSUES_MODULE.UPDATE_ISSUE)
        self.receiver_issue = (API.DOMAIN, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE)
        self.flows = []
        release_patch = patch.object(UPDATES, "fetch_release", return_value=updates.release(UPDATES.VERSION))
        release_patch.start()
        self.addCleanup(release_patch.stop)

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
        for issue in (ISSUES_MODULE.PROTOCOL_ISSUE, ISSUES_MODULE.UPDATE_ISSUE, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE):
            self.assertIsInstance(await REPAIRS.async_create_fix_flow(self.hass, issue, None), REPAIRS.CompanionRepairFlow)
        with self.assertRaises(ValueError):
            await REPAIRS.async_create_fix_flow(self.hass, "other", None)

    async def test_old_compatible_receiver_offers_optional_persistent_repair(self):
        peer = dict(self.peer, version="1.0.0", protocol_version=1, status="version_mismatch")
        await self.repairs.observe(peer)
        issue = self.hass.issues[self.receiver_issue]
        self.assertEqual(issue["severity"], "warning")
        self.assertTrue(issue["is_fixable"])
        self.assertTrue(issue["is_persistent"])
        self.assertNotIn(self.protocol_issue, self.hass.issues)
        self.assertEqual(self.calls, [])
        restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                                                   copy.deepcopy(self.repair_store.data))
        await restored.sync()
        self.assertEqual(restored.receivers[0]["status"], "version_mismatch")
        await restored.observe(dict(peer, user_id="other-user", version=UPDATES.VERSION, status="compatible"))
        self.assertIn(self.receiver_issue, self.hass.issues)
        await restored.observe(dict(peer, version=UPDATES.VERSION, status="compatible"))
        self.assertNotIn(self.receiver_issue, self.hass.issues)

    async def test_receiver_request_creates_the_matching_issue_without_starting_install(self):
        runtime = API.CompanionRuntime(self.hass, Store(), {})
        runtime.repairs = self.repairs
        for protocol, expected_status, issue in (("1", "version_mismatch", self.receiver_issue),
                                                 ("2", "protocol_mismatch", self.protocol_issue)):
            request = types.SimpleNamespace(remote="192.0.2.1", headers={
                API.COMPONENT_HEADER: "receiver", API.VERSION_HEADER: "1.0.0",
                API.PROTOCOL_HEADER: protocol, API.RECEIVER_HEADER: "a" * 32})
            self.assertEqual(await runtime.check_receiver(request, types.SimpleNamespace(id="receiver-user")), expected_status)
            self.assertIn(issue, self.hass.issues)
            self.assertIsNone(self.manager.job)
        self.assertNotIn(self.receiver_issue, self.hass.issues)
        self.assertEqual(self.calls, [])

    async def test_old_receivers_repair_only_receiver_without_hacs_or_ha_restart(self):
        for status, protocol, issue_id in (("version_mismatch", 1, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE),
                                          ("protocol_mismatch", 2, ISSUES_MODULE.PROTOCOL_ISSUE)):
            with self.subTest(status=status):
                peer = dict(self.peer, version="1.0.0", protocol_version=protocol, status=status)
                await self.repairs.observe(peer)
                self.hass.registry.async_get = lambda entity: None
                flow = await REPAIRS.async_create_fix_flow(self.hass, issue_id, None)
                flow.hass = self.hass
                self.flows.append(flow)
                form = await flow.async_step_init()
                self.assertEqual(form["step_id"], "confirm_receivers")
                self.assertEqual(form["description_placeholders"]["version"], UPDATES.VERSION)
                self.assertIsNone(self.manager.job)
                result = await flow.async_step_confirm_receivers({})
                self.assertEqual(result["type"], "progress")
                self.assertIsNone(self.manager.job["entity_id"])
                self.assertEqual(self.manager.job["phase"], "receivers")
                self.assertEqual(self.calls, [])
                plan = await self.manager.receiver_plan(peer["id"], peer["user_id"], "1.0.0", protocol)
                self.assertEqual(plan["job"]["release"]["version"], UPDATES.VERSION)
                self.assertEqual(await self.manager.receiver_plan(peer["id"], "other", UPDATES.VERSION), {"job": None})
                # Receiver confirmation is still required; only observing the
                # running target release/protocol completes the installation.
                await self.repairs.observe(dict(peer, version=UPDATES.VERSION, protocol_version=1, status="compatible"))
                await self.manager.receiver_plan(peer["id"], peer["user_id"], UPDATES.VERSION, 1)
                self.assertEqual(self.manager.job["phase"], "completed")
                self.assertEqual(self.calls, [])
                self.assertNotIn(self.protocol_issue, self.hass.issues)
                self.assertNotIn(self.receiver_issue, self.hass.issues)
                # Start the next independent case with the same stored format.
                self.manager.job = None

    async def test_receiver_repair_refuses_pending_ha_files_and_keeps_offer(self):
        peer = dict(self.peer, version="1.0.0", protocol_version=1, status="version_mismatch")
        await self.repairs.observe(peer)
        flow = await REPAIRS.async_create_fix_flow(self.hass, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE, None)
        flow.hass = self.hass
        await flow.async_step_init()
        self.disk_version = "9.0.0"
        result = await flow.async_step_confirm_receivers({})
        self.assertEqual(result["errors"]["base"], "hacs_version_changed")
        self.assertIsNone(self.manager.job)
        self.assertIn(self.receiver_issue, self.hass.issues)
        self.assertEqual(self.calls, [])

    async def test_missing_installed_files_yield_repair_error_without_installation(self):
        peer = dict(self.peer, version="1.0.0", protocol_version=1, status="version_mismatch")
        await self.repairs.observe(peer)
        flow = await REPAIRS.async_create_fix_flow(self.hass, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE, None)
        flow.hass = self.hass
        await flow.async_step_init()
        with patch.object(UPDATES, "downloaded_version", side_effect=OSError("missing manifest")):
            result = await flow.async_step_confirm_receivers({})
        self.assertEqual(result["errors"]["base"], "hacs_version_changed")
        self.assertIsNone(self.manager.job)
        self.assertEqual(self.calls, [])

    async def test_existing_stored_protocol_record_needs_no_migration(self):
        await self.repairs.observe(self.peer)
        saved = copy.deepcopy(self.repair_store.data)
        saved.pop("job_issue")
        restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime, saved)
        self.assertEqual(restored.job_issue, ISSUES_MODULE.PROTOCOL_ISSUE)
        self.assertEqual(restored.receivers, self.repairs.receivers)

    async def test_protocol_reconciles_to_optional_offer_when_ha_becomes_compatible(self):
        await self.repairs.observe(dict(self.peer, version="1.0.0"))
        with patch.object(ISSUES_MODULE, "PROTOCOL_VERSION", 2):
            await self.repairs.sync()
        self.assertNotIn(self.protocol_issue, self.hass.issues)
        self.assertIn(self.receiver_issue, self.hass.issues)

    async def optional_flow(self):
        peer = dict(self.peer, version="1.0.0", protocol_version=1, status="version_mismatch")
        await self.repairs.observe(peer)
        flow = await REPAIRS.async_create_fix_flow(self.hass, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE, None)
        flow.hass = self.hass
        self.flows.append(flow)
        return peer, flow

    async def test_ignore_needs_no_release_download_and_survives_restart_and_reconnect(self):
        peer, flow = await self.optional_flow()
        with patch.object(UPDATES, "fetch_release", side_effect=AssertionError("No download when ignoring")):
            menu = await flow.async_step_init()
            self.assertEqual(menu["type"], "menu")
            self.assertEqual(menu["menu_options"], ["install_receivers", "ignore"])
            self.assertEqual((await flow.async_step_ignore())["type"], "create_entry")
        self.assertNotIn(self.receiver_issue, self.hass.issues)
        self.assertIsNone(self.manager.job)
        self.assertEqual(self.calls, [])
        restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                                                   copy.deepcopy(self.repair_store.data))
        await restored.sync()
        await restored.observe(peer)
        self.assertNotIn(self.receiver_issue, self.hass.issues)
        self.assertEqual(restored.receivers, [peer])

    async def test_ignore_is_scoped_to_target_receiver_version_identity_and_user(self):
        peer, flow = await self.optional_flow()
        await flow.async_step_init()
        await flow.async_step_ignore()
        for change in ({"version": "0.9.0"}, {"id": "f" * 32}, {"user_id": "other-user"}):
            with self.subTest(change=change):
                restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                                                           copy.deepcopy(self.repair_store.data))
                await restored.observe(dict(peer, **change))
                self.assertIn(self.receiver_issue, self.hass.issues)
        future = list(UPDATES.version_tuple(UPDATES.VERSION))
        future[2] += 1
        with patch.object(ISSUES_MODULE, "VERSION", ".".join(map(str, future))):
            await self.repairs.sync()
            self.assertIn(self.receiver_issue, self.hass.issues)
        with patch.object(ISSUES_MODULE, "PROTOCOL_VERSION", 2):
            await self.repairs.sync()
            self.assertIn(self.protocol_issue, self.hass.issues)

    async def test_ignore_pending_or_declined_job_withdraws_it_without_claiming_installation(self):
        for status in ("pending", "declined", "failed"):
            with self.subTest(status=status):
                peer, flow = await self.optional_flow()
                await flow.async_step_init()
                await flow.async_step_install_receivers()
                job_id = self.manager.job["id"]
                if status != "pending":
                    await self.manager.report(peer["id"], peer["user_id"],
                        {"job_id": job_id, "attempt": 1, "status": status, "error": None})
                reopened = await REPAIRS.async_create_fix_flow(self.hass, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE, None)
                reopened.hass = self.hass
                self.flows.append(reopened)
                menu = await reopened.async_step_init()
                self.assertEqual(menu["step_id"], "optional_update")
                self.assertIn("ignore", menu["menu_options"])
                self.assertEqual((await reopened.async_step_ignore())["type"], "create_entry")
                self.assertEqual(self.manager.job["phase"], "cancelled")
                self.assertEqual(self.manager.job["receivers"][0]["status"], status)
                self.assertEqual(await self.manager.receiver_plan(peer["id"], peer["user_id"], peer["version"], 1), {"job": None})
                with self.assertRaises(UPDATES.UpdateError):
                    await self.manager.retry(job_id, None)
                with self.assertRaises(UPDATES.UpdateError):
                    await self.manager.report(peer["id"], peer["user_id"],
                        {"job_id": job_id, "attempt": 1, "status": "installing", "error": None})
                self.assertEqual(self.hass.issues, {})
                self.assertEqual(self.calls, [])
                restored = UPDATES.UpdateManager(self.hass, self.store, copy.deepcopy(self.store.data))
                self.assertEqual(await restored.receiver_plan(peer["id"], peer["user_id"], peer["version"], 1), {"job": None})
                await self.manager.check()
                await self.manager.start(self.manager.candidate["id"], [], None)
                await self.manager.task
                self.assertEqual(self.manager.job["phase"], "ha_restart_required")
                # Reset the independent scenario, retaining no ignored markers.
                self.manager.job = None
                self.repairs.ignored = []
                self.disk_version = UPDATES.VERSION
                self.state.attributes["installed_version"] = "v" + UPDATES.VERSION
                self.calls.clear()

    async def test_ignore_multiple_receivers_does_not_hide_new_arrivals_or_ha_work(self):
        peer, flow = await self.optional_flow()
        second = dict(peer, id="e" * 32, address="192.0.2.2")
        await self.repairs.observe(second)
        await flow.async_step_init()
        await flow.async_step_install_receivers()
        await self.repairs.observe(dict(peer, id="f" * 32, address="192.0.2.3"))
        result = await flow.async_step_ignore()
        self.assertEqual(self.manager.job["phase"], "cancelled")
        self.assertEqual(result["type"], "menu")
        self.assertEqual(result["description_placeholders"]["receivers"], "192.0.2.3")
        self.assertIn(self.receiver_issue, self.hass.issues)
        self.assertEqual(len(self.repairs.ignored), 2)
        await self.manager.check()
        await self.manager.start(self.manager.candidate["id"], [], self.user)
        result = await flow.async_step_ignore()
        self.assertEqual(result["errors"]["base"], "ignore_unavailable")
        await self.manager.task

    async def test_ignore_never_hides_changed_protocol_or_cancels_claimed_installation(self):
        peer, flow = await self.optional_flow()
        await flow.async_step_init()
        await flow.async_step_install_receivers()
        job_id = self.manager.job["id"]
        for status, error in (("installing", None), ("restart_required", None), ("failed", "install_uncertain")):
            with self.subTest(status=status):
                job = copy.deepcopy(self.manager.job)
                job["receivers"][0].update(status=status, error=error)
                await self.manager.save(job)
                result = await flow.async_step_ignore()
                self.assertEqual(result["errors"]["base"], "ignore_unavailable")
                self.assertEqual(self.manager.job["id"], job_id)
                self.assertEqual(self.manager.job["phase"], "receivers")
                self.assertEqual(self.repairs.ignored, [])
                self.assertIn(self.receiver_issue, self.hass.issues)
        job["receivers"][0].update(status="pending", error=None)
        await self.manager.save(job)
        await self.repairs.observe(dict(peer, protocol_version=2, status="protocol_mismatch"))
        result = await flow.async_step_ignore()
        self.assertEqual(result["errors"]["base"], "ignore_unavailable")
        self.assertIn(self.protocol_issue, self.hass.issues)
        self.assertEqual(self.repairs.ignored, [])
        critical = self.flow()
        self.assertEqual((await critical.async_step_ignore())["type"], "abort")

    async def test_ignore_storage_failures_leave_issue_retryable_without_installing(self):
        peer, flow = await self.optional_flow()
        await flow.async_step_init()
        await flow.async_step_install_receivers()
        self.repair_store.fail = True
        result = await flow.async_step_ignore()
        self.assertEqual(result["errors"]["base"], "update_storage_failed")
        self.assertEqual(self.manager.job["phase"], "receivers")
        self.assertEqual(self.repairs.ignored, [])
        self.repair_store.fail = False
        self.store.fail = True
        result = await flow.async_step_ignore()
        self.assertEqual(result["errors"]["base"], "update_storage_failed")
        self.assertEqual(self.manager.job["phase"], "receivers")
        self.assertIn(self.receiver_issue, self.hass.issues)
        self.store.fail = False
        # Resume after both stores and the integration have been reloaded.
        self.runtime.repairs = self.repairs = ISSUES_MODULE.RepairCoordinator(
            self.hass, self.repair_store, self.runtime, copy.deepcopy(self.repair_store.data))
        self.manager.on_change = self.repairs.sync
        reopened = await REPAIRS.async_create_fix_flow(self.hass, ISSUES_MODULE.RECEIVER_UPDATE_ISSUE, None)
        reopened.hass = self.hass
        self.flows.append(reopened)
        self.assertEqual((await reopened.async_step_init())["step_id"], "optional_update")
        self.assertEqual((await reopened.async_step_ignore())["type"], "create_entry")
        self.assertEqual(self.manager.job["phase"], "cancelled")
        self.assertEqual(self.hass.issues, {})

    async def test_ignored_records_default_for_published_storage_and_reject_corruption(self):
        peer, flow = await self.optional_flow()
        saved = copy.deepcopy(self.repair_store.data)
        saved.pop("ignored_receiver_updates")
        restored = ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime, saved)
        self.assertEqual(restored.ignored, [])
        for bad in (None, {}, [dict(peer, target_version="bad")]):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                ISSUES_MODULE.RepairCoordinator(self.hass, self.repair_store, self.runtime,
                    dict(saved, ignored_receiver_updates=bad))
