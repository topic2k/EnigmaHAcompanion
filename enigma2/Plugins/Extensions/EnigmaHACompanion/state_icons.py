"""Render HA's passive SVG geometry with Enigma2's native SVG decoder."""

from collections import OrderedDict
import os
from tempfile import TemporaryDirectory

from Tools.LoadPixmap import LoadPixmap

from .enigmaha_protocol.icons import valid_icon


class StateIcons:
    def __init__(self):
        self.cache = OrderedDict()
        try:
            self.directory = TemporaryDirectory(prefix="enigmaha-icons-")
        except OSError:
            self.directory = None

    def get(self, state, size):
        icon = state.get("icon")
        if not self.directory or state.get("state") not in {"on", "off"} or not valid_icon(icon):
            return None
        color = "#ffc107" if state["state"] == "on" else "#9e9e9e"
        key = (icon["path"], color, size)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        # Only path grammar is accepted, never externally supplied XML/URLs.
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               'width="{0}" height="{0}"><path fill="{1}" d="{2}"/></svg>').format(size, color, icon["path"])
        file = os.path.join(self.directory.name, "icon.svg")
        pixmap = None
        try:
            with open(file, "w", encoding="ascii") as stream:
                stream.write(svg)
            pixmap = LoadPixmap(file, cached=False, width=size, height=size)
        except (OSError, RuntimeError, ValueError):
            pass  # Keep the readable state text if decoding fails.
        finally:
            try:
                os.unlink(file)
            except OSError:
                pass
        self.cache[key] = pixmap
        if len(self.cache) > 128:
            self.cache.popitem(last=False)
        return pixmap

    def close(self):
        self.cache.clear()
        if self.directory:
            self.directory.cleanup()
            self.directory = None
