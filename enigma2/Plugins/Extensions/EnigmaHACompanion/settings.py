"""Private receiver configuration, independent of Enigma2 globals."""

import json
import os
import tempfile

from .skin import profile_choices
from .companion.i18n import LANGUAGE_CHOICES, translate

CONFIG_PATH = "/etc/enigma2/enigmaha_companion.json"
DEFAULTS = {"url": "", "token": "", "refresh_seconds": 10, "font_family": "",
            "font_size": 0, "timeout": 5, "show_in_mainmenu": False,
            "reverse_channel_paging": False, "skin_profile": "auto", "language": "auto"}


def validate_settings(values):
    if not isinstance(values, dict) or set(values) - set(DEFAULTS):
        raise ValueError("Ungültige Konfigurationsfelder")
    language = values.get("language", "de")
    t = lambda message: translate(message, language)
    result = dict(DEFAULTS)
    result.update(values)
    # A stored configuration without a language predates language selection.
    # Only an absent settings file starts with the new automatic default.
    result["language"] = language
    if not isinstance(result["language"], str) or result["language"] not in dict(LANGUAGE_CHOICES):
        raise ValueError(t("Ungültige Sprache"))
    if not isinstance(result["skin_profile"], str) or result["skin_profile"] not in dict(profile_choices()):
        raise ValueError(t("Ungültiges Skin-Profil"))
    if type(result["show_in_mainmenu"]) is not bool:
        raise ValueError(t("Ungültiger Hauptmenü-Schalter"))
    if type(result["reverse_channel_paging"]) is not bool:
        raise ValueError(t("Ungültige Ch-Blätterrichtung"))
    for name in ("url", "token", "font_family"):
        if not isinstance(result[name], str):
            raise ValueError(t("Ungültiger Textwert"))
    result["font_family"] = result["font_family"].strip()
    if len(result["font_family"]) > 64 or any(ord(c) < 32 or ord(c) == 127 for c in result["font_family"]):
        raise ValueError(t("Ungültige Schriftfamilie"))
    for name, low, high in (("refresh_seconds", 5, 300), ("timeout", 1, 30), ("font_size", 0, 64)):
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError(t("Ungültiger Zahlenwert"))
    if 0 < result["font_size"] < 16:
        raise ValueError(t("Schriftgröße: 0 oder 16–64"))
    return result


def load_settings(path=CONFIG_PATH):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return validate_settings(json.load(handle))
    except FileNotFoundError:
        return dict(DEFAULTS)


def save_settings(values, path=CONFIG_PATH):
    values = validate_settings(values)
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".enigmaha-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(values, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
