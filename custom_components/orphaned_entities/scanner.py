"""Orphaned Entity Scanner."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.util import dt as dt_util

from .const import (
    CONF_INACTIVITY_DAYS,
    CONF_IGNORED_DOMAINS,
    DEFAULT_INACTIVITY_DAYS,
    DEFAULT_IGNORED_DOMAINS,
)

_LOGGER = logging.getLogger(__name__)


class OrphanedEntityScanner:
    """Scans for orphaned or inactive entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry

    async def async_scan(self, ignored_entities: set[str]) -> list[dict]:
        """Scan entity and device registries for orphaned entities."""
        hass = self._hass
        options = self._entry.options

        inactivity_days = options.get(CONF_INACTIVITY_DAYS, DEFAULT_INACTIVITY_DAYS)
        ignored_domains_str = options.get(CONF_IGNORED_DOMAINS, DEFAULT_IGNORED_DOMAINS)
        ignored_domains = {d.strip() for d in ignored_domains_str.split(",") if d.strip()}

        ent_reg = er.async_get(hass)
        dev_reg = dr.async_get(hass)

        now = dt_util.utcnow()
        cutoff = now - timedelta(days=inactivity_days)

        results = []

        for entity_entry in ent_reg.entities.values():
            entity_id = entity_entry.entity_id
            domain = entity_id.split(".")[0]

            # Skip ignored domains
            if domain in ignored_domains:
                continue

            # Skip already disabled entities
            if entity_entry.disabled:
                continue

            # Skip explicitly ignored entities
            if entity_id in ignored_entities:
                continue

            orphan_reasons = []

            # Check: unavailable device
            if entity_entry.device_id:
                device = dev_reg.async_get(entity_entry.device_id)
                if device is None:
                    orphan_reasons.append("device_missing")
            else:
                # No device at all — check if it has a config entry
                if not entity_entry.config_entry_id and not entity_entry.platform:
                    orphan_reasons.append("no_device_no_platform")

            # Check: state availability
            state = hass.states.get(entity_id)
            if state is None:
                orphan_reasons.append("no_state")
            elif state.state in ("unavailable", "unknown"):
                # Check how long it's been unavailable
                last_changed = state.last_changed
                if last_changed and last_changed < cutoff:
                    # Show even if entity has a config_entry — long-term unavailable
                    # is a strong signal of an orphaned browser session, removed device, etc.
                    orphan_reasons.append(f"unavailable_{inactivity_days}d")

            # Check: entity has no config entry and no device
            if (
                entity_entry.config_entry_id is None
                and entity_entry.device_id is None
                and domain not in {"input_boolean", "input_text", "input_number",
                                   "input_select", "input_datetime", "input_button",
                                   "timer", "counter", "zone", "person", "automation",
                                   "script", "scene", "group"}
            ):
                orphan_reasons.append("no_integration")

            # Check: entity has integration/device but has been unavailable
            # longer than the inactivity threshold — catches stale browser sessions,
            # removed devices that left entries behind, etc.
            # Only add this reason if no other reason was found yet (avoids duplicates)
            if not orphan_reasons and state is not None and state.state in ("unavailable", "unknown"):
                last_changed = state.last_changed
                if last_changed and last_changed < cutoff:
                    orphan_reasons.append(f"stale_{inactivity_days}d")

            if orphan_reasons:
                entity_info = {
                    "entity_id": entity_id,
                    "name": entity_entry.name or (state.attributes.get("friendly_name") if state else None) or entity_id,
                    "domain": domain,
                    "platform": entity_entry.platform or "unknown",
                    "reasons": orphan_reasons,
                    "state": state.state if state else "not_found",
                    "last_changed": state.last_changed.isoformat() if state and state.last_changed else None,
                    "disabled": entity_entry.disabled,
                    "device_id": entity_entry.device_id,
                    "config_entry_id": entity_entry.config_entry_id,
                }
                results.append(entity_info)

        _LOGGER.info("Orphaned entity scan: %d candidates found", len(results))
        return results
