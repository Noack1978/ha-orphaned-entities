"""Config Flow for Orphaned Entities."""
from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload, ConfigEntry
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_SCAN_INTERVAL,
    CONF_INACTIVITY_DAYS,
    CONF_IGNORED_DOMAINS,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_INACTIVITY_DAYS,
    DEFAULT_IGNORED_DOMAINS,
)


class OrphanedEntitiesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")

        if user_input is not None:
            return self.async_create_entry(
                title="Orphaned Entities",
                data={},
                options={
                    CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL],
                    CONF_INACTIVITY_DAYS: user_input[CONF_INACTIVITY_DAYS],
                    CONF_IGNORED_DOMAINS: user_input[CONF_IGNORED_DOMAINS],
                },
            )

        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(int, vol.Range(min=1, max=168)),
            vol.Optional(CONF_INACTIVITY_DAYS, default=DEFAULT_INACTIVITY_DAYS): vol.All(int, vol.Range(min=1, max=365)),
            vol.Optional(CONF_IGNORED_DOMAINS, default=DEFAULT_IGNORED_DOMAINS): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return OrphanedEntitiesOptionsFlow()


class OrphanedEntitiesOptionsFlow(OptionsFlowWithReload):
    """Options flow."""

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema({
            vol.Optional(
                CONF_SCAN_INTERVAL,
                default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
            ): vol.All(int, vol.Range(min=1, max=168)),
            vol.Optional(
                CONF_INACTIVITY_DAYS,
                default=self.config_entry.options.get(CONF_INACTIVITY_DAYS, DEFAULT_INACTIVITY_DAYS),
            ): vol.All(int, vol.Range(min=1, max=365)),
            vol.Optional(
                CONF_IGNORED_DOMAINS,
                default=self.config_entry.options.get(CONF_IGNORED_DOMAINS, DEFAULT_IGNORED_DOMAINS),
            ): str,
        })

        return self.async_show_form(step_id="init", data_schema=schema)
