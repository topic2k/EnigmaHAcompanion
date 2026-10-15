"""Receiver-initiated updates: exact releases, consent and interruption recovery."""

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

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
