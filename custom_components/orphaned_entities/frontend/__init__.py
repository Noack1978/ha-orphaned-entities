"""Frontend resource registration for Orphaned Entities card."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_JS_FILENAME = "orphaned-entities-card.js"
URL_BASE = "/orphaned_entities_card"
_FRONTEND_DIR = Path(__file__).parent


class JSModuleRegistration:
    """Handles registration of the Lovelace JS module."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def async_register(self) -> None:
        """Register static path and Lovelace resource."""
        hass = self._hass
        url_path = f"{URL_BASE}/{CARD_JS_FILENAME}"

        # Register static HTTP path
        await hass.http.async_register_static_paths([
            StaticPathConfig(URL_BASE, str(_FRONTEND_DIR), cache_headers=False)
        ])
        _LOGGER.info("Orphaned Entities: static path OK → %s", url_path)

        # Register Lovelace resource via lovelace storage
        await _async_register_resource(hass, url_path)


async def _async_register_resource(hass: HomeAssistant, url_path: str) -> None:
    """Register JS module as Lovelace resource using storage directly."""
    from homeassistant.helpers.storage import Store

    LOVELACE_RESOURCES_STORAGE = "lovelace_resources"
    store = Store(hass, 1, LOVELACE_RESOURCES_STORAGE)

    try:
        data = await store.async_load()
    except Exception as err:
        _LOGGER.warning("Orphaned Entities: could not read lovelace_resources storage: %s", err)
        data = None

    if data is None:
        data = {"items": []}

    items = data.get("items", [])

    # Check if already registered
    if any(item.get("url") == url_path for item in items):
        _LOGGER.debug("Orphaned Entities: Lovelace resource already present")
        return

    # Add new resource entry
    import uuid
    new_item = {
        "id": str(uuid.uuid4()).replace("-", "")[:8],
        "type": "module",
        "url": url_path,
    }
    items.append(new_item)
    data["items"] = items

    try:
        await store.async_save(data)
        _LOGGER.info("Orphaned Entities: Lovelace resource registered → %s", url_path)
    except Exception as err:
        _LOGGER.warning(
            "Orphaned Entities: could not save Lovelace resource. "
            "Add manually: URL=%s Type=JavaScript-Modul. Error: %s",
            url_path, err,
        )
