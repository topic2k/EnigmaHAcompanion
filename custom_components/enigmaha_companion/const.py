DOMAIN = "enigmaha_companion"
BASE = "/api/enigmaha_companion/v1"
VERSION = "1.1.1"
CONF_LANGUAGE = "language"
DEFAULT_LANGUAGE = "auto"
LEGACY_LANGUAGE = "de"
LANGUAGES = ("de", "en", "auto")


def empty_menu():
    return {"schema_version": 1, "revision": 1,
            "display": {"font_family": "Regular", "font_size": 28},
            "root": {"type": "menu", "id": "home", "label": "Home Assistant", "children": []}}
