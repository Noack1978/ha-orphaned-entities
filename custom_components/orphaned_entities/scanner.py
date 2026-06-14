"""Orphaned Entity Scanner."""
from __future__ import annotations

import logging
from datetime import timedelta

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

YAML_BASED_PLATFORMS = {
    "template", "statistics", "filter", "min_max", "utility_meter",
    "history_stats", "trend", "threshold", "tod", "generic_hygrostat",
    "generic_thermostat", "derivative", "integration", "bayesian",
    "combine_state",
}

NO_DEVICE_OK_DOMAINS = {
    "input_boolean", "input_text", "input_number", "input_select",
    "input_datetime", "input_button", "timer", "counter", "zone",
    "person", "automation", "script", "scene", "group",
}


async def _get_active_entity_ids(hass: HomeAssistant, entity_ids: list[str], cutoff) -> set[str]:
    """Query recorder DB for entity_ids that had a non-unavailable/unknown
    state within the cutoff window. Returns a set of entity_ids that ARE active.

    If the recorder cannot be queried, returns the full input set (i.e. treat
    everything as active — fail safe, never flag as stale)."""
    if not entity_ids:
        return set()

    try:
        from homeassistant.components.recorder import get_instance
        from homeassistant.components.recorder.util import session_scope
        import sqlalchemy as sa

        recorder_instance = get_instance(hass)

        def _query() -> set[str]:
            with session_scope(session=recorder_instance.get_session()) as session:
                try:
                    rows = session.execute(
                        sa.text(
                            "SELECT DISTINCT sm.entity_id FROM states s "
                            "JOIN states_meta sm ON s.metadata_id = sm.metadata_id "
                            "WHERE sm.entity_id IN :eids "
                            "AND s.state NOT IN ('unavailable', 'unknown') "
                            "AND s.last_updated_ts >= :cutoff"
                        ).bindparams(sa.bindparam("eids", expanding=True)),
                        {"eids": entity_ids, "cutoff": cutoff.timestamp()},
                    ).fetchall()
                    return {r[0] for r in rows}
                except Exception:
                    try:
                        rows = session.execute(
                            sa.text(
                                "SELECT DISTINCT entity_id FROM states "
                                "WHERE entity_id IN :eids "
                                "AND state NOT IN ('unavailable', 'unknown') "
                                "AND last_updated >= :cutoff"
                            ).bindparams(sa.bindparam("eids", expanding=True)),
                            {"eids": entity_ids, "cutoff": cutoff.isoformat()},
                        ).fetchall()
                        return {r[0] for r in rows}
                    except Exception:
                        return set(entity_ids)  # fail safe: treat all as active

        return await recorder_instance.async_add_executor_job(_query)
    except Exception:
        return set(entity_ids)  # recorder unavailable: fail safe


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

        # ── Pre-pass: collect candidate entities and group by device ──
        # We need to know, for each device, whether ANY of its entities had
        # real activity within the cutoff window. This avoids flagging
        # sub-entities (e.g. "Child lock" on a switch) as stale just because
        # that particular feature is unsupported/never reported, while the
        # device itself is fully active.
        all_entity_ids: list[str] = []
        device_entity_map: dict[str, list[str]] = {}

        for entity_entry in ent_reg.entities.values():
            entity_id = entity_entry.entity_id
            domain = entity_id.split(".")[0]
            if domain in ignored_domains or entity_entry.disabled or entity_id in ignored_entities:
                continue
            state = hass.states.get(entity_id)
            if state is not None and state.state in ("unavailable", "unknown"):
                all_entity_ids.append(entity_id)
                if entity_entry.device_id:
                    device_entity_map.setdefault(entity_entry.device_id, []).append(entity_id)

        active_entity_ids = await _get_active_entity_ids(hass, all_entity_ids, cutoff)

        # Devices that have at least one entity with recent real activity
        active_devices: set[str] = set()
        for device_id, entities in device_entity_map.items():
            if any(eid in active_entity_ids for eid in entities):
                active_devices.add(device_id)

        # ── Main pass ──
        results = []

        for entity_entry in ent_reg.entities.values():
            entity_id = entity_entry.entity_id
            domain = entity_id.split(".")[0]

            if domain in ignored_domains:
                continue
            if entity_entry.disabled:
                continue
            if entity_id in ignored_entities:
                continue

            orphan_reasons = []

            # Check: device referenced but missing from registry
            if entity_entry.device_id:
                device = dev_reg.async_get(entity_entry.device_id)
                if device is None:
                    orphan_reasons.append("device_missing")
            else:
                if not entity_entry.config_entry_id and not entity_entry.platform:
                    orphan_reasons.append("no_device_no_platform")

            state = hass.states.get(entity_id)

            if state is None:
                orphan_reasons.append("no_state")
            elif state.state in ("unavailable", "unknown"):
                last_changed = state.last_changed
                if last_changed and last_changed < cutoff:
                    orphan_reasons.append(f"unavailable_{inactivity_days}d")

            # Check: entity has no config entry and no device — but exclude
            # YAML-based helper platforms (template, statistics, ...) which
            # legitimately have neither.
            if (
                entity_entry.config_entry_id is None
                and entity_entry.device_id is None
                and entity_entry.platform not in YAML_BASED_PLATFORMS
                and domain not in NO_DEVICE_OK_DOMAINS
            ):
                orphan_reasons.append("no_integration")

            # Check: entity has integration/device but is persistently
            # unavailable/unknown AND (if it belongs to a device) the device
            # itself has no other entity with recent activity either.
            # This avoids false positives for sub-entities like "Child lock"
            # that a device simply never reports, while the device is alive.
            if (
                not orphan_reasons
                and state is not None
                and state.state in ("unavailable", "unknown")
            ):
                if entity_entry.device_id:
                    device_is_active = entity_entry.device_id in active_devices
                else:
                    device_is_active = entity_id in active_entity_ids

                if not device_is_active:
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
