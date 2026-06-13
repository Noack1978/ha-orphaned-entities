"""Orphaned Entities Integration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_INACTIVITY_DAYS,
    CONF_IGNORED_DOMAINS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_INACTIVITY_DAYS,
    DEFAULT_IGNORED_DOMAINS,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .scanner import OrphanedEntityScanner

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = []


@dataclass
class OrphanedEntitiesData:
    """Runtime data for the integration."""

    scanner: OrphanedEntityScanner
    store: Store
    ignored_entities: set[str] = field(default_factory=set)
    last_scan_results: list[dict] = field(default_factory=list)
    cancel_interval: object = None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Orphaned Entities from a config entry."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored = await store.async_load() or {}

    ignored = set(stored.get("ignored_entities", []))

    scanner = OrphanedEntityScanner(hass, entry)
    runtime = OrphanedEntitiesData(
        scanner=scanner,
        store=store,
        ignored_entities=ignored,
    )
    entry.runtime_data = runtime

    # Initial scan
    runtime.last_scan_results = await scanner.async_scan(ignored)

    # Schedule periodic scan
    interval_hours = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    @callback
    def _scheduled_scan(now=None):
        hass.async_create_background_task(
            _do_scan(hass, entry),
            name="orphaned_entities_scan",
        )

    runtime.cancel_interval = async_track_time_interval(
        hass,
        _scheduled_scan,
        timedelta(hours=interval_hours),
    )

    # Register services
    _register_services(hass, entry)

    # Register frontend resource
    await _register_frontend(hass)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _do_scan(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Perform a background scan."""
    runtime: OrphanedEntitiesData = entry.runtime_data
    runtime.last_scan_results = await runtime.scanner.async_scan(runtime.ignored_entities)
    _LOGGER.debug("Orphaned entities scan complete: %d found", len(runtime.last_scan_results))


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Register integration services."""

    async def handle_get_results(call: ServiceCall) -> None:
        runtime: OrphanedEntitiesData = entry.runtime_data
        hass.bus.async_fire(
            f"{DOMAIN}_results",
            {
                "entities": runtime.last_scan_results,
                "ignored": list(runtime.ignored_entities),
            },
        )

    async def handle_rescan(call: ServiceCall) -> None:
        runtime: OrphanedEntitiesData = entry.runtime_data
        runtime.last_scan_results = await runtime.scanner.async_scan(runtime.ignored_entities)
        hass.bus.async_fire(
            f"{DOMAIN}_results",
            {
                "entities": runtime.last_scan_results,
                "ignored": list(runtime.ignored_entities),
            },
        )

    async def handle_disable_entity(call: ServiceCall) -> None:
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        ent_reg = er.async_get(hass)
        ent_reg.async_update_entity(
            entity_id,
            disabled_by=er.RegistryEntryDisabler.USER,
        )
        _LOGGER.info("Disabled orphaned entity: %s", entity_id)

    async def handle_delete_entity(call: ServiceCall) -> None:
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        ent_reg = er.async_get(hass)
        entry_obj = ent_reg.async_get(entity_id)
        if entry_obj:
            ent_reg.async_remove(entity_id)
            _LOGGER.info("Deleted orphaned entity: %s", entity_id)

    async def handle_ignore_entity(call: ServiceCall) -> None:
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        runtime: OrphanedEntitiesData = entry.runtime_data
        runtime.ignored_entities.add(entity_id)
        await runtime.store.async_save(
            {"ignored_entities": list(runtime.ignored_entities)}
        )
        _LOGGER.info("Ignored orphaned entity: %s", entity_id)
        hass.bus.async_fire(
            f"{DOMAIN}_results",
            {
                "entities": runtime.last_scan_results,
                "ignored": list(runtime.ignored_entities),
            },
        )

    async def handle_unignore_entity(call: ServiceCall) -> None:
        entity_id = call.data.get("entity_id")
        if not entity_id:
            return
        runtime: OrphanedEntitiesData = entry.runtime_data
        runtime.ignored_entities.discard(entity_id)
        await runtime.store.async_save(
            {"ignored_entities": list(runtime.ignored_entities)}
        )
        _LOGGER.info("Unignored orphaned entity: %s", entity_id)
        hass.bus.async_fire(
            f"{DOMAIN}_results",
            {
                "entities": runtime.last_scan_results,
                "ignored": list(runtime.ignored_entities),
            },
        )

    if not hass.services.has_service(DOMAIN, "get_results"):
        hass.services.async_register(DOMAIN, "get_results", handle_get_results)
        hass.services.async_register(DOMAIN, "rescan", handle_rescan)
        hass.services.async_register(DOMAIN, "disable_entity", handle_disable_entity)
        hass.services.async_register(DOMAIN, "delete_entity", handle_delete_entity)
        hass.services.async_register(DOMAIN, "ignore_entity", handle_ignore_entity)
        hass.services.async_register(DOMAIN, "unignore_entity", handle_unignore_entity)


async def _register_frontend(hass: HomeAssistant) -> None:
    """Register the Lovelace card resource."""
    from homeassistant.components.frontend import async_register_built_in_panel
    from homeassistant.components.lovelace.resources import ResourceStorageCollection
    import homeassistant.components.lovelace as lovelace_comp

    resource_url = "/orphaned_entities_card/orphaned-entities-card.js"
    try:
        resources = hass.data.get("lovelace", {}).get("resources")
        if resources is None:
            return
        current = [r["url"] for r in resources.async_items()]
        if resource_url not in current:
            await resources.async_create_item(
                {"res_type": "module", "url": resource_url}
            )
    except Exception as err:
        _LOGGER.debug("Could not auto-register frontend resource: %s", err)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration (runs once). Registers frontend resource."""
    from homeassistant.core import CoreState, EVENT_HOMEASSISTANT_STARTED
    from .frontend import JSModuleRegistration

    async def _register_frontend(_event=None) -> None:
        await JSModuleRegistration(hass).async_register()

    if hass.state is CoreState.running:
        await _register_frontend()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _register_frontend)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    runtime: OrphanedEntitiesData = entry.runtime_data
    if runtime.cancel_interval:
        runtime.cancel_interval()
    for service in ["get_results", "rescan", "disable_entity", "delete_entity",
                    "ignore_entity", "unignore_entity"]:
        hass.services.async_remove(DOMAIN, service)
    return True
