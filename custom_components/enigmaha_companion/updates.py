"""Confirmed HACS/IPK update, pinned to one release and persisted across restarts."""

import asyncio
import ast
import copy
import json
from pathlib import Path
from time import monotonic
from uuid import uuid4

from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry

from .enigmaha_protocol.compatibility import VERSION, PROTOCOL_VERSION, protocol_version, valid_receiver_id
from .enigmaha_protocol.releases import (
    REPOSITORY_URL, UpdateError, fetch_latest_release, fetch_release, validate_release, version_tuple,
)


def normalized_version(value):
    if isinstance(value, str):
        value = value.removeprefix("v")
        try:
            version_tuple(value)
            return value
        except UpdateError:
            pass
    return None


def downloaded_version():
    return json.loads(Path(__file__).with_name("manifest.json").read_text(encoding="utf-8"))["version"]


def downloaded_protocol_version():
    """Read installed source without importing cached or still-running modules."""
    tree = ast.parse((Path(__file__).parent / "enigmaha_protocol/compatibility.py").read_text(encoding="utf-8"))
    values = {target.id: ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
              for target in node.targets if isinstance(target, ast.Name) and target.id in {"VERSION", "PROTOCOL_VERSION"}}
    value = values.get("PROTOCOL_VERSION")
    if value is None:
        value = protocol_version(None, values.get("VERSION"))
    if type(value) is not int or not 1 <= value <= 99999:
        raise ValueError("invalid installed protocol identity")
    return value


