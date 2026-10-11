"""Authenticated receiver routes and administrator menu configuration."""

import asyncio
import json
import logging
from time import monotonic

from aiohttp import web
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components.http import HomeAssistantView, KEY_HASS_USER
from homeassistant.components import persistent_notification
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError

from .const import BASE, CONF_LANGUAGE, DOMAIN, LANGUAGES
from .enigmaha_protocol import ActionError, ProtocolError, prepare_action, validate_menu
from .enigmaha_protocol.menu import index_nodes, validate_display
from .enigmaha_protocol.compatibility import (
    COMPONENT_HEADER, VERSION_HEADER, RECEIVER_HEADER, VERSION, PROTOCOL_HEADER, PROTOCOL_VERSION,
    peer_status, protocol_version, valid_version, valid_receiver_id,
)
from .enigmaha_protocol.releases import UpdateError
from .icons import IconResolver
from .menus import legacy_menu, receiver_menu, validate_configuration

LIMIT = 1024 * 1024
_LOGGER = logging.getLogger(__name__)


class CompanionRuntime:
    def __init__(self, hass, store, menu, config_entry=None):
        self.hass, self.store, self.menu = hass, store, menu
        self.config_entry = config_entry
        self.lock = asyncio.Lock()
        self.active = True
        self.icons = IconResolver(hass)
        self.receivers = {}
        self.updates = None
        self.repairs = None
        self.editor_status_messages = {}
        self.legacy_notices_cleared = False

    async def async_set_display(self, display):
        """Keep options and published editor APIs on one revisioned menu store."""
        display = validate_display(display)
        async with self.lock:
            if not self.active:
                raise HomeAssistantError("integration_unavailable")
            if display == self.menu["display"]:
                return
            if self.menu["revision"] == 2147483647:
                raise HomeAssistantError("revision_limit")
            config = validate_configuration({**self.menu, "display": display,
                                             "revision": self.menu["revision"] + 1})
            await self.store.async_save(config)
            self.menu = config

    def log_editor_status(self, receivers, updates, language):
        """Log informational status changes at DEBUG without creating notices."""
        if not self.legacy_notices_cleared:
            self.clear_editor_notifications()
        if not _LOGGER.isEnabledFor(logging.DEBUG):
            return
        english = language == "en"
        messages = {
            "version": (f"HA integration {VERSION}, protocol {PROTOCOL_VERSION}. Matching protocols allow different releases."
                        if english else f"HA-Integration {VERSION}, Protokoll {PROTOCOL_VERSION}. Gleiche Protokolle erlauben unterschiedliche Releases."),
            "no_receiver": (("No receiver request in the last 5 minutes. Versions are checked when connecting."
                             if english else "Noch keine Receiver-Anfrage in den letzten 5 Minuten. Die Prüfung erfolgt beim Verbinden.")
                            if not receivers else None),
            "hacs": (("HACS update unavailable. Install EnigmaHA through HACS first and enable its update entity."
                      if english else "HACS-Update nicht verfügbar. EnigmaHA zuerst über HACS installieren und die Update-Entität aktivieren.")
                     if updates is not None and not updates.get("hacs") else None),
        }
        job = updates.get("job") if updates else None
        if job:
            if job["phase"] == "completed":
                version = job["release"]["version"]
                messages[("update", job["id"])] = (
                    f"Release {version}: Completed: HA and all participating receivers are running the same release."
                    if english else f"Release {version}: Abgeschlossen: HA und alle beteiligten Receiver verwenden denselben Release.")
            for receiver in job["receivers"]:
                if receiver["status"] == "completed" and not receiver.get("error"):
                    address = receiver["address"]
                    messages[("receiver_update", job["id"], receiver.get("id"), address)] = (
                        f"Receiver {address}: Running target version"
                        if english else f"Receiver {address}: Zielversion läuft")
        for key, message in messages.items():
            if self.editor_status_messages.get(key) == message:
                continue
            if message:
                _LOGGER.debug("%s", message)
        self.editor_status_messages = messages

    def clear_editor_notifications(self):
        """Remove only the informational notices created by older versions."""
        for key in ("version", "no_receiver", "hacs"):
            persistent_notification.async_dismiss(self.hass, f"{DOMAIN}_{key}")
        self.legacy_notices_cleared = True

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
    return receiver_menu(menu, user.id,
                         lambda entity: user.permissions.check_entity(entity, POLICY_READ),
                         lambda entity: user.permissions.check_entity(entity, POLICY_CONTROL))


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
        menu = filtered_menu(runtime.menu, user)
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
                plan = prepare_action(filtered_menu(runtime.menu, user), command, get_state, can_control)
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
        menu = legacy_menu(runtime.menu)
        if menu is None:
            return self.reply({"error": "configuration_upgrade_required"}, 409)
        return self.reply(menu)

    async def put(self, request):
        runtime, _ = self.access(request, admin=True)
        try:
            menu = validate_menu(await read_json(request))
        except ProtocolError as error:
            return self.reply({"error": "invalid_menu", "detail": str(error)}, 400)
        async with runtime.lock:
            if not runtime.active:
                raise web.HTTPServiceUnavailable()
            if legacy_menu(runtime.menu) is None:
                return self.reply({"error": "configuration_upgrade_required"}, 409)
            if menu["revision"] != runtime.menu["revision"]:
                return self.reply({"error": "stale_menu"}, 409)
            menu["revision"] += 1
            try:
                validate_menu(menu)
            except ProtocolError:
                return self.reply({"error": "revision_limit"}, 409)
            # Failed storage must leave the live menu and revision unchanged.
            try:
                await runtime.store.async_save(validate_configuration(menu))
            except (OSError, HomeAssistantError):
                return self.reply({"error": "storage_failed"}, 500)
            runtime.menu = validate_configuration(menu)
        return self.reply(menu)


