"""Receiver-only stable updates, exact repair releases and interruption recovery."""

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "protocol"), str(ROOT / "enigma2")]
from companion import updater
from enigmaha_protocol import releases


class LocalUpdateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.updater = updater.ReceiverUpdater(str(Path(directory.name) / "update.json"))
        self.release = {"version": "9.0.0", "ipk_url": releases.asset_url("9.0.0", releases.ipk_name("9.0.0")),
                        "ipk_sha256": hashlib.sha256(b"ipk").hexdigest(), "ipk_size": 3}

    def prepare(self):
        with patch.object(updater, "fetch_release", return_value=self.release) as fetch:
            job = self.updater.local_update("9.0.0")
        fetch.assert_called_once_with("9.0.0")
        return job

    def available(self):
        with patch.object(updater, "fetch_latest_release", return_value=self.release) as fetch, \
             patch.object(updater, "fetch_release") as exact, \
             patch.object(updater.subprocess, "run") as run:
            job = self.updater.available_update()
        fetch.assert_called_once_with()
        exact.assert_not_called()
        run.assert_not_called()
        return job

    def test_available_update_is_local_latest_and_requires_consent(self):
        job = self.available()
        self.assertEqual(job["release"], self.release)
        self.assertTrue(job["local"])
        self.assertEqual(job["status"], "pending")
        self.assertEqual(job["attempt"], 1)
        self.assertIsNone(self.updater.journal())
        with self.assertRaises(releases.UpdateError):
            self.updater.perform(job, None)
        self.assertIsNone(self.updater.journal())

    def test_available_update_returns_none_for_current_or_older_receiver_release(self):
        for version in ("9.0.0", "10.0.0"):
            with self.subTest(version=version), patch.object(updater, "VERSION", version):
                self.assertIsNone(self.available())
                self.assertIsNone(self.updater.journal())

    def test_available_update_compares_versions_numerically(self):
        with patch.object(updater, "VERSION", "8.10.0"):
            self.assertEqual(self.available()["release"]["version"], "9.0.0")
        with patch.object(updater, "VERSION", "10.0.0"):
            self.assertIsNone(self.available())

    def test_available_update_resumes_only_same_confirmed_local_release(self):
        job = self.prepare()
        job["attempt"] = 2
        self.updater.confirm(job)
        before = Path(self.updater.path).read_bytes()
        resumed = self.available()
        self.assertEqual(resumed, job)
        self.assertEqual(Path(self.updater.path).read_bytes(), before)
        newer = dict(self.release, version="10.0.0",
                     ipk_url=releases.asset_url("10.0.0", releases.ipk_name("10.0.0")))
        with patch.object(updater, "fetch_latest_release", return_value=newer):
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.available_update()
        self.assertEqual(caught.exception.code, "install_uncertain")
        self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_available_update_recovers_local_restart_before_release_lookup(self):
        job = self.prepare()
        for status in ("installing", "uncertain", "restart_required"):
            with self.subTest(status=status):
                self.updater.save(job, status)
                before = Path(self.updater.path).read_bytes()
                with patch.object(self.updater, "installed", return_value=True) as installed, \
                     patch.object(updater, "fetch_latest_release") as fetch:
                    restart = self.updater.available_update()
                installed.assert_called_once_with("9.0.0")
                fetch.assert_not_called()
                self.assertEqual(restart, dict(job, release={"version": "9.0.0"}, status="restart_required"))
                self.assertEqual(Path(self.updater.path).read_bytes(), before)
                with patch.object(self.updater, "installed", return_value=False), \
                     patch.object(updater, "fetch_latest_release") as fetch:
                    with self.assertRaises(releases.UpdateError) as caught:
                        self.updater.available_update()
                self.assertEqual(caught.exception.code, "install_uncertain")
                fetch.assert_not_called()
                self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_available_update_acknowledges_running_local_release_then_checks_latest(self):
        job = self.prepare()
        self.updater.save(job, "restart_required")
        with patch.object(updater, "VERSION", "9.0.0"), \
             patch.object(self.updater, "installed") as installed:
            self.assertIsNone(self.available())
        installed.assert_not_called()
        self.assertEqual(self.updater.journal()["status"], "completed")

    def test_available_update_preserves_active_coordinated_jobs(self):
        job = dict(self.prepare(), local=False)
        for status in ("confirmed", "installing", "uncertain", "restart_required"):
            with self.subTest(status=status):
                self.updater.save(job, status)
                before = Path(self.updater.path).read_bytes()
                with patch.object(updater, "fetch_latest_release") as fetch, \
                     patch.object(self.updater, "installed") as installed:
                    with self.assertRaises(releases.UpdateError) as caught:
                        self.updater.available_update()
                self.assertEqual(caught.exception.code, "install_uncertain")
                fetch.assert_not_called()
                installed.assert_not_called()
                self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_available_update_can_follow_inactive_jobs_without_rewriting_them(self):
        for local in (False, True):
            for status in ("failed", "completed"):
                with self.subTest(local=local, status=status):
                    job = dict(self.prepare(), local=local)
                    self.updater.save(job, status)
                    before = Path(self.updater.path).read_bytes()
                    new = self.available()
                    self.assertNotEqual(new["id"], job["id"])
                    self.assertTrue(new["local"])
                    self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_available_update_rejects_bad_release_results_and_corrupt_journal(self):
        for release in (None, {}, dict(self.release, ipk_sha256="bad")):
            with self.subTest(release=release), \
                 patch.object(updater, "fetch_latest_release", return_value=release), \
                 patch.object(updater.subprocess, "run") as run:
                with self.assertRaises(releases.UpdateError) as caught:
                    self.updater.available_update()
                self.assertEqual(caught.exception.code, "invalid_release")
                run.assert_not_called()
                self.assertIsNone(self.updater.journal())
        Path(self.updater.path).write_text("{", encoding="utf-8")
        with patch.object(updater, "fetch_latest_release") as fetch:
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.available_update()
        self.assertEqual(caught.exception.code, "update_storage_failed")
        fetch.assert_not_called()

    def test_active_install_lock_blocks_discovery_and_confirmation(self):
        job = self.prepare()
        with updater._INSTALL_LOCK:
            with patch.object(updater, "fetch_latest_release") as fetch:
                with self.assertRaises(releases.UpdateError) as caught:
                    self.updater.available_update()
                self.assertEqual(caught.exception.code, "install_uncertain")
                fetch.assert_not_called()
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.confirm(job)
            self.assertEqual(caught.exception.code, "install_uncertain")
        self.assertIsNone(self.updater.journal())

    def test_confirm_cannot_replace_or_reclassify_active_job(self):
        job = self.prepare()
        replacements = (dict(job, id="c" * 32), dict(job, attempt=2), dict(job, local=False))
        for status in ("confirmed", "installing", "uncertain", "restart_required"):
            for replacement in replacements:
                with self.subTest(status=status, replacement=replacement):
                    self.updater.save(job, status)
                    before = Path(self.updater.path).read_bytes()
                    with self.assertRaises(releases.UpdateError) as caught:
                        self.updater.confirm(replacement)
                    self.assertEqual(caught.exception.code, "install_uncertain")
                    self.assertEqual(Path(self.updater.path).read_bytes(), before)
                    self.updater.confirm(job)
                    self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_stale_local_install_cannot_overwrite_another_confirmed_job(self):
        current = self.prepare()
        self.updater.confirm(current)
        before = Path(self.updater.path).read_bytes()
        for stale in (dict(current, id="c" * 32), dict(current, attempt=2)):
            with self.subTest(stale=stale), patch.object(updater.subprocess, "run") as run:
                with self.assertRaises(releases.UpdateError) as caught:
                    self.updater.perform(stale, None)
            self.assertEqual(caught.exception.code, "install_uncertain")
            self.assertEqual(Path(self.updater.path).read_bytes(), before)
            run.assert_not_called()

    def test_local_job_cannot_claim_coordinated_consent(self):
        job = self.prepare()
        self.updater.confirm(dict(job, local=False))
        before = Path(self.updater.path).read_bytes()
        with patch.object(updater.subprocess, "run") as run:
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.perform(job, None)
        self.assertEqual(caught.exception.code, "install_uncertain")
        self.assertEqual(Path(self.updater.path).read_bytes(), before)
        run.assert_not_called()

    def test_preparation_does_not_record_consent_and_blocks_downgrades(self):
        job = self.prepare()
        self.assertTrue(job["local"])
        self.assertIsNone(self.updater.journal())
        with self.assertRaises(releases.UpdateError):
            self.updater.perform(job, None)
        for version in ("0.0.0", updater.VERSION, "invalid"):
            with self.subTest(version=version), patch.object(updater, "fetch_release") as fetch:
                with self.assertRaises(releases.UpdateError):
                    self.updater.local_update(version)
                fetch.assert_not_called()

    def test_local_install_checks_package_and_recovers_without_second_install(self):
        job = self.prepare()
        self.updater.confirm(job)
        self.assertTrue(self.updater.journal()["local"])
        commands = []
        def run(command, **kwargs):
            commands.append(command[1])
            self.assertFalse(kwargs.get("shell", False))
            fields = "Package: " + releases.PACKAGE + "\nVersion: 9.0.0\nArchitecture: all\nStatus: install ok installed\n"
            return types.SimpleNamespace(returncode=0, stdout=fields)
        with patch.object(updater.os, "geteuid", return_value=0, create=True), \
             patch.object(updater, "open_public", return_value=io.BytesIO(b"ipk")), \
             patch.object(updater.subprocess, "run", side_effect=run):
            self.updater.perform(job, None)
            self.assertEqual(commands, ["info", "install", "status"])
            self.updater.perform(job, None)
            self.assertEqual(commands.count("install"), 1)
            restart = self.updater.local_restart()
            self.assertEqual(restart["status"], "restart_required")
        with patch.object(updater, "VERSION", "9.0.0"):
            self.assertIsNone(self.updater.local_restart())
        self.assertEqual(self.updater.journal()["status"], "completed")
        self.assertTrue(self.updater.journal()["local"])

    def test_manual_install_never_uses_an_accidentally_supplied_ha_client(self):
        job = self.available()
        self.updater.confirm(job)
        client = types.SimpleNamespace(report_update=lambda *args: self.fail("local update reported to HA"))
        fields = "Package: " + releases.PACKAGE + "\nVersion: 9.0.0\nArchitecture: all\nStatus: install ok installed\n"
        with patch.object(updater.os, "geteuid", return_value=0, create=True), \
             patch.object(updater, "open_public", return_value=io.BytesIO(b"ipk")), \
             patch.object(updater.subprocess, "run", return_value=types.SimpleNamespace(returncode=0, stdout=fields)) as run:
            self.updater.perform(job, client)
        self.assertEqual([call.args[0][1] for call in run.call_args_list], ["info", "install", "status"])
        self.assertEqual(self.updater.journal()["status"], "restart_required")

    def test_uncertain_install_is_never_replayed_or_overwritten(self):
        job = self.prepare()
        self.updater.save(job, "uncertain")
        before = Path(self.updater.path).read_bytes()
        with patch.object(self.updater, "installed", return_value=False):
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.local_restart()
        self.assertEqual(caught.exception.code, "install_uncertain")
        with self.assertRaises(releases.UpdateError):
            self.updater.local_update("10.0.0")
        coordinated = dict(job, id="c" * 32, local=False)
        with self.assertRaises(releases.UpdateError):
            self.updater.confirm(coordinated)
        self.assertEqual(Path(self.updater.path).read_bytes(), before)
        self.assertEqual(self.prepare()["id"], job["id"])

    def test_existing_coordinated_journal_is_preserved(self):
        job = dict(self.prepare(), local=False)
        for status in ("confirmed", "installing", "uncertain", "restart_required"):
            self.updater.save(job, status)
            before = Path(self.updater.path).read_bytes()
            with patch.object(self.updater, "installed", return_value=False):
                if status == "confirmed":
                    self.assertIsNone(self.updater.local_restart())
                else:
                    with self.assertRaises(releases.UpdateError) as caught:
                        self.updater.local_restart()
                    self.assertEqual(caught.exception.code, "install_uncertain")
            with self.assertRaises(releases.UpdateError):
                self.updater.local_update("9.0.0")
            self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_coordinated_restart_recovers_verified_install_without_ha_or_reinstall(self):
        job = dict(self.prepare(), local=False)
        for status in ("installing", "uncertain", "restart_required"):
            with self.subTest(status=status):
                self.updater.save(job, status)
                before = Path(self.updater.path).read_bytes()
                with patch.object(self.updater, "installed", return_value=True) as installed, \
                     patch.object(updater, "fetch_release") as fetch, \
                     patch.object(updater.subprocess, "run") as run:
                    restart = self.updater.local_restart()
                    installed.assert_called_once_with("9.0.0")
                    fetch.assert_not_called()
                    run.assert_not_called()
                self.assertEqual(restart, {"id": job["id"], "attempt": job["attempt"],
                    "release": {"version": "9.0.0"}, "status": "restart_required"})
                self.assertEqual(Path(self.updater.path).read_bytes(), before)
                with patch.object(updater, "VERSION", "9.0.0"):
                    self.assertIsNone(self.updater.local_restart())
                self.assertEqual(self.updater.journal()["status"], "completed")
                self.assertNotIn("local", self.updater.journal())

    def test_unclaimed_failed_and_completed_coordinated_jobs_do_not_offer_offline_restart(self):
        job = dict(self.prepare(), local=False)
        for status in ("confirmed", "failed", "completed"):
            with self.subTest(status=status):
                self.updater.save(job, status)
                before = Path(self.updater.path).read_bytes()
                with patch.object(self.updater, "installed") as installed:
                    self.assertIsNone(self.updater.local_restart())
                    installed.assert_not_called()
                self.assertEqual(Path(self.updater.path).read_bytes(), before)

    def test_nonlocal_job_cannot_bypass_ha_reporting(self):
        job = dict(self.prepare(), local=False)
        self.updater.confirm(job)
        with self.assertRaises(releases.UpdateError):
            self.updater.perform(job, None)

    def test_failed_checksum_cannot_install_local_package(self):
        job = self.prepare()
        self.updater.confirm(job)
        with patch.object(updater.os, "geteuid", return_value=0, create=True), \
             patch.object(updater, "open_public", return_value=io.BytesIO(b"bad")), \
             patch.object(updater.subprocess, "run") as run:
            with self.assertRaises(releases.UpdateError) as caught:
                self.updater.perform(job, None)
        self.assertEqual(caught.exception.code, "checksum_failed")
        run.assert_not_called()
        self.assertEqual(self.updater.journal()["status"], "failed")


