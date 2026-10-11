"""Resolve entity icons using the installed Home Assistant frontend assets."""

import asyncio
from collections import OrderedDict
import json
import logging
from pathlib import Path
import re

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons

from .enigmaha_protocol.icons import valid_icon_path

DEFAULTS = {
    "light": ("mdi:lightbulb", "mdi:lightbulb-off"),
    "switch": ("mdi:toggle-switch-variant", "mdi:toggle-switch-variant-off"),
    "input_boolean": ("mdi:toggle-switch", "mdi:toggle-switch-off"),
    "binary_sensor": ("mdi:checkbox-marked-circle", "mdi:radiobox-blank"),
}
_LOGGER = logging.getLogger(__name__)
MAX_CHUNK_BYTES = 1024 * 1024
MAX_CACHED_CHUNKS = 4


class FrontendIconPaths:
    """Read HA's local static/mdi JSON chunks on demand, off the event loop.

    Use HA's chunk metadata and retain only four chunks of geometry.
    Frontend updates take effect with the usual HA restart. No network is used.
    """

    def __init__(self, root=None):
        self.root = root
        self.parts = None
        self.chunks = OrderedDict()
        self.warned = False

    def _read_json(self, file):
        with file.open("rb") as stream:
            data = stream.read(MAX_CHUNK_BYTES + 1)
        if len(data) > MAX_CHUNK_BYTES:
            raise ValueError("frontend icon chunk too large")
        return json.loads(data)

    def _read(self, file):
        if file in self.chunks:
            self.chunks.move_to_end(file)
            return self.chunks[file]
        chunk = self._read_json(file)
        if not isinstance(chunk, dict):
            raise ValueError("frontend icon chunk must be an object")
        self.chunks[file] = chunk
        if len(self.chunks) > MAX_CACHED_CHUNKS:
            self.chunks.popitem(last=False)
        return chunk

    def get(self, name):
        """Return validated geometry, or let the receiver show state text."""
        try:
            if self.parts is None:
                if self.root is None:
                    import hass_frontend
                    self.root = Path(hass_frontend.where())
                metadata = self._read_json(self.root / "static/mdi/iconMetadata.json")
                parts = metadata.get("parts") if isinstance(metadata, dict) else None
                if not isinstance(parts, list) or not parts:
                    raise ValueError("HA frontend icon metadata has no parts")
                previous_start = ""
                for index, part in enumerate(parts):
                    if (not isinstance(part, dict) or not isinstance(part.get("file"), str)
                            or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", part["file"])):
                        raise ValueError("invalid frontend icon chunk filename")
                    start = part.get("start", "")
                    if (not isinstance(start, str) or (index and start <= previous_start)
                            or (not index and start)):
                        raise ValueError("invalid frontend icon chunk boundaries")
                    previous_start = start
                self.parts = parts
            # Same lexicographic chunk selection as HA's findIconChunk().
            selected = self.parts[0]["file"]
            for part in self.parts[1:]:
                if name < part["start"]:
                    break
                selected = part["file"]
            path = self._read(self.root / "static/mdi" / (selected + ".json")).get(name)
            return path if valid_icon_path(path) else None
        except (ImportError, OSError, ValueError, RecursionError):
            if not self.warned:
                _LOGGER.warning("Home Assistant icon assets unavailable; receiver uses state text")
                self.warned = True
        return None


def state_icon(resource, state):
    return resource.get("state", {}).get(state) or resource.get("default")


class IconResolver:
    def __init__(self, hass):
        self.hass = hass
        self.frontend = FrontendIconPaths()
        self.lock = asyncio.Lock()

    async def resolve(self, state):
        domain = state.entity_id.split(".", 1)[0]
        if state.state not in {"on", "off"}:
            return None
        registry = er.async_get(self.hass)
        entry = registry.async_get(state.entity_id)
        name = (entry.icon if entry else None) or state.attributes.get("icon")
        if not name and entry and entry.translation_key:
            resources = await async_get_icons(self.hass, "entity", [entry.platform])
            resource = resources.get(entry.platform, {}).get(domain, {}).get(entry.translation_key, {})
            name = state_icon(resource, state.state)
        if not name:
            resources = await async_get_icons(self.hass, "entity_component", [domain])
            component = resources.get(domain, {})
            resource = component.get(state.attributes.get("device_class")) or component.get("_", {})
            name = state_icon(resource, state.state)
        fallback = DEFAULTS.get(domain, DEFAULTS["binary_sensor"])[state.state == "off"]
        # Browser-only custom icon providers cannot execute in the integration.
        if not isinstance(name, str) or name.split(":", 1)[0] not in {"mdi", "hass", "hassio"}:
            name = fallback
        else:
            name = "mdi:" + name.split(":", 1)[-1]
        async with self.lock:
            path = await self.hass.async_add_executor_job(self.frontend.get, name[4:])
            if not path and name != fallback:
                name = fallback
                path = await self.hass.async_add_executor_job(self.frontend.get, name[4:])
        return {"name": name, "path": path} if path else None
