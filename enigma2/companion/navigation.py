"""Text-menu controller; adapters handle drawing and asynchronous I/O."""

from .i18n import translate

from enigmaha_protocol.menu import SELECT_ACTION, index_nodes, validate_display, validate_menu


class Navigator:
    def __init__(self, document, display_override=None, language="de"):
        self.language = language
        self.menu = validate_menu(document)
        self.nodes = index_nodes(self.menu)
        self.stack = [(self.menu["root"]["id"], 0)]
        self.select_preview = None
        display = dict(self.menu["display"])
        if display_override:
            display.update(display_override)
        self.display = validate_display(display)

    @property
    def current(self):
        return self.nodes[self.stack[-1][0]]

    @property
    def selection(self):
        children = self.current["children"]
        return children[self.stack[-1][1]] if children else None

    @property
    def breadcrumb(self):
        return " / ".join(self.nodes[node_id]["label"] for node_id, _ in self.stack)

    def move(self, delta):
        self.clear_select_preview()
        children = self.current["children"]
        if children:
            node_id, position = self.stack[-1]
            self.stack[-1] = (node_id, (position + delta) % len(children))

    def position(self):
        """Keep stable menu/entry IDs so reordered lists retain their selection."""
        result = []
        for menu_id, index in self.stack:
            children = self.nodes[menu_id]["children"]
            result.append([menu_id, children[index]["id"] if children else None])
        return result

    def restore_position(self, path):
        if not path:
            return
        for depth, (menu_id, selected_id) in enumerate(path):
            if self.current["id"] != menu_id:
                break
            children = self.current["children"]
            index = next((i for i, child in enumerate(children) if child["id"] == selected_id), None)
            if index is None:
                break
            self.stack[-1] = (menu_id, index)
            child = children[index]
            if (depth + 1 >= len(path) or child["type"] != "menu"
                    or path[depth + 1][0] != child["id"]):
                break
            self.stack.append((child["id"], 0))

    def back(self):
        """Return whether a parent menu was entered; stay at the root otherwise."""
        self.clear_select_preview()
        if len(self.stack) == 1:
            return False
        self.stack.pop()
        return True

    def activate(self, states):
        """Open a menu, or return a command without executing it."""
        node = self.selection
        if node is None:
            return None
        if node["type"] == "menu":
            self.clear_select_preview()
            self.stack.append((node["id"], 0))
            return None
        if SELECT_ACTION in node["actions"]:
            preview = self.select_preview
            self.select_preview = None
            state = states.get(node["entity_id"], {}).get("state")
            if (preview is None or preview[0] != node["id"] or preview[2] != tuple(node.get("options", ()))
                    or preview[1] == state):
                return None
            return {"schema_version": 1, "revision": self.menu["revision"],
                    "entry_id": node["id"], "action": SELECT_ACTION, "option": preview[1],
                    "options": list(preview[2])}
        self.clear_select_preview()
        state = states.get(node["entity_id"], {}).get("state")
        if "toggle" not in node["actions"] or state not in {"on", "off"}:
            return None
        return {"schema_version": 1, "revision": self.menu["revision"],
                "entry_id": node["id"], "action": "toggle"}

    def clear_select_preview(self):
        had_preview = self.select_preview is not None
        self.select_preview = None
        return had_preview

    def preview_select(self, direction, states):
        """Change a select value locally; the HA service runs only on activation."""
        node = self.selection
        if (node is None or node["type"] != "entity" or SELECT_ACTION not in node["actions"]
                or not node.get("options")):
            return None
        options = tuple(node["options"])
        preview = self.select_preview
        current = (preview[1] if preview is not None and preview[0] == node["id"]
                   and preview[2] == options else states.get(node["entity_id"], {}).get("state"))
        if current in options:
            position = (options.index(current) + (1 if direction > 0 else -1)) % len(options)
        else:
            position = 0 if direction > 0 else len(options) - 1
        selected = options[position]
        self.select_preview = (node["id"], selected, options)
        return selected

    def choose_select_option(self, option):
        """Use an item selected in the long-OK options list as a local preview."""
        node = self.selection
        if (node is None or node["type"] != "entity" or SELECT_ACTION not in node["actions"]
                or option not in node.get("options", ())):
            return False
        self.select_preview = (node["id"], option, tuple(node["options"]))
        return True

    def dim(self, direction, states):
        """Return a dimming command for the selected, currently available light."""
        self.clear_select_preview()
        node = self.selection
        action = "dim_up" if direction > 0 else "dim_down" if direction < 0 else None
        if (node is None or node["type"] != "entity" or action not in node["actions"]
                or states.get(node["entity_id"], {}).get("state") not in {"on", "off"}):
            return None
        return {"schema_version": 1, "revision": self.menu["revision"],
                "entry_id": node["id"], "action": action}

    def rows(self, states):
        rows = []
        for node in self.current["children"]:
            if node["type"] == "menu":
                value = ">"
            else:
                state = states.get(node["entity_id"], {})
                value = state.get("state")
                preview = self.select_preview
                if (SELECT_ACTION in node["actions"] and preview is not None and preview[0] == node["id"]
                        and preview[2] == tuple(node.get("options", ()))):
                    value = preview[1]
                brightness = state.get("brightness_pct")
                if (any(action in node["actions"] for action in ("dim_up", "dim_down"))
                        and type(brightness) is int and 0 <= brightness <= 100):
                    if value in {"on", "off"}:
                        value = "{} % {}".format(brightness,
                                translate("Ein", self.language) if value == "on" else translate("Aus", self.language))
                    else:
                        value = "{} %".format(brightness)
                elif value is None:
                    value = translate("Nicht vorhanden", self.language)
                elif value == "unavailable":
                    value = translate("Nicht verfügbar", self.language)
                elif value == "unknown":
                    value = translate("Unbekannt", self.language)
                elif value in {"on", "off"} and node["entity_id"].split(".", 1)[0] in {"light", "switch", "input_boolean"}:
                    value = translate("Ein", self.language) if value == "on" else translate("Aus", self.language)
                else:
                    unit = state.get("unit_of_measurement")
                    value = str(value) + (" " + unit if unit else "")
            rows.append((node["label"], value))
        return rows
