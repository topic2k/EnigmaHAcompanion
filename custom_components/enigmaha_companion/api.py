"""Authenticated receiver routes and administrator menu configuration."""

import asyncio
import copy
import json
from time import monotonic

from aiohttp import web
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components.http import HomeAssistantView, KEY_HASS_USER
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .const import BASE, DOMAIN
from .enigmaha_protocol import ActionError, ProtocolError, prepare_action, validate_menu
from .enigmaha_protocol.menu import index_nodes
from .enigmaha_protocol.compatibility import (
    COMPONENT_HEADER, VERSION_HEADER, RECEIVER_HEADER, VERSION, PROTOCOL_HEADER, PROTOCOL_VERSION,
    peer_status, protocol_version, valid_version, valid_receiver_id,
)
from .enigmaha_protocol.releases import UpdateError
from .icons import IconResolver

LIMIT = 1024 * 1024


class CompanionRuntime:
    def __init__(self, hass, store, menu):
        self.hass, self.store, self.menu = hass, store, menu
        self.lock = asyncio.Lock()
        self.active = True
        self.icons = IconResolver(hass)
        self.receivers = {}
        self.updates = None
        self.repairs = None

    def recent_receivers(self):
        cutoff = monotonic() - 300
        self.receivers = {key: value for key, value in self.receivers.items()
                          if value["seen"] >= cutoff}
        return [{key: value for key, value in receiver.items() if key not in {"seen", "user_id"}}
                for receiver in self.receivers.values()]

    async def check_receiver(self, request, user):
        self.recent_receivers()
        version = request.headers.get(VERSION_HEADER)
        protocol = request.headers.get(PROTOCOL_HEADER)
        status = peer_status(request.headers.get(COMPONENT_HEADER), version, "receiver", protocol)
        receiver_id = request.headers.get(RECEIVER_HEADER)
        receiver_id = receiver_id if valid_receiver_id(receiver_id) else None
        key = (user.id, receiver_id or request.remote)
        # Bound memory even when an authenticated caller sends many source addresses.
        if key not in self.receivers and len(self.receivers) >= 64:
            del self.receivers[min(self.receivers, key=lambda key: self.receivers[key]["seen"])]
        self.receivers[key] = {"address": request.remote or "?", "id": receiver_id, "user_id": user.id,
                               "version": version if valid_version(version) else None,
                               "protocol_version": protocol_version(protocol, version),
                               "status": status, "seen": monotonic()}
        if self.repairs is not None and receiver_id and status != "unidentified_peer":
            await self.repairs.observe(self.receivers[key])
        return status


def filtered_menu(menu, user):
    result = copy.deepcopy(menu)

    def filter_node(node):
        if node["type"] == "menu":
            node["children"] = [child for child in node["children"] if filter_node(child)]
            return True
        if not user.permissions.check_entity(node["entity_id"], POLICY_READ):
            return False
        if not user.permissions.check_entity(node["entity_id"], POLICY_CONTROL):
            node["actions"] = []
        return True

    filter_node(result["root"])
    return result


async def read_json(request):
    # readexactly-style loops bound chunked requests as well as Content-Length.
    data = bytearray()
    async for chunk in request.content.iter_chunked(16384):
        data.extend(chunk)
        if len(data) > LIMIT:
            raise web.HTTPRequestEntityTooLarge(max_size=LIMIT, actual_size=len(data))
    try:
        return json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise web.HTTPBadRequest(text="invalid_request") from None


class CompanionView(HomeAssistantView):
    requires_auth = True

    def __init__(self, hass):
        self.hass = hass

    def access(self, request, admin=False):
        user = request.get(KEY_HASS_USER)
        if user is None or not user.is_active:
            raise web.HTTPUnauthorized()
        if admin and not user.is_admin:
            raise web.HTTPForbidden()
        runtime = self.hass.data[DOMAIN].get("runtime")
        if runtime is None or not runtime.active:
            raise web.HTTPServiceUnavailable()
        return runtime, user

    def reply(self, data, status=200):
        return self.json(data, status, headers={"Cache-Control": "no-store",
                         COMPONENT_HEADER: "homeassistant", VERSION_HEADER: VERSION,
                         PROTOCOL_HEADER: str(PROTOCOL_VERSION)})

    async def receiver_error(self, runtime, request, user):
        status = await runtime.check_receiver(request, user)
        if status not in {"compatible", "version_mismatch"}:
            return self.reply({"error": status, "version": VERSION, "protocol_version": PROTOCOL_VERSION}, 426)
        return None


class MenuView(CompanionView):
    url, name = BASE + "/menu", DOMAIN + ":menu"

    async def get(self, request):
        runtime, user = self.access(request)
        error = await self.receiver_error(runtime, request, user)
        if error is not None:
            return error
        return self.reply(filtered_menu(runtime.menu, user))


class StatesView(CompanionView):
    url, name = BASE + "/states", DOMAIN + ":states"

    async def get(self, request):
        runtime, user = self.access(request)
        error = await self.receiver_error(runtime, request, user)
        if error is not None:
            return error
        states = {}
        icons = {}
        menu = runtime.menu
        for node in index_nodes(menu).values():
            if node["type"] != "entity" or not user.permissions.check_entity(node["entity_id"], POLICY_READ):
                continue
            if node["entity_id"] in states:
                continue
            state = self.hass.states.get(node["entity_id"])
            if state is not None:
                unit = state.attributes.get("unit_of_measurement")
                states[node["entity_id"]] = {
                    "state": state.state,
                    "unit_of_measurement": str(unit)[:64] if unit is not None else None,
                    "icon": None,
                }
                icon = await runtime.icons.resolve(state)
                if icon:
                    states[node["entity_id"]]["icon"] = icon["name"]
                    icons[icon["name"]] = icon["path"]
        return self.reply({"schema_version": 1, "revision": menu["revision"], "states": states, "icons": icons})


