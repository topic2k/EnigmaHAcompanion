"""Release verification, HACS coordination and OpenATV package transaction tests."""

import asyncio
import copy
from enum import IntFlag
import hashlib
import importlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]
from enigmaha_protocol import releases
from enigmaha_protocol.releases import UpdateError
from companion import updater
from companion.client import ClientError
from companion.client import CompanionClient
from enigmaha_protocol.compatibility import COMPONENT_HEADER, VERSION_HEADER, RECEIVER_HEADER, PROTOCOL_HEADER, PROTOCOL_VERSION
import test_ha_plugin as ha_tests

API, Store = ha_tests.API, ha_tests.Store

# load_api() already supplies the HA interfaces used by the packaged module.
with patch.dict(sys.modules, {"homeassistant.core": types.SimpleNamespace(Context=API.Context),
                             "homeassistant.exceptions": types.SimpleNamespace(HomeAssistantError=API.HomeAssistantError),
                             "homeassistant.helpers": types.SimpleNamespace(entity_registry=types.SimpleNamespace(async_get=lambda hass: hass.registry))}):
    UPDATES = importlib.import_module(API.__package__ + ".updates")


def release(version="2.0.0", data=b"test ipk"):
    return {"version": version, "ipk_url": releases.asset_url(version, releases.ipk_name(version)),
            "ipk_sha256": hashlib.sha256(data).hexdigest(), "ipk_size": len(data)}


def plan(status="pending", attempt=1):
    return {"id": "b" * 32, "release": release(), "status": status, "attempt": attempt}


class ReleaseTests(unittest.TestCase):
    def metadata(self):
        version = "2.0.0"
        return {"tag_name": "v" + version, "draft": False, "prerelease": False,
                "assets": [{"name": name, "size": 8, "browser_download_url": releases.asset_url(version, name)}
                           for name in (releases.ipk_name(version), "enigmaha_companion.zip", "SHA256SUMS.txt")]}

    def sums(self):
        return "a" * 64 + "  " + releases.ipk_name("2.0.0") + "\n" + "b" * 64 + "  enigmaha_companion.zip\n"

    def test_complete_stable_release_is_pinned_to_exact_assets(self):
        value = releases.release_with_checksums(self.metadata(), self.sums())
        self.assertEqual(value["version"], "2.0.0")
        self.assertEqual(value["ipk_sha256"], "a" * 64)
        self.assertEqual(value["ipk_url"], releases.asset_url("2.0.0", releases.ipk_name("2.0.0")))

    def test_rejects_unpublished_prerelease_wrong_asset_and_ambiguous_checksums(self):
        for change in ({"draft": True}, {"prerelease": True}, {"tag_name": "main"}, {"tag_name": "v2.0.0;reboot"}):
            with self.subTest(change=change), self.assertRaises(UpdateError):
                releases.release_with_checksums(dict(self.metadata(), **change), self.sums())
        for mode in ("missing", "external", "duplicate", "oversized"):
            metadata = self.metadata()
            if mode == "missing":
                metadata["assets"].pop()
            elif mode == "external":
                metadata["assets"][0]["browser_download_url"] = "https://evil.example/payload.ipk"
            elif mode == "duplicate":
                metadata["assets"].append(metadata["assets"][0])
            else:
                metadata["assets"][0]["size"] = releases.MAX_IPK_BYTES + 1
            with self.subTest(mode=mode), self.assertRaises(UpdateError):
                releases.release_with_checksums(metadata, self.sums())
        for sums in ("", self.sums() + self.sums(), self.sums() + "invalid\n"):
            with self.assertRaises(UpdateError):
                releases.release_with_checksums(self.metadata(), sums)

    def test_public_download_does_not_allow_plaintext_or_arbitrary_redirect_hosts(self):
        for url in ("http://github.com/file", "https://evil.example/file", "https://token@github.com/file"):
            with self.assertRaises(UpdateError):
                releases.open_public(url)
        opener = Mock()
        with patch.object(releases, "build_opener", return_value=opener):
            releases.open_public(release()["ipk_url"])
        request = opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))


class ReceiverUpdateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.updater = updater.ReceiverUpdater(str(Path(self.directory.name) / "journal.json"))
        self.job = plan()
        self.client = types.SimpleNamespace(report_update=Mock())
        self.commands = []
        def run(command, **kwargs):
            self.commands.append(command)
            self.assertFalse(kwargs.get("shell", False))
            if command[1] == "info":
                return types.SimpleNamespace(returncode=0, stdout="Package: " + releases.PACKAGE + "\nVersion: 2.0.0\nArchitecture: all\n")
            if command[1] == "status":
                return types.SimpleNamespace(returncode=0, stdout="Package: " + releases.PACKAGE + "\nVersion: 2.0.0\nStatus: install ok installed\n")
            return types.SimpleNamespace(returncode=0)
        patches = [patch.object(updater.os, "geteuid", return_value=0, create=True),
                   patch.object(updater, "open_public", side_effect=lambda url: io.BytesIO(b"test ipk")),
                   patch.object(updater.subprocess, "run", side_effect=run)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_identity_is_persistent_and_invalid_data_is_not_replaced(self):
        path = str(Path(self.directory.name) / "id")
        identity = updater.load_receiver_id(path)
        self.assertEqual(identity, updater.load_receiver_id(path))
        self.assertEqual(len(identity), 32)
        Path(path).write_text("bad identity")
        with self.assertRaises(ValueError):
            updater.load_receiver_id(path)
        self.assertEqual(Path(path).read_text(), "bad identity")

    def test_installation_requires_durable_local_confirmation(self):
        with self.assertRaises(UpdateError):
            self.updater.perform(self.job, self.client)
        self.assertEqual(self.commands, [])

    def test_verified_ipk_installs_once_and_recovers_lost_report(self):
        self.updater.confirm(self.job)
        self.updater.perform(self.job, self.client)
        self.assertEqual([command[1] for command in self.commands], ["info", "install", "status"])
        self.assertEqual(self.updater.journal()["status"], "restart_required")
        self.updater.perform(self.job, self.client)
        self.assertEqual(sum(command[1] == "install" for command in self.commands), 1)
        self.assertEqual(self.client.report_update.call_args.args[1], "restart_required")

    def test_bad_checksum_and_wrong_package_never_reach_install(self):
        self.updater.confirm(self.job)
        with patch.object(updater, "open_public", return_value=io.BytesIO(b"tampered")):
            with self.assertRaises(UpdateError) as caught:
                self.updater.perform(self.job, self.client)
        self.assertEqual(caught.exception.code, "checksum_failed")
        self.assertEqual(self.commands, [])
        self.job["attempt"] += 1
        self.updater.confirm(self.job)
        with patch.object(updater.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout="Package: wrong\nVersion: 2.0.0\nArchitecture: all\n")) as run:
            with self.assertRaises(UpdateError) as caught:
                self.updater.perform(self.job, self.client)
        self.assertEqual(caught.exception.code, "invalid_package")
        self.assertEqual(len(run.call_args_list), 1)

    def test_lost_claim_is_resumable_but_opkg_timeout_is_not_replayed(self):
        self.updater.confirm(self.job)
        self.client.report_update.side_effect = ClientError("connection_failed")
        with self.assertRaises(ClientError):
            self.updater.perform(self.job, self.client)
        self.assertEqual(self.updater.journal()["status"], "confirmed")
        self.assertEqual(self.commands, [])
        self.client.report_update.side_effect = None
        original = updater.subprocess.run
        def timed_out(command, **kwargs):
            if command[1] == "install":
                raise subprocess.TimeoutExpired(command, 300)
            return original(command, **kwargs)
        with patch.object(updater.subprocess, "run", side_effect=timed_out):
            with self.assertRaises(UpdateError) as caught:
                self.updater.perform(self.job, self.client)
        self.assertEqual(caught.exception.code, "install_uncertain")
        self.assertEqual(self.updater.journal()["status"], "uncertain")
        with patch.object(self.updater, "installed", return_value=False):
            with self.assertRaises(UpdateError):
                self.updater.perform(self.job, self.client)
        self.assertFalse(any(command[1] == "install" for command in self.commands))

    def test_lost_success_report_uses_installed_package_and_never_reinstalls(self):
        self.updater.confirm(self.job)
        def report(job, status, error=None):
            if status == "restart_required":
                raise ClientError("connection_failed")
        self.client.report_update.side_effect = report
        with self.assertRaises(ClientError):
            self.updater.perform(self.job, self.client)
        self.assertEqual(self.updater.journal()["status"], "restart_required")
        self.client.report_update.side_effect = None
        self.updater.perform(self.job, self.client)
        self.assertEqual(sum(command[1] == "install" for command in self.commands), 1)

    def test_storage_failure_before_opkg_cannot_install(self):
        self.updater.confirm(self.job)
        with patch.object(updater, "atomic_write", side_effect=OSError("disk full")):
            with self.assertRaises(UpdateError):
                self.updater.perform(self.job, self.client)
        self.assertFalse(any(command[1] == "install" for command in self.commands))

    def test_storage_failure_after_opkg_is_reported_as_uncertain_and_never_reinstalled(self):
        self.updater.confirm(self.job)
        save = self.updater.save
        def fail_after_install(job, status):
            if status == "restart_required":
                raise UpdateError("update_storage_failed")
            return save(job, status)
        with patch.object(self.updater, "save", side_effect=fail_after_install):
            with self.assertRaises(UpdateError):
                self.updater.perform(self.job, self.client)
        self.assertEqual(self.client.report_update.call_args.args[1:], ("failed", "install_uncertain"))
        self.assertEqual(self.updater.journal()["status"], "installing")
        self.updater.perform(self.job, self.client)
        self.assertEqual(sum(command[1] == "install" for command in self.commands), 1)

    def test_corrupt_journal_fails_closed_without_replacing_it(self):
        for value in ({"id": "a" * 32, "status": []},
                      {"id": "a" * 32, "status": "confirmed", "attempt": True, "version": "2.0.0"},
                      {"id": "a" * 32, "status": "confirmed", "attempt": 1, "version": "invalid"}):
            content = json.dumps(value)
            Path(self.updater.path).write_text(content)
            with self.assertRaises(UpdateError) as caught:
                self.updater.confirm(self.job)
            self.assertEqual(caught.exception.code, "update_storage_failed")
            self.assertEqual(Path(self.updater.path).read_text(), content)
        self.assertEqual(self.commands, [])


class CoordinatorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.disk_version = UPDATES.VERSION
        self.state = types.SimpleNamespace(entity_id="update.custom_name", state="on", attributes={
            "release_url": releases.REPOSITORY_URL + "/releases/v2.0.0", "installed_version": "v" + UPDATES.VERSION, "supported_features": 23})
        self.calls = []
        async def call(domain, service, data, blocking, context):
            self.calls.append((domain, service, data, context.user_id))
            if domain == "update":
                self.disk_version = data["version"].removeprefix("v")
                self.state.attributes["installed_version"] = data["version"]
        self.hass = types.SimpleNamespace(registry=types.SimpleNamespace(async_get=lambda entity: types.SimpleNamespace(platform="hacs")),
            states=types.SimpleNamespace(async_all=lambda: [self.state]), services=types.SimpleNamespace(async_call=call),
            async_add_executor_job=lambda func, *args: asyncio.to_thread(func, *args), async_create_task=asyncio.create_task)
        self.store = Store()
        self.manager = UPDATES.UpdateManager(self.hass, self.store)
        self.addAsyncCleanup(self.manager.close)
        self.user = types.SimpleNamespace(id="admin")
        self.receivers = [{"id": "a" * 32, "user_id": "receiver-user", "address": "192.0.2.1", "version": "1.0.0", "status": "compatible"}]
        for item in (patch.object(UPDATES, "downloaded_version", side_effect=lambda: self.disk_version),
                     patch.object(UPDATES, "fetch_latest_release", return_value=release())):
            item.start()
            self.addCleanup(item.stop)

    async def start(self):
        await self.manager.check()
        candidate_id = self.manager.candidate["id"]
        await self.manager.start(candidate_id, self.receivers, self.user)
        await self.manager.task
        return candidate_id

    def report(self, status, error=None):
        return self.manager.report("a" * 32, "receiver-user", {"job_id": self.manager.job["id"], "attempt": 1,
                                   "status": status, "error": error})

    async def test_exact_release_hacs_install_receiver_restart_ha_restart_and_verified_completion(self):
        candidate_id = await self.start()
        self.assertEqual(self.calls[0], ("update", "install", {"entity_id": "update.custom_name", "version": "v2.0.0"}, "admin"))
        await self.manager.start(candidate_id, self.receivers, self.user)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual((await self.manager.receiver_plan("a" * 32, "other-user", "1.0.0")), {"job": None})
        job = (await self.manager.receiver_plan("a" * 32, "receiver-user", "1.0.0"))["job"]
        self.assertEqual(job["release"], release())
        await self.report("installing")
        await self.report("restart_required")
        self.assertEqual((await self.manager.snapshot())["job"]["phase"], "receivers")
        with self.assertRaises(UPDATES.UpdateError):
            await self.manager.restart(self.manager.job["id"], self.user)
        await self.manager.receiver_plan("a" * 32, "receiver-user", "2.0.0")
        self.assertEqual((await self.manager.snapshot())["job"]["phase"], "ha_restart_required")
        await self.manager.restart(self.manager.job["id"], self.user)
        await asyncio.sleep(0)
        self.assertEqual(self.calls[-1][:2], ("homeassistant", "restart"))
        restored = UPDATES.UpdateManager(self.hass, self.store, copy.deepcopy(self.store.data))
        with patch.object(UPDATES, "VERSION", "2.0.0"):
            self.assertEqual((await restored.snapshot())["job"]["phase"], "completed")
        self.assertNotIn("user_id", restored.public_job()["receivers"][0])

    async def test_decline_retry_and_stale_reports_do_not_change_target(self):
        await self.start()
        await self.report("declined")
        self.assertEqual((await self.manager.receiver_plan("a" * 32, "receiver-user", "1.0.0"))["job"]["status"], "declined")
        await self.manager.retry(self.manager.job["id"], self.user)
        self.assertEqual(self.manager.job["receivers"][0]["attempt"], 2)
        with self.assertRaises(UPDATES.UpdateError):
            await self.report("installing")
        self.assertEqual(self.manager.job["release"]["version"], "2.0.0")

    async def test_cannot_start_without_hacs_receivers_or_with_a_downgrade(self):
        await self.manager.check()
        candidate = self.manager.candidate["id"]
        for receivers in ([dict(self.receivers[0], id=None)], [dict(self.receivers[0], version="3.0.0")]):
            with self.assertRaises(UPDATES.UpdateError):
                await self.manager.start(candidate, receivers, self.user)
        self.state.attributes["release_url"] = "https://github.com/other/repo/releases/v2.0.0"
        with self.assertRaises(UPDATES.UpdateError):
            await self.manager.check()
        self.assertEqual(self.calls, [])

    async def test_restart_or_reload_recovers_files_without_replaying_hacs(self):
        await self.start()
        saved = copy.deepcopy(self.store.data)
        saved["phase"] = "ha_installing"
        restored = UPDATES.UpdateManager(self.hass, self.store, saved)
        self.assertEqual((await restored.snapshot())["job"]["phase"], "receivers")
        self.assertEqual(len(self.calls), 1)
        self.disk_version = "1.0.0"
        restored = UPDATES.UpdateManager(self.hass, self.store, saved)
        self.assertEqual((await restored.snapshot())["job"]["phase"], "failed")
        self.assertEqual(len(self.calls), 1)

    async def test_storage_failure_prevents_install_and_unconfirmed_completion_is_rejected(self):
        await self.manager.check()
        self.store.fail = True
        with self.assertRaises(UPDATES.UpdateError):
            await self.manager.start(self.manager.candidate["id"], self.receivers, self.user)
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.manager.job)
        self.store.fail = False
        await self.start()
        with self.assertRaises(UPDATES.UpdateError):
            await self.report("completed")
        with self.assertRaises(UPDATES.UpdateError):
            await self.report("installing", "a token or arbitrary package output")

    async def test_outside_hacs_change_blocks_receiver_updates(self):
        await self.start()
        self.disk_version = "3.0.0"
        self.assertEqual(await self.manager.receiver_plan("a" * 32, "receiver-user", "1.0.0"), {"job": None})
        self.assertEqual(self.manager.job["phase"], "failed")

    async def test_every_participant_must_report_running_target_before_ha_restart(self):
        self.receivers.append(dict(self.receivers[0], id="c" * 32, address="192.0.2.2"))
        await self.start()
        await self.manager.receiver_plan("a" * 32, "receiver-user", "2.0.0")
        self.assertEqual((await self.manager.snapshot())["job"]["phase"], "receivers")
        with self.assertRaises(UPDATES.UpdateError):
            await self.manager.restart(self.manager.job["id"], self.user)
        await self.manager.report("c" * 32, "receiver-user", {"job_id": self.manager.job["id"], "attempt": 1,
                                  "status": "restart_required", "error": None})
        self.assertEqual((await self.manager.snapshot())["job"]["phase"], "receivers")
        await self.manager.receiver_plan("c" * 32, "receiver-user", "2.0.0")
        self.assertEqual((await self.manager.snapshot())["job"]["phase"], "ha_restart_required")

    async def test_hacs_failure_requires_explicit_retry_of_same_release(self):
        original = self.hass.services.async_call
        self.hass.services.async_call = AsyncMock(side_effect=API.HomeAssistantError())
        await self.start()
        self.assertEqual(self.manager.job["phase"], "failed")
        self.assertEqual(await self.manager.receiver_plan("a" * 32, "receiver-user", "1.0.0"), {"job": None})
        self.hass.services.async_call = original
        await self.manager.retry(self.manager.job["id"], self.user)
        await self.manager.task
        self.assertEqual(self.manager.job["phase"], "receivers")
        self.assertEqual(self.calls[0][2]["version"], "v2.0.0")

    async def test_expired_selection_never_starts_hacs(self):
        await self.manager.check()
        self.manager.checked_at -= 601
        with self.assertRaises(UPDATES.UpdateError) as caught:
            await self.manager.start(self.manager.candidate["id"], self.receivers, self.user)
        self.assertEqual(caught.exception.code, "release_check_required")
        self.assertEqual(self.calls, [])

    async def test_hacs_accepts_home_assistant_feature_flags_and_rejects_boolean(self):
        class UpdateFeatures(IntFlag):
            INSTALL = 1
            SPECIFIC_VERSION = 2
        self.state.attributes['supported_features'] = UpdateFeatures.INSTALL | UpdateFeatures.SPECIFIC_VERSION
        await self.manager.check()
        self.assertEqual(self.manager.hacs_entity().entity_id,self.state.entity_id)
        self.state.attributes['supported_features'] = True
        with self.assertRaises(UPDATES.UpdateError):
            self.manager.hacs_entity()

    async def test_failed_ha_restart_retains_target_and_requires_new_confirmation(self):
        await self.start()
        await self.manager.receiver_plan("a" * 32, "receiver-user", "2.0.0")
        self.hass.services.async_call = AsyncMock(side_effect=API.HomeAssistantError())
        await self.manager.restart(self.manager.job["id"], self.user)
        await self.manager.restart_task
        self.assertEqual(self.manager.job["error"], "ha_restart_failed")
        self.assertEqual(self.manager.job["phase"], "ha_restart_required")
        self.assertEqual(self.hass.services.async_call.await_count, 1)
        self.hass.services.async_call = AsyncMock()
        await self.manager.restart(self.manager.job["id"], self.user)
        await self.manager.restart_task
        self.assertIsNone(self.manager.job["error"])
        self.assertEqual(self.hass.services.async_call.await_count, 1)

    async def test_malformed_progress_never_changes_transaction(self):
        await self.start()
        saved = copy.deepcopy(self.manager.job)
        for body in ({"status": []}, {"attempt": True}, {"error": []}, {"status": "completed"}):
            report = {"job_id": saved["id"], "attempt": 1, "status": "installing", "error": None}
            report.update(body)
            with self.assertRaises(UPDATES.UpdateError):
                await self.manager.report("a" * 32, "receiver-user", report)
            self.assertEqual(self.manager.job, saved)


