"""Authenticated receiver routes and administrator menu configuration."""

import asyncio
import copy
import json

from aiohttp import web
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components.http import HomeAssistantView, KEY_HASS_USER
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .const import BASE, DOMAIN
from .enigmaha_protocol import ActionError, ProtocolError, prepare_action, validate_menu
from .enigmaha_protocol.menu import index_nodes
from .icons import IconResolver

LIMIT = 1024 * 1024


class CompanionRuntime:
    def __init__(self, hass, store, menu):
        self.hass, self.store, self.menu = hass, store, menu
        self.lock = asyncio.Lock()
        self.active = True
        self.icons = IconResolver(hass)


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
        return self.json(data, status, headers={"Cache-Control": "no-store"})


class MenuView(CompanionView):
    url, name = BASE + "/menu", DOMAIN + ":menu"

    async def get(self, request):
        runtime, user = self.access(request)
        return self.reply(filtered_menu(runtime.menu, user))


class StatesView(CompanionView):
    url, name = BASE + "/states", DOMAIN + ":states"

    async def get(self, request):
        runtime, user = self.access(request)
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


def register_views(hass):
    for view in (MenuView, StatesView, ActionsView, ConfigView):
        hass.http.register_view(view(hass))