class UpdateManager:
    def __init__(self, hass, store, job=None):
        self.hass, self.store, self.job = hass, store, job
        self.lock = asyncio.Lock()
        self.candidate = None
        self.checked_at = 0
        self.task = None
        self.restart_task = None
        self.active = True
        self.on_change = None
        self.listeners = set()
        if job is not None:
            validate_release(job["release"])

    def add_listener(self, listener):
        """Observe durable job changes alongside the existing repair callback."""
        self.listeners.add(listener)
        return lambda: self.listeners.discard(listener)

    async def save(self, job):
        # Do not advance the live state if persistence fails.
        try:
            await self.store.async_save(job)
        except (OSError, HomeAssistantError):
            raise UpdateError("update_storage_failed") from None
        self.job = job
        for listener in tuple(self.listeners):
            listener()
        if self.on_change is not None:
            await self.on_change()

    def hacs_entity(self):
        registry = entity_registry.async_get(self.hass)
        matches = []
        for state in self.hass.states.async_all():
            if not state.entity_id.startswith("update.") or state.state in {"unknown", "unavailable"}:
                continue
            entry = registry.async_get(state.entity_id)
            release_url = state.attributes.get("release_url", "")
            features = state.attributes.get("supported_features", 0)
            if (entry is not None and entry.platform == "hacs" and isinstance(release_url, str)
                    and (release_url == REPOSITORY_URL or release_url.startswith(REPOSITORY_URL + "/releases/"))
                    and isinstance(features, int) and not isinstance(features, bool) and features & 3 == 3):
                matches.append(state)
        if len(matches) != 1:
            raise UpdateError("hacs_unavailable")
        return matches[0]

    async def check(self):
        self.hacs_entity()
        release = await self.hass.async_add_executor_job(fetch_latest_release)
        if version_tuple(release["version"]) < version_tuple(VERSION):
            raise UpdateError("downgrade_blocked")
        return await self._select_release(release)

    async def check_receivers(self):
        """Offer the running HA release without requiring or changing HACS."""
        release = await self.hass.async_add_executor_job(fetch_release, VERSION)
        if release["version"] != VERSION:
            raise UpdateError("invalid_release")
        return await self._select_release(release)

    async def _select_release(self, release):
        async with self.lock:
            if not self.active:
                raise UpdateError("update_unavailable")
            self.candidate = {"id": uuid4().hex, "release": release}
            self.checked_at = monotonic()
            return copy.deepcopy(self.candidate)

    async def refresh(self):
        if not self.job or self.job["phase"] in {"failed", "completed", "cancelled"}:
            return
        job = copy.deepcopy(self.job)
        target = job["release"]["version"]
        if job["phase"] == "ha_installing" and self.task is not None and not self.task.done():
            return
        try:
            installed = await self.hass.async_add_executor_job(downloaded_version)
            target_protocol = await self.hass.async_add_executor_job(downloaded_protocol_version)
        except (OSError, ValueError):
            installed = None
            target_protocol = None
        if installed == target:
            job["protocol_version"] = target_protocol
        if job["phase"] == "ha_installing":
            # After a process interruption, inspect the installed files. Never replay the install.
            if installed == target:
                job["phase"] = "receivers"
            else:
                job["phase"], job["error"] = "failed", "ha_install_interrupted"
        if job["phase"] in {"receivers", "ha_restart_required"}:
            if installed != target:
                job["phase"], job["error"] = "failed", "hacs_version_changed"
            elif all(receiver["status"] == "completed" for receiver in job["receivers"]):
                job["phase"] = "completed" if VERSION == target and PROTOCOL_VERSION == target_protocol else "ha_restart_required"
        if job != self.job:
            await self.save(job)

    async def snapshot(self):
        async with self.lock:
            await self.refresh()
            try:
                state = self.hacs_entity()
                hacs = {"entity_id": state.entity_id, "installed_version": state.attributes.get("installed_version")}
            except UpdateError:
                hacs = None
            return {"hacs": hacs, "candidate": copy.deepcopy(self.candidate), "job": self.public_job()}

    def public_job(self):
        if self.job is None:
            return None
        result = copy.deepcopy(self.job)
        for receiver in result["receivers"]:
            receiver.pop("user_id", None)
        return result

    async def start(self, candidate_id, receivers, user, *, receiver_only=False):
        async with self.lock:
            if not self.active:
                raise UpdateError("update_unavailable")
            if self.job and self.job["phase"] not in {"completed", "failed", "cancelled"}:
                if self.job["candidate_id"] == candidate_id:
                    return  # Lost HTTP reply: return the existing job, do not repeat HACS.
                raise UpdateError("update_in_progress")
            if (self.candidate is None or self.candidate["id"] != candidate_id
                    or monotonic() - self.checked_at > 600):
                raise UpdateError("release_check_required")
            entity = None if receiver_only else self.hacs_entity()
            if entity is not None and entity.attributes.get("in_progress"):
                raise UpdateError("update_in_progress")
            release = self.candidate["release"]
            target = release["version"]
            if (receiver_only and not receivers) or any(not valid_receiver_id(receiver.get("id")) or receiver["status"] == "unidentified_peer"
                                    for receiver in receivers):
                raise UpdateError("receiver_update_unavailable")
            if any(receiver.get("version") is None or version_tuple(receiver["version"]) > version_tuple(target)
                   for receiver in receivers):
                raise UpdateError("downgrade_blocked")
            if receiver_only:
                try:
                    installed = await self.hass.async_add_executor_job(downloaded_version)
                    installed_protocol = await self.hass.async_add_executor_job(downloaded_protocol_version)
                except (OSError, ValueError):
                    raise UpdateError("hacs_version_changed") from None
                if target != VERSION or installed != VERSION or installed_protocol != PROTOCOL_VERSION:
                    raise UpdateError("hacs_version_changed")
                if not self.active:
                    raise UpdateError("update_unavailable")
            elif normalized_version(entity.attributes.get("installed_version")) not in (VERSION, target):
                raise UpdateError("hacs_version_changed")
            if target == VERSION and all(receiver["version"] == target and receiver["status"] == "compatible" for receiver in receivers):
                raise UpdateError("already_current")
            job = {"id": uuid4().hex, "candidate_id": candidate_id, "release": copy.deepcopy(release),
                   "entity_id": entity.entity_id if entity else None,
                   "phase": "receivers" if receiver_only else "ha_installing", "error": None,
                   "receivers": [{"id": receiver["id"], "user_id": receiver["user_id"],
                                  "address": receiver["address"], "version": receiver["version"],
                                  "status": "completed" if receiver["version"] == target and receiver["status"] == "compatible" else "pending",
                                  "attempt": 1, "error": None} for receiver in receivers]}
            if receiver_only:
                job["protocol_version"] = PROTOCOL_VERSION
            await self.save(job)
            if not receiver_only:
                self.task = self.hass.async_create_task(self.install_ha(user.id if user is not None else None))

    async def install_ha(self, user_id):
        try:
            target = self.job["release"]["version"]
            state = self.hacs_entity()
            if state.entity_id != self.job["entity_id"]:
                raise UpdateError("hacs_version_changed")
            installed = normalized_version(state.attributes.get("installed_version"))
            if installed is None or version_tuple(installed) > version_tuple(target):
                raise UpdateError("downgrade_blocked")
            if normalized_version(state.attributes.get("installed_version")) != target:
                await self.hass.services.async_call("update", "install", {
                    "entity_id": state.entity_id, "version": "v" + target,
                }, blocking=True, context=Context(user_id=user_id))
            if await self.hass.async_add_executor_job(downloaded_version) != target:
                raise UpdateError("hacs_install_failed")
            async with self.lock:
                job = copy.deepcopy(self.job)
                job["protocol_version"] = await self.hass.async_add_executor_job(downloaded_protocol_version)
                job["phase"], job["error"] = "receivers", None
                await self.save(job)
                await self.refresh()
        except (UpdateError, HomeAssistantError, OSError, ValueError) as error:
            async with self.lock:
                job = copy.deepcopy(self.job)
                job["phase"], job["error"] = "failed", error.code if isinstance(error, UpdateError) else "hacs_install_failed"
                await self.save(job)

    def participant(self, receiver_id, user_id):
        if self.job:
            return next((receiver for receiver in self.job["receivers"]
                         if receiver["id"] == receiver_id and receiver["user_id"] == user_id), None)
        return None

    async def receiver_plan(self, receiver_id, user_id, version, protocol=PROTOCOL_VERSION):
        async with self.lock:
            await self.refresh()
            receiver = self.participant(receiver_id, user_id)
            if receiver is None or self.job["phase"] in {"ha_installing", "failed", "cancelled"}:
                return {"job": None}
            if (version == self.job["release"]["version"] and protocol == self.job.get("protocol_version", PROTOCOL_VERSION)
                    and receiver["status"] != "completed"):
                job = copy.deepcopy(self.job)
                next(item for item in job["receivers"] if item["id"] == receiver_id and item["user_id"] == user_id).update(
                    status="completed", version=version, error=None)
                await self.save(job)
            await self.refresh()
            receiver = self.participant(receiver_id, user_id)
            return {"job": {"id": self.job["id"], "release": copy.deepcopy(self.job["release"]),
                            "status": receiver["status"], "attempt": receiver["attempt"]}}

    async def report(self, receiver_id, user_id, body):
        async with self.lock:
            receiver = self.participant(receiver_id, user_id)
            if (receiver is None or not isinstance(body, dict)
                    or set(body) != {"job_id", "attempt", "status", "error"}
                    or body["job_id"] != self.job["id"] or body["attempt"] != receiver["attempt"]
                    or self.job["phase"] != "receivers"):
                raise UpdateError("stale_update")
            status = body["status"]
            if not isinstance(status, str) or type(body["attempt"]) is not int:
                raise UpdateError("invalid_update")
            allowed = {"pending": {"installing", "declined", "failed", "restart_required"},
                       "installing": {"restart_required", "failed"},
                       "restart_required": {"restart_required"}, "failed": {"failed", "restart_required"}, "declined": {"declined"}}
            if status not in allowed.get(receiver["status"], set()) and status != receiver["status"]:
                raise UpdateError("stale_update")
            # Fixed, non-sensitive error codes only; never accept package output or URLs.
            errors = {None, "download_failed", "checksum_failed", "invalid_package", "install_failed",
                      "install_uncertain", "permission_denied", "update_storage_failed"}
            if not (body["error"] is None or isinstance(body["error"], str)) or body["error"] not in errors:
                raise UpdateError("invalid_update")
            job = copy.deepcopy(self.job)
            next(item for item in job["receivers"] if item["id"] == receiver_id and item["user_id"] == user_id).update(
                status=status, error=body["error"])
            await self.save(job)

    async def retry(self, job_id, user):
        async with self.lock:
            if not self.job or self.job["id"] != job_id or self.job["phase"] == "cancelled":
                raise UpdateError("stale_update")
            job = copy.deepcopy(self.job)
            if job["phase"] == "failed":
                if job["entity_id"] is None:
                    # A receiver-only job must never turn into an HA install.
                    raise UpdateError("hacs_version_changed")
                job["phase"], job["error"] = "ha_installing", None
                await self.save(job)
                self.task = self.hass.async_create_task(self.install_ha(user.id if user is not None else None))
                return
            for receiver in job["receivers"]:
                if receiver["status"] in {"declined", "failed"} and receiver["error"] != "install_uncertain":
                    receiver.update(status="pending", attempt=receiver["attempt"] + 1, error=None)
            await self.save(job)

    def can_cancel_receiver_update(self, job_id, version, receivers):
        """Only withdraw unclaimed receiver-only work for this exact offer."""
        if not self.active:
            return False
        job = self.job
        if not job or job["phase"] in {"completed", "cancelled"}:
            return job_id is None or bool(job and job["id"] == job_id)
        keys = {(r["id"], r["user_id"]) for r in receivers}
        return bool(job["id"] == job_id and job["entity_id"] is None
            and job["phase"] in {"receivers", "failed"} and job["release"]["version"] == version
            and job.get("protocol_version") == PROTOCOL_VERSION
            and all(r["status"] in {"pending", "declined", "failed", "completed"}
                    and r["error"] != "install_uncertain"
                    and (r["status"] == "completed" or (r["id"], r["user_id"]) in keys)
                    for r in job["receivers"]))

    async def cancel_receiver_update(self, job_id, version, receivers):
        """Caller holds lock while persisting the matching repair decision."""
        if not self.can_cancel_receiver_update(job_id, version, receivers):
            raise UpdateError("ignore_unavailable")
        if self.job and self.job["phase"] not in {"completed", "cancelled"}:
            job = copy.deepcopy(self.job)
            job["phase"], job["error"] = "cancelled", None
            await self.save(job)

    async def restart(self, job_id, user):
        async with self.lock:
            await self.refresh()
            if (not self.job or self.job["id"] != job_id or self.job["phase"] != "ha_restart_required"
                    or await self.hass.async_add_executor_job(downloaded_version) != self.job["release"]["version"]):
                raise UpdateError("restart_not_ready")
            if self.restart_task is not None and not self.restart_task.done():
                return
            job = copy.deepcopy(self.job)
            job["error"] = None
            await self.save(job)
            self.restart_task = self.hass.async_create_task(self.restart_ha(user.id if user is not None else None))

    async def restart_ha(self, user_id):
        try:
            await self.hass.services.async_call("homeassistant", "restart", {}, blocking=True,
                                                context=Context(user_id=user_id))
        except HomeAssistantError:
            async with self.lock:
                job = copy.deepcopy(self.job)
                job["error"] = "ha_restart_failed"
                await self.save(job)

    async def close(self):
        self.active = False
        self.listeners.clear()
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
