"""Durable protocol problems and actionable issues backed by the update job."""

import asyncio
import copy

from homeassistant.helpers import issue_registry as ir
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .enigmaha_protocol.compatibility import PROTOCOL_VERSION, valid_receiver_id, valid_version
from .enigmaha_protocol.releases import UpdateError

PROTOCOL_ISSUE = "protocol_mismatch"
UPDATE_ISSUE = "update_incomplete"


class RepairCoordinator:
    def __init__(self, hass, store, runtime, saved=None):
        self.hass, self.store, self.runtime = hass, store, runtime
        self.lock = asyncio.Lock()
        self.active = True
        if saved is not None and not isinstance(saved, dict):
            raise ValueError("invalid stored repair state")
        self.receivers = (saved or {}).get("receivers", [])
        self.job_id = (saved or {}).get("job_id")
        if (not isinstance(self.receivers, list) or len(self.receivers) > 64
                or (self.job_id is not None and not valid_receiver_id(self.job_id))):
            raise ValueError("invalid stored repair state")
        for receiver in self.receivers:
            if (not isinstance(receiver, dict) or not valid_receiver_id(receiver.get("id"))
                    or not valid_version(receiver.get("version")) or not isinstance(receiver.get("user_id"), str)
                    or not isinstance(receiver.get("address"), str) or receiver.get("status") != "protocol_mismatch"
                    or (receiver.get("protocol_version") is not None and
                        (type(receiver["protocol_version"]) is not int or not 1 <= receiver["protocol_version"] <= 99999))):
                raise ValueError("invalid stored repair receiver")

    async def _save(self, receivers, job_id):
        try:
            await self.store.async_save({"receivers": receivers, "job_id": job_id})
        except (OSError, HomeAssistantError):
            raise UpdateError("update_storage_failed") from None
        self.receivers, self.job_id = receivers, job_id

    async def observe(self, receiver):
        async with self.lock:
            if not self.active:
                return
            key = (receiver["id"], receiver["user_id"])
            records = copy.deepcopy(self.receivers)
            index = next((i for i, record in enumerate(records) if (record["id"], record["user_id"]) == key), None)
            if receiver["status"] == "protocol_mismatch":
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

    async def bind_job(self, job_id):
        async with self.lock:
            await self._save(copy.deepcopy(self.receivers), job_id)
            self._issues()

    async def sync(self):
        async with self.lock:
            if not self.active:
                return
            job = self.runtime.updates.job
            receivers = [r for r in self.receivers if r["protocol_version"] != PROTOCOL_VERSION]
            job_id = self.job_id
            if job_id and job and job["id"] == job_id and job["phase"] == "completed":
                job_id = None
            if receivers != self.receivers or job_id != self.job_id:
                await self._save(copy.deepcopy(receivers), job_id)
            self._issues()

    def _issues(self):
        job = self.runtime.updates.job
        continuing = bool(self.job_id and job and job["id"] == self.job_id and job["phase"] != "completed")
        if self.receivers or continuing:
            peers = ", ".join(f'{r["address"]}: {r["version"]} / {r["protocol_version"] or "?"}' for r in self.receivers)
            ir.async_create_issue(self.hass, DOMAIN, PROTOCOL_ISSUE, is_fixable=True, is_persistent=True,
                severity=ir.IssueSeverity.ERROR, translation_key=PROTOCOL_ISSUE,
                translation_placeholders={"protocol": str(PROTOCOL_VERSION), "receivers": peers or "—"})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, PROTOCOL_ISSUE)
        if job and (job["phase"] in {"failed", "ha_restart_required"}
                    or any(r["status"] == "failed" for r in job["receivers"])):
            ir.async_create_issue(self.hass, DOMAIN, UPDATE_ISSUE, is_fixable=True, is_persistent=True,
                severity=ir.IssueSeverity.ERROR, translation_key=UPDATE_ISSUE,
                translation_placeholders={"version": job["release"]["version"]})
        else:
            ir.async_delete_issue(self.hass, DOMAIN, UPDATE_ISSUE)

    def close(self):
        self.active = False
        for issue in (PROTOCOL_ISSUE, UPDATE_ISSUE):
            ir.async_delete_issue(self.hass, DOMAIN, issue)