class ConfigurationView(CompanionView):
    url, name = BASE + "/configuration", DOMAIN + ":configuration"

    async def get(self, request):
        runtime, _ = self.access(request, admin=True)
        return self.reply(validate_configuration(runtime.menu))

    async def put(self, request):
        runtime, _ = self.access(request, admin=True)
        try:
            config = validate_configuration(await read_json(request))
        except ProtocolError as error:
            return self.reply({"error": "invalid_menu", "detail": str(error)}, 400)
        async with runtime.lock:
            if not runtime.active:
                raise web.HTTPServiceUnavailable()
            if config["revision"] != runtime.menu["revision"]:
                return self.reply({"error": "stale_menu"}, 409)
            if config["revision"] == 2147483647:
                return self.reply({"error": "revision_limit"}, 409)
            config["revision"] += 1
            try:
                await runtime.store.async_save(config)
            except (OSError, HomeAssistantError):
                return self.reply({"error": "storage_failed"}, 500)
            runtime.menu = config
        return self.reply(config)


class UsersView(CompanionView):
    url, name = BASE + "/users", DOMAIN + ":users"

    async def get(self, request):
        self.access(request, admin=True)
        users = await self.hass.auth.async_get_users()
        return self.reply({"users": [{"id": user.id, "name": user.name or ""}
                                     for user in users if user.is_active and not user.system_generated]})


class PreviewView(CompanionView):
    url, name = BASE + "/preview", DOMAIN + ":preview"

    async def post(self, request):
        self.access(request, admin=True)
        body = await read_json(request)
        if (not isinstance(body, dict) or set(body) != {"configuration", "user_id"}
                or not isinstance(body["user_id"], str)):
            return self.reply({"error": "invalid_request"}, 400)
        try:
            config = validate_configuration(body["configuration"])
        except ProtocolError as error:
            return self.reply({"error": "invalid_menu", "detail": str(error)}, 400)
        user = await self.hass.auth.async_get_user(body["user_id"])
        if user is None or not user.is_active or user.system_generated:
            return self.reply({"error": "user_not_found"}, 404)
        return self.reply(filtered_menu(config, user))


class CompatibilityView(CompanionView):
    url, name = BASE + "/compatibility", DOMAIN + ":compatibility"

    async def get(self, request):
        runtime, _ = self.access(request, admin=True)
        # Read the live config entry so options apply without reloading the
        # integration or interrupting receiver requests and update jobs.
        language = runtime.config_entry.options.get(CONF_LANGUAGE) if runtime.config_entry else None
        receivers = runtime.recent_receivers()
        updates = await runtime.updates.snapshot() if runtime.updates else None
        # Logs are shared by HA users, so automatic mode follows
        # HA's system language rather than a particular browser profile.
        notice_language = language
        if language == "auto":
            locale = getattr(getattr(self.hass, "config", None), "language", "de")
            notice_language = str(locale).lower().replace("_", "-").split("-")[0]
        runtime.log_editor_status(receivers, updates, notice_language)
        return self.reply({"version": VERSION, "protocol_version": PROTOCOL_VERSION, "receivers": receivers,
                           "editor_language": language if language in LANGUAGES else None,
                           "updates": updates})


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
    for view in (MenuView, StatesView, ActionsView, ConfigView, ConfigurationView, UsersView,
                 PreviewView, CompatibilityView, UpdateAdminView, ReceiverUpdateView):
        hass.http.register_view(view(hass))
