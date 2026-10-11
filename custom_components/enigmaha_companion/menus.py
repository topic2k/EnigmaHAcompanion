"""Stored menu collections, lossless v1 migration and receiver projections."""

from .enigmaha_protocol import ProtocolError, validate_menu
from .enigmaha_protocol.menu import MAX_NODES, _integer, _keys, index_nodes, validate_display


def _access(value, root=False):
    _keys(value, ["mode"], ["users"], "access")
    mode = value["mode"]
    if not isinstance(mode, str) or mode not in ({"all", "users", "none"} if root else {"inherit", "users", "none"}):
        raise ProtocolError("invalid access mode")
    if mode != "users":
        if "users" in value:
            raise ProtocolError("users only allowed for selected-user access")
        return {"mode": mode}
    users = value.get("users")
    if (not isinstance(users, list) or len(users) > MAX_NODES
            or any(not isinstance(user, str) or not user or len(user) > 64
                   or any(not (char.isascii() and (char.isalnum() or char in "_-")) for char in user)
                   for user in users) or len(set(users)) != len(users)):
        raise ProtocolError("invalid access users")
    # An empty selection deliberately grants nobody access.
    return {"mode": mode, "users": list(users)}


def _document(config, root):
    return {"schema_version": 1, "revision": config["revision"],
            "display": dict(config["display"]), "root": root}


def _selection_root(roots):
    ids = set()
    for root in roots:
        ids.update(index_nodes({"root": root}))
    node_id = "__enigmaha_menus"
    suffix = 0
    while node_id in ids:
        suffix += 1
        node_id = "__enigmaha_menus_" + str(suffix)
    return {"type": "menu", "id": node_id, "label": "Home Assistant", "children": roots}


def validate_configuration(value):
    """Validate v2; migrate a published v1 menu without changing IDs/revision."""
    if isinstance(value, dict) and value.get("schema_version") == 1:
        menu = validate_menu(value)
        menu["root"]["access"] = {"mode": "all"}
        return {"schema_version": 2, "revision": menu["revision"],
                "display": menu["display"], "menus": [menu["root"]]}
    _keys(value, ["schema_version", "revision", "display", "menus"], [], "configuration")
    if type(value["schema_version"]) is not int or value["schema_version"] != 2:
        raise ProtocolError("unsupported configuration schema_version")
    _integer(value["revision"], 1, 2147483647, "revision")
    display = validate_display(value["display"])
    if not isinstance(value["menus"], list) or len(value["menus"]) > MAX_NODES:
        raise ProtocolError("menus must be a bounded array")
    roots, bare_roots, seen = [], [], set()
    for root in value["menus"]:
        if not isinstance(root, dict) or root.get("type") != "menu":
            raise ProtocolError("each root must be a menu")
        # Strip access iteratively before the strict wire validator. Never copy
        # unbounded recursive input, including cyclic objects supplied in-process.
        stripped = {}
        accesses = {}
        pending = [(root, stripped, 0)]
        while pending:
            node, target, depth = pending.pop()
            if depth > 8 or len(seen) >= MAX_NODES or not isinstance(node, dict):
                raise ProtocolError("menu size or nesting limit exceeded")
            node_id = node.get("id")
            if not isinstance(node_id, str) or node_id in seen:
                raise ProtocolError("invalid or duplicate node id")
            seen.add(node_id)
            access = _access(node.get("access", {"mode": "all" if depth == 0 else "inherit"}), depth == 0)
            accesses[node_id] = access
            target.update({key: item for key, item in node.items() if key not in {"access", "children"}})
            if "children" in node:
                if not isinstance(node["children"], list) or len(node["children"]) > MAX_NODES:
                    raise ProtocolError("children must be a bounded array")
                target["children"] = [{} for _ in node["children"]]
                pending.extend((child, dest, depth + 1) for child, dest in zip(node["children"], target["children"]))
        bare = validate_menu(_document(value, stripped))["root"]
        bare_roots.append(bare)
        annotated = validate_menu(_document(value, bare))["root"]
        for node in index_nodes({"root": annotated}).values():
            access = accesses[node["id"]]
            if access["mode"] != "inherit":
                node["access"] = access
        roots.append(annotated)
    if len(bare_roots) > 1:
        # The extra selection level must also fit published receiver limits.
        validate_menu(_document(value, _selection_root(bare_roots)))
    return {"schema_version": 2, "revision": value["revision"], "display": display, "menus": roots}


def legacy_menu(value):
    """Return a v1 admin document only when editing it cannot lose any ACLs."""
    config = validate_configuration(value)
    if len(config["menus"]) != 1:
        return None
    root = config["menus"][0]
    for node in index_nodes({"root": root}).values():
        access = node.get("access", {"mode": "inherit"})
        if access["mode"] not in {"all", "inherit"}:
            return None
        node.pop("access", None)
    return _document(config, root)


def receiver_menu(value, user_id, can_read, can_control):
    """Use the same projection for menus, states, commands and admin previews."""
    config = validate_configuration(value)

    def visible(node):
        access = node.pop("access", {"mode": "inherit"})
        if access["mode"] == "none" or (access["mode"] == "users" and user_id not in access["users"]):
            return None
        if node["type"] == "entity":
            if not can_read(node["entity_id"]):
                return None
            if not can_control(node["entity_id"]):
                node["actions"] = []
        else:
            had_children = bool(node["children"])
            node["children"] = [child for child in (visible(child) for child in node["children"]) if child is not None]
            if had_children and not node["children"]:
                return None
        return node

    roots = [root for root in (visible(root) for root in config["menus"]) if root is not None]
    if len(roots) == 1:
        root = roots[0]
    elif roots:
        root = _selection_root(roots)
    else:
        root = {"type": "menu", "id": "__enigmaha_no_menu", "label": "Home Assistant", "children": []}
    return validate_menu(_document(config, root))
