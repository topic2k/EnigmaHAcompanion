"""Confirmed OpenATV IPK installation with a durable journal and no shell commands."""

import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path
import subprocess
import tempfile
from threading import Lock
from uuid import uuid4

from enigmaha_protocol.compatibility import VERSION, valid_receiver_id
from enigmaha_protocol.releases import PACKAGE, UpdateError, fetch_release, open_public, validate_release, version_tuple

IDENTITY_PATH = "/etc/enigma2/enigmaha_companion_receiver_id"
JOURNAL_PATH = "/etc/enigma2/enigmaha_companion_update.json"
OPKG = "/usr/bin/opkg"
_INSTALL_LOCK = Lock()
_IDENTITY_LOCK = Lock()


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".enigmaha-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_receiver_id(path=IDENTITY_PATH):
    with _IDENTITY_LOCK:
        try:
            receiver_id = Path(path).read_text(encoding="ascii").strip()
        except FileNotFoundError:
            receiver_id = uuid4().hex
            atomic_write(path, receiver_id + "\n")
        if not valid_receiver_id(receiver_id):
            raise ValueError("invalid receiver identity")
        return receiver_id


class ReceiverUpdater:
    def __init__(self, journal_path=JOURNAL_PATH):
        self.path = journal_path

    def journal(self):
        try:
            value = json.loads(Path(self.path).read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            raise UpdateError("update_storage_failed") from None
        if (not isinstance(value, dict) or not valid_receiver_id(value.get("id"))
                or type(value.get("attempt")) is not int or value["attempt"] < 1
                or not isinstance(value.get("status"), str)
                or value.get("status") not in {"confirmed", "installing", "restart_required", "failed", "uncertain", "completed"}
                or ("local" in value and type(value["local"]) is not bool)):
            raise UpdateError("update_storage_failed")
        try:
            version_tuple(value.get("version"))
        except UpdateError:
            raise UpdateError("update_storage_failed") from None
        return value

    def save(self, job, status):
        try:
            value = {"id": job["id"], "version": job["release"]["version"],
                     "attempt": job["attempt"], "status": status}
            if job.get("local") is True:
                value["local"] = True
            atomic_write(self.path, json.dumps(value))
        except OSError:
            raise UpdateError("update_storage_failed") from None

    def local_update(self, version):
        """Pin a receiver-only update to the running HA release, without downgrades."""
        if version_tuple(version) <= version_tuple(VERSION):
            raise UpdateError("invalid_package")
        journal = self.journal()
        resume = journal and journal["status"] in {"confirmed", "installing", "uncertain", "restart_required"}
        if resume and (journal.get("local") is not True or journal["version"] != version):
            raise UpdateError("install_uncertain")
        return {"id": journal["id"] if resume else uuid4().hex,
                "attempt": journal["attempt"] if resume else 1,
                "release": fetch_release(version), "status": "pending", "local": True}

    def local_restart(self):
        """Recover installed updates before contacting HA; never replay opkg."""
        journal = self.journal()
        if not journal:
            return None
        recovering = journal["status"] in {"installing", "uncertain", "restart_required"}
        if journal.get("local") is not True and not recovering:
            return None
        job = {"id": journal["id"], "attempt": journal["attempt"],
               "release": {"version": journal["version"]}, "status": "restart_required"}
        if journal.get("local") is True:
            job["local"] = True
        if journal["version"] == VERSION:
            self.acknowledge_running(job)
        elif recovering:
            if not self.installed(journal["version"]):
                raise UpdateError("install_uncertain")
            return job
        return None

    @staticmethod
    def report(client, job, status, error=None):
        if client is not None:
            if error is None:
                client.report_update(job, status)
            else:
                client.report_update(job, status, error)

    def confirm(self, job):
        journal = self.journal()
        if journal and journal["status"] in {"installing", "uncertain", "restart_required"}:
            if journal["id"] == job["id"] and journal["version"] == job["release"]["version"]:
                return
            raise UpdateError("install_uncertain")
        self.save(job, "confirmed")

    def acknowledge_running(self, job):
        if job and job["release"]["version"] == VERSION:
            journal = self.journal()
            if journal and journal["id"] == job["id"] and journal["status"] != "completed":
                self.save(job, "completed")

    @staticmethod
    def package_fields(output):
        return dict(line.split(": ", 1) for line in output.splitlines() if ": " in line)

    def installed(self, version):
        try:
            result = subprocess.run([OPKG, "status", PACKAGE], capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return False
        fields = self.package_fields(result.stdout)
        return (result.returncode == 0 and fields.get("Package") == PACKAGE and fields.get("Version") == version
                and fields.get("Status") == "install ok installed")

    def download(self, release, destination):
        digest = hashlib.sha256()
        size = 0
        try:
            with open_public(release["ipk_url"]) as response, open(destination, "wb") as output:
                while True:
                    chunk = response.read(64 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > release["ipk_size"]:
                        raise UpdateError("checksum_failed")
                    digest.update(chunk)
                    output.write(chunk)
        except (OSError, ValueError, HTTPException):
            raise UpdateError("download_failed") from None
        if size != release["ipk_size"] or digest.hexdigest() != release["ipk_sha256"]:
            raise UpdateError("checksum_failed")

    def perform(self, job, client):
        if client is None and job.get("local") is not True:
            raise UpdateError("invalid_package")
        release = validate_release(job["release"])
        target = release["version"]
        if version_tuple(target) < version_tuple(VERSION):
            raise UpdateError("invalid_package")
        if not _INSTALL_LOCK.acquire(blocking=False):
            raise UpdateError("install_uncertain")
        try:
            journal = self.journal()
            if not journal or journal["id"] != job["id"] or journal["version"] != target:
                raise UpdateError("install_uncertain")
            if journal["status"] in {"installing", "uncertain", "restart_required"}:
                if not self.installed(target):
                    raise UpdateError("install_uncertain")
                self.save(job, "restart_required")
                self.report(client, job, "restart_required")
                return
            if journal["status"] != "confirmed" or journal["attempt"] != job["attempt"]:
                raise UpdateError("install_uncertain")
            if os.geteuid() != 0:
                raise UpdateError("permission_denied")
            # Idempotent claim. A lost reply cannot trigger an unconfirmed installation.
            self.report(client, job, "installing")
            with tempfile.TemporaryDirectory(prefix="enigmaha-update-") as directory:
                path = str(Path(directory) / "companion.ipk")
                self.download(release, path)
                try:
                    result = subprocess.run([OPKG, "info", path], capture_output=True, text=True, timeout=15, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    raise UpdateError("invalid_package") from None
                fields = self.package_fields(result.stdout)
                if (result.returncode != 0 or fields.get("Package") != PACKAGE
                        or fields.get("Version") != target or fields.get("Architecture") != "all"):
                    raise UpdateError("invalid_package")
                self.save(job, "installing")
                try:
                    with tempfile.TemporaryFile() as log:
                        result = subprocess.run([OPKG, "install", path], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                                timeout=300, check=False)
                except (OSError, subprocess.TimeoutExpired):
                    self.save(job, "uncertain")
                    raise UpdateError("install_uncertain") from None
                if result.returncode != 0 or not self.installed(target):
                    self.save(job, "uncertain")
                    raise UpdateError("install_uncertain")
                self.save(job, "restart_required")
            self.report(client, job, "restart_required")
        except UpdateError as error:
            # The journal written before opkg is authoritative if reporting fails.
            journal = self.journal()
            if journal and journal["status"] not in {"installing", "uncertain", "restart_required"}:
                self.save(job, "failed")
            reported_error = "install_uncertain" if journal and journal["status"] in {"installing", "uncertain"} else error.code
            try:
                self.report(client, job, "failed", reported_error)
            except Exception:
                pass
            raise
        finally:
            _INSTALL_LOCK.release()
