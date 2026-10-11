"""Restrict transported icons to passive SVG path geometry on a 24x24 canvas."""

import re

PATH = re.compile(r"[MmZzLlHhVvCcSsQqTtAa0-9eE.,+\-\s]+\Z")


def valid_icon_path(value):
    return (isinstance(value, str) and 0 < len(value) <= 16384
            and value[0] in "Mm" and PATH.fullmatch(value) is not None)


def valid_icon(value):
    return (isinstance(value, dict) and set(value) == {"name", "path"}
            and isinstance(value["name"], str)
            and re.fullmatch(r"mdi:[a-z0-9-]{1,100}", value["name"]) is not None
            and valid_icon_path(value["path"]))
