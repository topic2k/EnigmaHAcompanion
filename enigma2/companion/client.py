"""Blocking HTTP client: Enigma2 adapters MUST run calls in a worker thread."""

import json
from uuid import uuid4
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from enigmaha_protocol.menu import ProtocolError, validate_menu
from enigmaha_protocol.icons import valid_icon
from enigmaha_protocol.compatibility import COMPONENT_HEADER, VERSION_HEADER, RECEIVER_HEADER, VERSION, PROTOCOL_HEADER, PROTOCOL_VERSION, peer_status, protocol_version, valid_version, valid_receiver_id
from enigmaha_protocol.releases import UpdateError, validate_release

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
API_PATH = "/api/enigmaha_companion/v1"


class ClientError(Exception):
    def __init__(self, code, status=None, peer_version=None, peer_protocol=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.peer_version = peer_version
        self.peer_protocol = peer_protocol


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a receiver's bearer token to another location.
        return None


class CompanionClient:
    def __init__(self, base_url, token, timeout=5, receiver_id=None):
        parts = urlsplit(base_url)
        if (parts.scheme not in {"http", "https"} or not parts.hostname
                or parts.username is not None or parts.password is not None
                or parts.query or parts.fragment or parts.path not in {"", "/"}
                or any(ord(char) <= 32 for char in base_url)):
            raise ValueError("expected HA origin, e.g. https://ha.example.org")
        if not isinstance(token, str) or not token or any(ord(c) <= 32 or ord(c) > 126 for c in token):
            raise ValueError("invalid token")
        if not 0 < timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds")
        self._base_url = base_url.rstrip("/") + API_PATH
        self._token = token
        self._timeout = timeout
        self._opener = build_opener(_NoRedirect())
        self.receiver_id = receiver_id or uuid4().hex
        if not valid_receiver_id(self.receiver_id):
            raise ValueError("invalid receiver ID")
        self.peer_version = self.peer_protocol = None

    def _check_peer(self, headers, allow_mismatch=False):
        version = headers.get(VERSION_HEADER)
        protocol = protocol_version(headers.get(PROTOCOL_HEADER), version)
        status = peer_status(headers.get(COMPONENT_HEADER), version, "homeassistant", headers.get(PROTOCOL_HEADER))
        if status not in {"compatible", "version_mismatch"} and not (allow_mismatch and status == "protocol_mismatch"):
            raise ClientError(status, peer_version=version if valid_version(version) else None, peer_protocol=protocol)
        self.peer_version, self.peer_protocol = version, protocol

    def _request(self, method, path, body=None, allow_mismatch=False):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self._base_url + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json", "Content-Type": "application/json",
            COMPONENT_HEADER: "receiver", VERSION_HEADER: VERSION,
            PROTOCOL_HEADER: str(PROTOCOL_VERSION),
            RECEIVER_HEADER: self.receiver_id,
        })
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                self._check_peer(response.headers, allow_mismatch)
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            status = error.code
            headers = error.headers
            error.close()
            if status == 426:
                self._check_peer(headers)
                if self.peer_version != VERSION:
                    raise ClientError("legacy_version_mismatch", status, self.peer_version, self.peer_protocol)
                raise ClientError("unidentified_peer", status)
            code = {401: "unauthorized", 403: "forbidden", 404: "not_found",
                    409: "conflict"}.get(status, "http_error")
            raise ClientError(code, status) from None
        except (URLError, TimeoutError, OSError, HTTPException):
            # Error URLs, server messages and token values never escape to UI.
            raise ClientError("connection_failed") from None
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ClientError("response_too_large")
        try:
            result = json.loads(payload.decode("utf-8"))
        except (UnicodeError, ValueError, RecursionError):
            raise ClientError("invalid_response") from None
        if not isinstance(result, dict):
            raise ClientError("invalid_response")
        return result

    def get_menu(self):
        try:
            return validate_menu(self._request("GET", "/menu"))
        except ProtocolError:
            raise ClientError("invalid_menu") from None

    def get_info(self):
        try:
            result = self._request("GET", "/info")
        except ClientError as error:
            if error.code == "not_found":  # Older integrations have no info route.
                return None
            raise
        counts = {"menus", "submenus", "lights", "switches", "sensors", "other_entities"}
        if (set(result) != counts | {"user_name"}
                or (result["user_name"] is not None and
                    (not isinstance(result["user_name"], str) or len(result["user_name"]) > 255))
                or any(type(result[key]) is not int or not 0 <= result[key] <= 500 for key in counts)):
            raise ClientError("invalid_response")
        return result

    def get_update(self):
        result = self._request("GET", "/receiver_update", allow_mismatch=True)
        if set(result) != {"job"}:
            raise ClientError("invalid_response")
        job = result["job"]
        if job is None:
            return None
        if (not isinstance(job, dict) or set(job) != {"id", "release", "status", "attempt"}
                or not valid_receiver_id(job["id"]) or type(job["attempt"]) is not int or job["attempt"] < 1
                or not isinstance(job["status"], str)
                or job["status"] not in {"pending", "installing", "restart_required", "completed", "declined", "failed"}):
            raise ClientError("invalid_response")
        try:
            validate_release(job["release"])
        except UpdateError:
            raise ClientError("invalid_response") from None
        return job

    def report_update(self, job, status, error=None):
        result = self._request("POST", "/receiver_update", {"job_id": job["id"], "attempt": job["attempt"],
                               "status": status, "error": error}, allow_mismatch=True)
        if result != {"accepted": True} or type(result.get("accepted")) is not bool:
            raise ClientError("invalid_response")
        return result

    def get_states(self, menu):
        from enigmaha_protocol.menu import index_nodes
        menu = validate_menu(menu)
        result = self._request("GET", "/states")
        if (set(result) != {"schema_version", "revision", "states", "icons"}
                or type(result.get("schema_version")) is not int or result["schema_version"] != 1
                or type(result.get("revision")) is not int):
            raise ClientError("invalid_response")
        if result["revision"] != menu["revision"]:
            raise ClientError("stale_menu")
        states = result["states"]
        if not isinstance(states, dict):
            raise ClientError("invalid_response")
        allowed = {node["entity_id"] for node in index_nodes(menu).values() if node["type"] == "entity"}
        if not set(states).issubset(allowed):
            raise ClientError("invalid_response")
        icons = result["icons"]
        if (not isinstance(icons, dict) or len(icons) > len(allowed)
                or any(not valid_icon({"name": name, "path": path}) for name, path in icons.items())):
            raise ClientError("invalid_response")
        for value in states.values():
            if (not isinstance(value, dict) or set(value) != {"state", "unit_of_measurement", "icon"}
                    or not isinstance(value["state"], str) or len(value["state"]) > 255
                    or (value["unit_of_measurement"] is not None and
                        (not isinstance(value["unit_of_measurement"], str) or len(value["unit_of_measurement"]) > 64))):
                raise ClientError("invalid_response")
            name = value["icon"]
            if name is not None and (not isinstance(name, str) or name not in icons or value["state"] not in {"on", "off"}):
                raise ClientError("invalid_response")
            value["icon"] = {"name": name, "path": icons[name]} if name is not None else None
        return states

    def execute(self, command):
        """Send once only. A lost reply must never automatically repeat toggle."""
        result = self._request("POST", "/actions", command)
        if result != {"accepted": True} or type(result.get("accepted")) is not bool:
            raise ClientError("invalid_response")
        return result
