"""Native repair wizard; all installation work belongs to UpdateManager."""

import asyncio
import copy

import probatio

from homeassistant.components.repairs import RepairsFlow

from .const import DOMAIN
from .enigmaha_protocol.releases import UpdateError
from .repair_issues import PROTOCOL_ISSUE, UPDATE_ISSUE


class CompanionRepairFlow(RepairsFlow):
    def __init__(self):
        super().__init__()
        self.candidate = None
        self.poll_task = None
        self.job_id = None

    def runtime(self):
        runtime = self.hass.data.get(DOMAIN, {}).get("runtime")
        return runtime if runtime and runtime.active else None

    def form(self, step, job=None, error=None):
        return self.async_show_form(step_id=step, data_schema=probatio.Schema({}),
            description_placeholders={"version": job["release"]["version"] if job else "—",
                "receivers": ", ".join(r["address"] for r in (job or {}).get("receivers", [])) or "—"},
            errors={"base": error} if error else {})

    async def async_step_init(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        try:
            job = (await runtime.updates.snapshot())["job"]
        except UpdateError as error:
            return self.form("check", error=error.code)
        if job and job["phase"] != "completed":
            self.job_id = job["id"]
            return await self.async_step_resume()
        if not runtime.repairs.receivers:
            return self.async_create_entry(title="", data={})
        try:
            await runtime.updates.check()
        except UpdateError as error:
            return self.form("check", error=error.code)
        self.candidate = copy.deepcopy(runtime.updates.candidate)
        return await self.async_step_confirm()

    async def async_step_check(self, user_input=None):
        return await self.async_step_init()

    async def async_step_confirm(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        if self.candidate is None:
            return await self.async_step_init()
        peers = copy.deepcopy(runtime.repairs.receivers)
        if not peers:
            return self.async_create_entry(title="", data={})
        error = None
        if user_input is not None:
            try:
                # HA's native repairs endpoints require an administrator. They do
                # not pass a user_id to flows; use the system service context,
                # never guess an owner or accept an actor from submitted data.
                await runtime.updates.start(self.candidate["id"], peers, None)
                self.job_id = runtime.updates.job["id"]
                await runtime.repairs.bind_job(self.job_id)
                return await self.async_step_resume()
            except UpdateError as caught:
                if caught.code == "release_check_required":
                    self.candidate = None
                    return await self.async_step_init()
                error = caught.code
        return self.form("confirm", {"release": self.candidate["release"], "receivers": peers}, error)

    async def async_step_resume(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        try:
            job = (await runtime.updates.snapshot())["job"]
        except UpdateError as error:
            return self.form("check", error=error.code)
        if not job or (self.job_id and job["id"] != self.job_id):
            return self.async_abort(reason="stale_update")
        self.job_id = job["id"]
        if job["phase"] == "completed":
            if runtime.repairs.receivers:
                return await self.async_step_init()
            return self.async_create_entry(title="", data={})
        if any(r["error"] == "install_uncertain" for r in job["receivers"]):
            return self.form("manual", job)
        if job["phase"] == "ha_restart_required":
            return self.form("restart", job)
        if job["phase"] == "failed" or any(r["status"] in {"failed", "declined"} for r in job["receivers"]):
            return self.form("retry", job)
        return await self.async_step_wait()

    async def async_step_wait(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        if self.poll_task is not None and self.poll_task.done():
            # Retrieve observer failures and present the durable job again.
            # Installation itself always belongs to the independent coordinator.
            if not self.poll_task.cancelled():
                self.poll_task.exception()
            self.poll_task = None
            return self.async_show_progress_done(next_step_id="resume")
        try:
            job = (await runtime.updates.snapshot())["job"]
        except UpdateError as error:
            return self.form("check", error=error.code)
        if self.poll_task is None:
            async def changed():
                while runtime.active:
                    await asyncio.sleep(2)
                    if (await runtime.updates.snapshot())["job"] != job:
                        return
            # Cancelling the wizard cancels only this observer, not installation.
            self.poll_task = self.hass.async_create_task(changed())
        return self.async_show_progress(step_id="wait", progress_action=job["phase"],
            progress_task=self.poll_task,
            description_placeholders={"version": job["release"]["version"],
                "receivers": ", ".join(r["address"] for r in job["receivers"])})

    async def async_step_retry(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        if user_input is not None:
            try:
                await runtime.updates.retry(self.job_id, None)
            except UpdateError as error:
                return self.form("retry", runtime.updates.public_job(), error.code)
        return await self.async_step_resume()

    async def async_step_restart(self, user_input=None):
        runtime = self.runtime()
        if runtime is None:
            return self.async_abort(reason="integration_unavailable")
        if user_input is not None:
            try:
                await runtime.updates.restart(self.job_id, None)
            except UpdateError as error:
                return self.form("restart", runtime.updates.public_job(), error.code)
            # The persisted issue is cleared by observed completion after restart.
            return self.async_abort(reason="restart_requested")
        return await self.async_step_resume()

    async def async_step_manual(self, user_input=None):
        return await self.async_step_resume()


async def async_create_fix_flow(hass, issue_id, data):
    if issue_id not in {PROTOCOL_ISSUE, UPDATE_ISSUE}:
        raise ValueError("unknown EnigmaHA repair issue")
    return CompanionRepairFlow()
