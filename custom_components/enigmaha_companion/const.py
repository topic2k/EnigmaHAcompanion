DOMAIN = "enigmaha_companion"
BASE = "/api/enigmaha_companion/v1"
VERSION = "1.0.1"


def empty_menu():
    return {"schema_version": 1, "revision": 1,
            "display": {"font_family": "Regular", "font_size": 28},
            "root": {"type": "menu", "id": "home", "label": "Home Assistant", "children": []}}
