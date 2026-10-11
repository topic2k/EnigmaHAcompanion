"""Blocking HTTP client: Enigma2 adapters MUST run calls in a worker thread."""

import json
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from enigmaha_protocol.menu import ProtocolError, validate_menu
from enigmaha_protocol.icons import valid_icon

MAX_RESPONSE_BYTES = 8 * 1024 * 1024
API_PATH = "/api/enigmaha_companion/v1"


class ClientError(Exception):
    def __init__(self, code, status=None):
        super().__init__(code)
        self.code = code
        self.status = status


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a receiver's bearer token to another location.
        return None


class CompanionClient:
    def __init__(self, base_url, token, timeout=5):
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

    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self._base_url + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self._token,
            "Accept": "application/json", "Content-Type": "application/json",
        })
        try:
            with self._opener.open(request, timeout=self._timeout) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            status = error.code
            error.close()
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