class ActionsView(CompanionView):
    url, name = BASE + "/actions", DOMAIN + ":actions"

    async def post(self, request):
        runtime, user = self.access(request)
        error = await self.receiver_error(runtime, request, user)
        if error is not None:
            return error
        command = await read_json(request)
        async with runtime.lock:
            if not runtime.active:
                raise web.HTTPServiceUnavailable()

            def get_state(entity_id):
                state = self.hass.states.get(entity_id)
                return state.state if state else None

            def can_control(entity_id):
                return (user.permissions.check_entity(entity_id, POLICY_READ)
                        and user.permissions.check_entity(entity_id, POLICY_CONTROL))

            try:
                plan = prepare_action(runtime.menu, command, get_state, can_control)
            except ActionError as error:
                return self.reply({"error": error.code}, error.status)
            try:
                await self.hass.services.async_call(
                    plan["domain"], plan["service"], plan["data"],
                    blocking=True, context=Context(user_id=user.id),
                )
            except HomeAssistantError:
                return self.reply({"error": "service_failed"}, 500)
        return self.reply({"accepted": True})


class ConfigView(CompanionView):
    url, name = BASE + "/config", DOMAIN + ":config"

    async def get(self, request):
        runtime, _ = self.access(request, admin=True)
        return self.reply(runtime.menu)

    async def put(self, request):
        runtime, _ = self.access(request, admin=True)
        try:
            menu = validate_menu(await read_json(request))
        except ProtocolError as error:
            return self.reply({"error": "invalid_menu", "detail": str(error)}, 400)
        async with runtime.lock:
            if not runtime.active:
                raise web.HTTPServiceUnavailable()
            if menu["revision"] != runtime.menu["revision"]:
                return self.reply({"error": "stale_menu"}, 409)
            menu["revision"] += 1
            try:
                validate_menu(menu)
            except ProtocolError:
                return self.reply({"error": "revision_limit"}, 409)
            # Failed storage must leave the live menu and revision unchanged.
            try:
                await runtime.store.async_save(menu)
            except (OSError, HomeAssistantError):
                return self.reply({"error": "storage_failed"}, 500)
            runtime.menu = menu
        return self.reply(menu)


class CompatibilityView(CompanionView):
    url, name = BASE + "/compatibility", DOMAIN + ":compatibility"

    async def get(self, request):
        runtime, _ = self.access(request, admin=True)
        return self.reply({"version": VERSION, "protocol_version": PROTOCOL_VERSION, "receivers": runtime.recent_receivers(),
                           "updates": await runtime.updates.snapshot() if runtime.updates else None})


class UpdateAdminView(CompanionView):
    url, name = BASE + "/updates", DOMAIN + ":updates"

    async def post(self, request):
        runtime, user = self.access(request, admin=True)
        if runtime.updates is None:
            raise web.HTTPServiceUnavailable()
        body = await read_json(request)
        if not isinstance(body, dict):
            return self.reply({"error": "invalid_update"}, 400)
        try:
            action = body.get("action")
            if action == "check" and set(body) == {"action"}:
                await runtime.updates.check()
            elif action == "start" and set(body) == {"action", "candidate_id", "receiver_ids"}:
                runtime.recent_receivers()
                ids = body["receiver_ids"]
                if (not isinstance(ids, list) or not ids or any(not valid_receiver_id(value) for value in ids)
                        or len(set(ids)) != len(ids)):
                    raise UpdateError("receiver_update_unavailable")
                receivers = [receiver for receiver in runtime.receivers.values() if receiver["id"] in ids]
                if len(receivers) != len(ids):
                    raise UpdateError("receiver_update_unavailable")
                await runtime.updates.start(body["candidate_id"], receivers, user)
            elif action == "retry" and set(body) == {"action", "job_id"}:
                await runtime.updates.retry(body["job_id"], user)
            elif action == "restart" and set(body) == {"action", "job_id"}:
                await runtime.updates.restart(body["job_id"], user)
            else:
                raise UpdateError("invalid_update")
        except UpdateError as error:
            return self.reply({"error": error.code}, 409)
        return self.reply(await runtime.updates.snapshot())


class ReceiverUpdateView(CompanionView):
    url, name = BASE + "/receiver_update", DOMAIN + ":receiver_update"

    async def receiver_access(self, request):
        runtime, user = self.access(request)
        receiver_id = request.headers.get(RECEIVER_HEADER)
        if (request.headers.get(COMPONENT_HEADER) != "receiver" or not valid_receiver_id(receiver_id)
                or not valid_version(request.headers.get(VERSION_HEADER))):
            raise web.HTTPBadRequest()
        if runtime.updates is None:
            raise web.HTTPServiceUnavailable()
        await runtime.check_receiver(request, user)
        return runtime, user, receiver_id

    async def get(self, request):
        runtime, user, receiver_id = await self.receiver_access(request)
        try:
            result = await runtime.updates.receiver_plan(receiver_id, user.id, request.headers[VERSION_HEADER],
                protocol_version(request.headers.get(PROTOCOL_HEADER), request.headers[VERSION_HEADER]))
        except UpdateError as error:
            return self.reply({"error": error.code}, 409)
        return self.reply(result)

    async def post(self, request):
        runtime, user, receiver_id = await self.receiver_access(request)
        try:
            await runtime.updates.report(receiver_id, user.id, await read_json(request))
        except UpdateError as error:
            return self.reply({"error": error.code}, 409)
        return self.reply({"accepted": True})


def register_views(hass):
    for view in (MenuView, StatesView, ActionsView, ConfigView, CompatibilityView, UpdateAdminView, ReceiverUpdateView):
        hass.http.register_view(view(hass))