class ExactReleaseTests(unittest.TestCase):
    def metadata(self):
        version = "9.0.0"
        return {"tag_name": "v" + version, "draft": False, "prerelease": False,
                "assets": [{"name": name, "size": 3, "browser_download_url": releases.asset_url(version, name)}
                           for name in (releases.ipk_name(version), "enigmaha_companion.zip", "SHA256SUMS.txt")]}

    def test_pins_requested_tag_and_preserves_latest_release_checks(self):
        sums = "a" * 64 + "  " + releases.ipk_name("9.0.0") + "\n" + "b" * 64 + "  enigmaha_companion.zip\n"
        for version, suffix in (("9.0.0", "tags/v9.0.0"), (None, "latest")):
            with patch.object(releases, "_read_public", side_effect=[json.dumps(self.metadata()).encode(), sums.encode()]) as read:
                result = releases.fetch_latest_release() if version is None else releases.fetch_release(version)
            self.assertEqual(result["version"], "9.0.0")
            self.assertTrue(read.call_args_list[0].args[0].endswith("/releases/" + suffix))

    def test_wrong_tag_prerelease_and_invalid_version_are_rejected(self):
        for metadata in (self.metadata(), dict(self.metadata(), prerelease=True)):
            with patch.object(releases, "_read_public", return_value=json.dumps(metadata).encode()):
                with self.assertRaises(releases.UpdateError):
                    releases.fetch_release("8.0.0")
        with patch.object(releases, "_read_public") as read:
            with self.assertRaises(releases.UpdateError):
                releases.fetch_release("../latest")
            read.assert_not_called()

    def test_available_update_uses_validated_latest_stable_release_without_ha(self):
        sums = "a" * 64 + "  " + releases.ipk_name("9.0.0") + "\n" + "b" * 64 + "  enigmaha_companion.zip\n"
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(releases, "_read_public", side_effect=[json.dumps(self.metadata()).encode(), sums.encode()]) as read, \
             patch.object(updater, "fetch_release") as exact, \
             patch.object(updater.subprocess, "run") as run:
            receiver = updater.ReceiverUpdater(str(Path(directory) / "update.json"))
            job = receiver.available_update()
            self.assertIsNone(receiver.journal())
        self.assertEqual(job["release"]["version"], "9.0.0")
        self.assertTrue(job["local"])
        self.assertTrue(read.call_args_list[0].args[0].endswith("/releases/latest"))
        self.assertEqual(read.call_count, 2)
        exact.assert_not_called()
        run.assert_not_called()

    def test_available_update_rejects_missing_or_broken_latest_releases(self):
        metadata = self.metadata()
        cases = ([HTTPError("https://api.github.com/", 404, "Not Found", {}, None)],
                 [b"not json"], [b"null"],
                 [json.dumps(dict(metadata, draft=True)).encode()],
                 [json.dumps(dict(metadata, prerelease=True)).encode()],
                 [json.dumps(dict(metadata, assets=metadata["assets"][1:])).encode()],
                 [json.dumps(metadata).encode(), b"invalid checksums"],
                 [json.dumps(metadata).encode(), b""])
        self.addCleanup(cases[0][0].close)
        for responses in cases:
            with self.subTest(responses=responses), tempfile.TemporaryDirectory() as directory, \
                 patch.object(releases, "_read_public", side_effect=responses), \
                 patch.object(updater.subprocess, "run") as run:
                receiver = updater.ReceiverUpdater(str(Path(directory) / "update.json"))
                with self.assertRaises(releases.UpdateError) as caught:
                    receiver.available_update()
                self.assertIn(caught.exception.code, {"invalid_release", "release_check_failed"})
                self.assertIsNone(receiver.journal())
                run.assert_not_called()
