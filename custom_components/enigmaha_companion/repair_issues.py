"""Durable protocol problems and actionable issues backed by the update job."""

import asyncio
import copy

from homeassistant.helpers import issue_registry as ir
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .enigmaha_protocol.compatibility import VERSION, PROTOCOL_VERSION, valid_receiver_id, valid_version
from .enigmaha_protocol.releases import UpdateError, version_tuple

PROTOCOL_ISSUE = "protocol_mismatch"
UPDATE_ISSUE = "update_incomplete"
RECEIVER_UPDATE_ISSUE = "receiver_update_available"


class RepairCoordinator:
    def __init__(self, hass, store, runtime, saved=None):
        self.hass, self.store, self.runtime = hass, store, runtime
        self.lock = asyncio.Lock()
        self.active = True
        if saved is not None and not isinstance(saved, dict):
            raise ValueError("invalid stored repair state")
        self.receivers = (saved or {}).get("receivers", [])
        self.job_id = (saved or {}).get("job_id")
        self.job_issue = (saved or {}).get("job_issue", PROTOCOL_ISSUE)
        if (not isinstance(self.receivers, list) or len(self.receivers) > 64
                or (self.job_id is not None and not valid_receiver_id(self.job_id))
                or self.job_issue not in {PROTOCOL_ISSUE, RECEIVER_UPDATE_ISSUE}):
            raise ValueError("invalid stored repair state")
        for receiver in self.receivers:
            if (not isinstance(receiver, dict) or not valid_receiver_id(receiver.get("id"))
                    or not valid_version(receiver.get("version")) or not isinstance(receiver.get("user_id"), str)
                    or not isinstance(receiver.get("address"), str)
                    or receiver.get("status") not in {"protocol_mismatch", "version_mismatch"}
                    or (receiver.get("protocol_version") is not None and
                        (type(receiver["protocol_version"]) is not int or not 1 <= receiver["protocol_version"] <= 99999))):
                raise ValueError("invalid stored repair receiver")

    async def _save(self, receivers, job_id, job_issue=None):
        job_issue = self.job_issue if job_issue is None else job_issue
        try:
            await self.store.async_save({"receivers": receivers, "job_id": job_id, "job_issue": job_issue})
        except (OSError, HomeAssistantError):
            raise UpdateError("update_storage_failed") from None
        self.receivers, self.job_id = receivers, job_id
        self.job_issue = job_issue

    def receivers_for_issue(self, issue):
        if issue == RECEIVER_UPDATE_ISSUE:
            return [r for r in self.receivers if r["status"] == "version_mismatch"]
        return [r for r in self.receivers if r["status"] == "protocol_mismatch"]

    async def observe(self, receiver):
        async with self.lock:
            if not self.active:
                return
            key = (receiver["id"], receiver["user_id"])
            records = copy.deepcopy(self.receivers)
            index = next((i for i, record in enumerate(records) if (record["id"], record["user_id"]) == key), None)
            if (receiver["status"] == "protocol_mismatch"
                    or (receiver["status"] == "version_mismatch"
                        and version_tuple(receiver["version"]) < version_tuple(VERSION))):
                record = {field: receiver[field] for field in ("id", "user_id", "address", "version", "protocol_version", "status")}
                if index is not None:
                    records[index] = record
                elif len(records) < 64:
                    records.append(record)
            elif index is not None:
                del records[index]
            if records != self.receivers:
                await self._save(records, self.job_id)
            self._issues()

    async def bind_job(self, job_id, issue=PROTOCOL_ISSUE):
        async with self.lock:
            await self._save(copy.deepcopy(self.receivers), job_id, issue)
            self._issues()

    async def sync(self):
        async with self.lock:
            if not self.active:
                return
            job = self.runtime.updates.job
            receivers = []
            for receiver in self.receivers:
                receiver = dict(receiver)
                if receiver["protocol_version"] != PROTOCOL_VERSION:
                    receiver["status"] = "protocol_mismatch"
                elif version_tuple(receiver["version"]) < version_tuple(VERSION):
                    receiver["status"] = "version_mismatch"
                else:
                    continue
                receivers.append(receiver)
            job_id = self.job_id
            if job_id and job and job["id"] == job_id and job["phase"] == "completed":
                job_id = None
            if receivers != self.receivers or job_id != self.job_id:
                await self._save(copy.deepcopy(receivers), job_id)
            self._issues()

    def _issues(self):
        job = self.runtime.updates.job
        continuing = bool(self.job_id and job and job["id"] == self.job_id and job["phase"] != "completed")
        protocol_receivers = self.receivers_for_issue(PROTOCOL_ISSUE)
        if protocol_receivers or (continuing and self.job_issue == PROTOCOL_ISSUE):
            peers = ", ".join(f'{r["address"]}: {r["version"]} / {r["protocol_version"] or "?"}' for r in protocol_receivers)
            ir.async_create_issue(self.hass, DOMAIN, PROTOCOL_ISSUE, is_fixable=True, is_persistent=True,
                severity=ir.IssueSeverity.ERROR, translation_key=PROTOCOL_ISSUE,
                translation_placeholders={"protocol": str(PROTOCOL_VERSION), "receivers": peers or "—"})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, PROTOCOL_ISSUE)
        outdated = self.receivers_for_issue(RECEIVER_UPDATE_ISSUE)
        if outdated or (continuing and self.job_issue == RECEIVER_UPDATE_ISSUE):
            peers = ", ".join(f'{r["address"]}: {r["version"]}' for r in outdated)
            ir.async_create_issue(self.hass, DOMAIN, RECEIVER_UPDATE_ISSUE, is_fixable=True, is_persistent=True,
                severity=ir.IssueSeverity.WARNING, translation_key=RECEIVER_UPDATE_ISSUE,
                translation_placeholders={"version": VERSION, "receivers": peers or "—"})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, RECEIVER_UPDATE_ISSUE)
        if job and (job["phase"] in {"failed", "ha_restart_required"}
                    or any(r["status"] == "failed" for r in job["receivers"])):
            ir.async_create_issue(self.hass, DOMAIN, UPDATE_ISSUE, is_fixable=True, is_persistent=True,
                severity=ir.IssueSeverity.ERROR, translation_key=UPDATE_ISSUE,
                translation_placeholders={"version": job["release"]["version"]})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, UPDATE_ISSUE)

    def close(self):
        self.active = False
        for issue in (PROTOCOL_ISSUE, UPDATE_ISSUE, RECEIVER_UPDATE_ISSUE):
            ir.async_delete_issue(self.hass, DOMAIN, issue)
