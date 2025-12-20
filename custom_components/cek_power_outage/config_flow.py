"""Config flow for CEK Power Outage integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_QUEUE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_QUEUE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MAX_UPDATE_INTERVAL,
    MIN_UPDATE_INTERVAL,
)


class CEKPowerOutageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for CEK Power Outage."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            queue = user_input[CONF_QUEUE]

            # Check if this queue is already configured
            await self.async_set_unique_id(f"cek_{queue}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"CEK Queue {queue}",
                data={CONF_QUEUE: queue},
                options={CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL]},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_QUEUE, default=DEFAULT_QUEUE): str,
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
                "max_interval": str(MAX_UPDATE_INTERVAL),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return CEKPowerOutageOptionsFlow()


class CEKPowerOutageOptionsFlow(OptionsFlow):
    """Handle options flow for CEK Power Outage."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=current_interval
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_UPDATE_INTERVAL, max=MAX_UPDATE_INTERVAL),
                    ),
                }
            ),
            description_placeholders={
                "min_interval": str(MIN_UPDATE_INTERVAL),
                "max_interval": str(MAX_UPDATE_INTERVAL),
            },
        )


