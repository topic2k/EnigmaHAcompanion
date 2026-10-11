"""Validate and detach untrusted JSON menu definitions."""

import copy
import re

ID = re.compile(r"[a-zA-Z0-9_-]{1,64}\Z")
ENTITY = re.compile(r"[a-z_][a-z0-9_]*\.[a-z0-9_]+\Z")
MAX_DEPTH = 8
MAX_NODES = 500
TOGGLE_DOMAINS = {"light", "switch", "input_boolean"}


class ProtocolError(ValueError):
    """Invalid or unsupported protocol document."""


def _keys(value, required, optional, path):
    if not isinstance(value, dict):
        raise ProtocolError("{}: expected object".format(path))
    missing = set(required) - set(value)
    extra = set(value) - set(required) - set(optional)
    if missing or extra:
        raise ProtocolError("{}: missing or unsupported fields".format(path))


def _integer(value, minimum, maximum, path):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ProtocolError("{}: expected integer {}..{}".format(path, minimum, maximum))


def _text(value, maximum, path):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ProtocolError("{}: invalid text".format(path))
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ProtocolError("{}: control characters forbidden".format(path))


def validate_display(value):
    _keys(value, ["font_family", "font_size"], [], "display")
    _text(value["font_family"], 64, "font_family")
    _integer(value["font_size"], 16, 64, "font_size")
    return dict(value)


def validate_menu(document):
    """Return an independent validated copy; reject unknown fields/version.

    Limits are checked before copying so malformed deep input cannot cause a
    recursive copy failure. The transport must also limit incoming bytes.
    """
    _keys(document, ["schema_version", "revision", "display", "root"], [], "menu")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise ProtocolError("unsupported schema_version")
    _integer(document["revision"], 1, 2147483647, "revision")
    validate_display(document["display"])
    seen = set()
    pending = [(document["root"], 0)]
    if not isinstance(document["root"], dict) or document["root"].get("type") != "menu":
        raise ProtocolError("root must be a menu")
    while pending:
        node, depth = pending.pop()
        if depth > MAX_DEPTH or len(seen) >= MAX_NODES:
            raise ProtocolError("menu size or nesting limit exceeded")
        if not isinstance(node, dict):
            raise ProtocolError("entry must be an object")
        kind = node.get("type")
        if kind == "menu":
            _keys(node, ["type", "id", "label", "children"], [], "menu node")
            if not isinstance(node["children"], list):
                raise ProtocolError("children must be an array")
            if len(node["children"]) > MAX_NODES:
                raise ProtocolError("too many children")
            pending.extend((child, depth + 1) for child in node["children"])
        elif kind == "entity":
            _keys(node, ["type", "id", "label", "entity_id", "actions"], [], "entity node")
            entity_id = node["entity_id"]
            if not isinstance(entity_id, str) or len(entity_id) > 255 or not ENTITY.fullmatch(entity_id):
                raise ProtocolError("invalid entity_id")
            actions = node["actions"]
            if not isinstance(actions, list) or any(action != "toggle" for action in actions):
                raise ProtocolError("unsupported actions")
            if len(actions) > 1:
                raise ProtocolError("duplicate actions")
            if actions and entity_id.split(".", 1)[0] not in TOGGLE_DOMAINS:
                raise ProtocolError("domain does not support toggle")
        else:
            raise ProtocolError("unknown node type")
        node_id = node["id"]
        if not isinstance(node_id, str) or not ID.fullmatch(node_id) or node_id in seen:
            raise ProtocolError("invalid or duplicate node id")
        seen.add(node_id)
        _text(node["label"], 120, "label")
    return copy.deepcopy(document)


def index_nodes(document):
    """Index a previously validated document."""
    result = {}
    pending = [document["root"]]
    while pending:
        node = pending.pop()
        result[node["id"]] = node
        if node["type"] == "menu":
            pending.extend(node["children"])
    return result
