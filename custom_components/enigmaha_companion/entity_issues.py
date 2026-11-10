"""Home Assistant repair issues for missing menu entities."""

import asyncio
import hashlib

from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .const import DOMAIN

MISSING_ENTITY_ISSUE = "missing_menu_entity"


def _issue_id(entity_id):
    return MISSING_ENTITY_ISSUE + "_" + hashlib.sha256(entity_id.encode("utf-8")).hexdigest()


class EntityIssueCoordinator:
    def __init__(self, hass, runtime):
        self.hass = hass
        self.runtime = runtime
        self.active = True
        self.started = False
        self.missing = set()
        self.issue_ids = set()
        self.unsubscribers = []
        self.lock = asyncio.Lock()

    async def async_start(self):
        bus = getattr(self.hass, "bus", None)
        if getattr(self.hass, "is_running", False):
            await self._async_started(None)
        elif bus is not None and hasattr(bus, "async_listen_once"):
            self.unsubscribers.append(bus.async_listen_once("homeassistant_started", self._async_started))

    async def _async_started(self, event):
        if not self.active or self.started:
            return
        self.started = True
        bus = getattr(self.hass, "bus", None)
        if bus is not None and hasattr(bus, "async_listen"):
            self.unsubscribers.extend((
                bus.async_listen("entity_registry_updated", self._async_registry_updated),
                bus.async_listen("state_changed", self._async_state_changed),
            ))
        await self.sync()

    async def _async_registry_updated(self, event):
        await self.sync()

    async def _async_state_changed(self, event):
        if event.data.get("entity_id") in self.missing:
            await self.sync()

    def _referenced_entities(self):
        references = {}
        for root in self.runtime.menu.get("menus", ()):
            pending = [root]
            while pending:
                node = pending.pop()
                if node["type"] == "menu":
                    pending.extend(node["children"])
                else:
                    references.setdefault(node["entity_id"], []).append(node["label"])
        return references

    def _entity_exists(self, entity_id, registry):
        states = getattr(self.hass, "states", None)
        if states is not None and states.get(entity_id) is not None:
            return True
        entities = getattr(registry, "entities", {})
        if entities.get(entity_id) is not None:
            return True
        return getattr(registry, "async_get", lambda _entity_id: None)(entity_id) is not None

    async def sync(self):
        if not self.active or not self.started:
            return
        async with self.lock:
            if not self.active or not self.started:
                return
            registry = async_get_entity_registry(self.hass)
            references = self._referenced_entities()
            missing = {entity_id: labels for entity_id, labels in references.items()
                       if not self._entity_exists(entity_id, registry)}
            for entity_id, labels in missing.items():
                issue_id = _issue_id(entity_id)
                self.issue_ids.add(issue_id)
                ir.async_create_issue(
                    self.hass, DOMAIN, issue_id,
                    is_fixable=False, is_persistent=True, severity=ir.IssueSeverity.WARNING,
                    translation_key=MISSING_ENTITY_ISSUE,
                    translation_placeholders={
                        "entity_id": entity_id,
                        "entries": ", ".join(labels[:5]) + (" …" if len(labels) > 5 else ""),
                    },
                )
            missing_ids = {_issue_id(entity_id) for entity_id in missing}
            current_ids = {_issue_id(entity_id) for entity_id in references}
            for issue_id in (current_ids | self.issue_ids) - missing_ids:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)
            self.issue_ids = missing_ids
            self.missing = set(missing)

    def close(self):
        self.active = False
        for unsubscribe in self.unsubscribers:
            unsubscribe()
        self.unsubscribers.clear()
        self.issue_ids.clear()
        self.missing.clear()