"""Text-menu controller; adapters handle drawing and asynchronous I/O."""

from enigmaha_protocol.menu import index_nodes, validate_display, validate_menu


class Navigator:
    def __init__(self, document, display_override=None):
        self.menu = validate_menu(document)
        self.nodes = index_nodes(self.menu)
        self.stack = [(self.menu["root"]["id"], 0)]
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
        children = self.current["children"]
        if children:
            node_id, position = self.stack[-1]
            self.stack[-1] = (node_id, (position + delta) % len(children))

    def back(self):
        """False at root tells the GUI to close the plugin."""
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
            self.stack.append((node["id"], 0))
            return None
        state = states.get(node["entity_id"], {}).get("state")
        if "toggle" not in node["actions"] or state not in {"on", "off"}:
            return None
        return {"schema_version": 1, "revision": self.menu["revision"],
                "entry_id": node["id"], "action": "toggle"}

    def rows(self, states):
        rows = []
        for node in self.current["children"]:
            if node["type"] == "menu":
                value = ">"
            else:
                state = states.get(node["entity_id"], {})
                value = state.get("state")
                if value is None:
                    value = "Nicht vorhanden"
                elif value == "unavailable":
                    value = "Nicht verfügbar"
                elif value == "unknown":
                    value = "Unbekannt"
                elif value in {"on", "off"} and node["entity_id"].split(".", 1)[0] in {"light", "switch", "input_boolean"}:
                    value = "Ein" if value == "on" else "Aus"
                else:
                    unit = state.get("unit_of_measurement")
                    value = str(value) + (" " + unit if unit else "")
            rows.append((node["label"], value))
        return rows
