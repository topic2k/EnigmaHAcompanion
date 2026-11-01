"""Server-side action planning. This module never calls HA services itself."""

from .menu import (SELECT_ACTION, SELECT_DOMAINS, ProtocolError, _keys, _text,
                   index_nodes, validate_menu, validate_select_options)


class ActionError(ValueError):
    def __init__(self, code, status):
        super().__init__(code)
        self.code = code
        self.status = status


def prepare_action(document, request, get_state, can_control, can_dim=None, get_options=None):
    """Resolve a command against the current server menu and user permissions.

    get_state(entity_id) returns a HA state string or None for a missing entity.
    can_control(entity_id) must use the authenticated user's HA permissions.
    Authentication happens in the future HTTP adapter before this function.
    """
    menu = validate_menu(document)
    try:
        _keys(request, ["schema_version", "revision", "entry_id", "action"], ["option", "options"], "command")
        if type(request["schema_version"]) is not int or request["schema_version"] != 1:
            raise ProtocolError("unsupported version")
        if type(request["revision"]) is not int or request["revision"] < 1:
            raise ProtocolError("invalid revision")
        if (not isinstance(request["entry_id"], str) or not isinstance(request["action"], str)
                or request["action"] not in {"toggle", "dim_up", "dim_down", SELECT_ACTION}):
            raise ProtocolError("invalid action")
        if request["action"] == SELECT_ACTION:
            if "option" not in request or "options" not in request:
                raise ProtocolError("select_option requires option and options")
            _text(request["option"], 255, "option")
            validate_select_options(request["options"])
        elif "option" in request or "options" in request:
            raise ProtocolError("select fields require select_option")
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
    if request["action"] == SELECT_ACTION:
        if entity_id.split(".", 1)[0] not in SELECT_DOMAINS:
            raise ActionError("entity_not_supported", 409)
        offered_options = node.get("options")
        if not offered_options or request["options"] != offered_options:
            raise ActionError("stale_options", 409)
        if get_options is None:
            raise ActionError("entity_not_supported", 409)
        try:
            current_options = validate_select_options(get_options(entity_id))
        except ProtocolError:
            raise ActionError("entity_unavailable", 409) from None
        if current_options != offered_options:
            raise ActionError("stale_options", 409)
        if state is None or state in {"unknown", "unavailable"}:
            raise ActionError("entity_unavailable", 409)
        if request["option"] not in current_options:
            raise ActionError("option_not_available", 409)
        return {"domain": entity_id.split(".", 1)[0], "service": SELECT_ACTION,
                "data": {"entity_id": entity_id, "option": request["option"]}}
    if state not in {"on", "off"}:
        raise ActionError("entity_unavailable", 409)
    if request["action"] in {"dim_up", "dim_down"}:
        if entity_id.split(".", 1)[0] != "light" or can_dim is None or not can_dim(entity_id):
            raise ActionError("entity_not_supported", 409)
        step = node.get("brightness_step_pct", 10)
        if request["action"] == "dim_down":
            step = -step
        return {"domain": "light", "service": "turn_on",
                "data": {"entity_id": entity_id, "brightness_step_pct": step}}
    return {"domain": entity_id.split(".", 1)[0], "service": "toggle",
            "data": {"entity_id": entity_id}}