class UpdateRouteTests(unittest.IsolatedAsyncioTestCase):
    asyncSetUp = ha_tests.HAPluginTests.asyncSetUp
    asyncTearDown = ha_tests.HAPluginTests.asyncTearDown
    request = ha_tests.HAPluginTests.request

    async def test_update_routes_require_admin_or_bound_receiver_identity(self):
        for method, route, user, expected in [("POST", "/updates", "receiver", 403),
                ("POST", "/updates", "none", 401), ("GET", "/receiver_update", "receiver", 400)]:
            async with await self.request(method, route, user, body={"action": "check"} if method == "POST" else None) as response:
                self.assertEqual(response.status, expected)

    async def test_actual_routes_pin_hacs_and_ipk_and_verify_receiver_after_restart(self):
        disk = [UPDATES.VERSION]
        hacs_state = types.SimpleNamespace(entity_id="update.renamed_by_user", state="on", attributes={
            "release_url": releases.REPOSITORY_URL + "/releases/v2.0.0", "installed_version": "v" + UPDATES.VERSION, "supported_features": 23})
        self.hass.registry.async_get = lambda entity: types.SimpleNamespace(platform="hacs")
        self.hass.states.async_all = lambda: [self.state, hacs_state]
        self.hass.async_create_task = asyncio.create_task
        async def service(domain, service, data, blocking, context):
            self.calls.append((domain, service, data))
            disk[0] = "2.0.0"
            hacs_state.attributes["installed_version"] = "v2.0.0"
        self.hass.services.async_call = service
        manager = self.runtime.updates = UPDATES.UpdateManager(self.hass, Store())
        self.addAsyncCleanup(manager.close)
        client = CompanionClient(self.url, "receiver", receiver_id="a" * 32)
        with patch.object(UPDATES, "downloaded_version", side_effect=lambda: disk[0]), \
             patch.object(UPDATES, "downloaded_protocol_version", return_value=2), \
             patch.object(UPDATES, "fetch_latest_release", return_value=release()):
            self.assertIsNone(await asyncio.to_thread(client.get_update))
            async with await self.request("POST", "/updates", body={"action": "check"}) as response:
                self.assertEqual(response.status, 200)
                candidate = (await response.json())["candidate"]
            async with await self.request("POST", "/updates", body={"action": "start", "candidate_id": candidate["id"],
                                                                      "receiver_ids": ["a" * 32]}) as response:
                self.assertEqual(response.status, 200)
            await manager.task
            job = await asyncio.to_thread(client.get_update)
            self.assertEqual(job["release"], release())
            self.assertEqual(self.calls, [("update", "install", {"entity_id": "update.renamed_by_user", "version": "v2.0.0"})])
            await asyncio.to_thread(client.report_update, job, "installing")
            await asyncio.to_thread(client.report_update, job, "restart_required")
            # A second user cannot report progress for this receiver, even with its UUID.
            foreign = {COMPONENT_HEADER: "receiver", VERSION_HEADER: "2.0.0", RECEIVER_HEADER: "a" * 32, PROTOCOL_HEADER: "2"}
            async with await self.request("GET", "/receiver_update", "reader", peer_headers=foreign) as response:
                self.assertEqual(await response.json(), {"job": None})
            async with await self.request("GET", "/receiver_update", "receiver", peer_headers=foreign) as response:
                self.assertEqual((await response.json())["job"]["status"], "completed")
            async with await self.request("GET", "/menu", "receiver", peer_headers=foreign) as response:
                self.assertEqual(response.status, 426)
            async with await self.request("GET", "/compatibility") as response:
                self.assertEqual((await response.json())["updates"]["job"]["phase"], "ha_restart_required")
            with patch.object(UPDATES, "VERSION", "2.0.0"), patch.object(UPDATES, "PROTOCOL_VERSION", 2):
                async with await self.request("GET", "/compatibility") as response:
                    self.assertEqual((await response.json())["updates"]["job"]["phase"], "completed")


if __name__ == "__main__":
    unittest.main()
