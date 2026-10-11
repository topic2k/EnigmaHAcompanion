"""Server-side action planning. This module never calls HA services itself."""

from .menu import ProtocolError, _keys, index_nodes, validate_menu


class ActionError(ValueError):
    def __init__(self, code, status):
        super().__init__(code)
        self.code = code
        self.status = status


def prepare_action(document, request, get_state, can_control):
    """Resolve a command against the current server menu and user permissions.

    get_state(entity_id) returns a HA state string or None for a missing entity.
    can_control(entity_id) must use the authenticated user's HA permissions.
    Authentication happens in the future HTTP adapter before this function.
    """
    menu = validate_menu(document)
    try:
        _keys(request, ["schema_version", "revision", "entry_id", "action"], [], "command")
        if type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ProtocolError("unsupported version")
        if type(request["revision"]) is not int or request["revision"] < 1:
            raise ProtocolError("invalid revision")
        if not isinstance(request["entry_id"], str) or request["action"] != "toggle":
            raise ProtocolError("invalid action")
    except ProtocolError:
        raise ActionError("invalid_request", 400) from None
    if request["revision"] != menu["revision"]:
        raise ActionError("stale_menu", 409)
    node = index_nodes(menu).get(request["entry_id"])
    if node is None or node["type"] != "entity":
        raise ActionError("entry_not_found", 404)
    if request["action"] not in node["actions"]:
        raise ActionError("action_not_allowed", 403)
    entity_id = node["entity_id"]
    if not can_control(entity_id):
        raise ActionError("forbidden", 403)
    state = get_state(entity_id)
    if state not in {"on", "off"}:
        raise ActionError("entity_unavailable", 409)
    return {"domain": entity_id.split(".", 1)[0], "service": "toggle",
            "data": {"entity_id": entity_id}}
