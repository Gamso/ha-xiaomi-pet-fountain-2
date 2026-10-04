"""Config flow for the Xiaomi Smart Pet Fountain 2."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
import voluptuous as vol

from .api import FountainAuthError, FountainClient, FountainConnectionError, FountainInfo
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    SUPPORTED_MODELS,
)

_LOGGER = logging.getLogger(__name__)

TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _user_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
        }
    )


def unique_id_from_info(info: FountainInfo) -> str | None:
    """Stable identifier of the device: its MAC address, else its device ID."""
    if info.mac:
        return format_mac(info.mac)
    if info.serial_number:
        return f"did_{info.serial_number}"
    return None


class XiaomiPetFountainConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a fountain by IP address and token."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FountainOptionsFlow:
        """Create the options flow."""
        return FountainOptionsFlow()

    async def _async_validate(
        self, user_input: dict[str, Any], errors: dict[str, str]
    ) -> tuple[dict[str, str], FountainInfo] | None:
        """Normalize and check the input; fill errors and return None on failure."""
        host = user_input[CONF_HOST].strip()
        token = user_input[CONF_TOKEN].strip().lower()
        if not TOKEN_RE.match(token):
            errors[CONF_TOKEN] = "invalid_token_format"
            return None
        client = FountainClient(self.hass, host, token)
        try:
            info = await client.async_validate()
        except FountainAuthError:
            errors["base"] = "invalid_token"
            return None
        except FountainConnectionError:
            errors["base"] = "cannot_connect"
            return None
        except Exception:
            _LOGGER.exception("Unexpected error while validating %s", host)
            errors["base"] = "unknown"
            return None
        if info.model not in SUPPORTED_MODELS:
            _LOGGER.warning("Device at %s is a %s, not a supported model", host, info.model)
            errors["base"] = "unsupported_model"
            return None
        if unique_id_from_info(info) is None:
            errors["base"] = "cannot_identify"
            return None
        return {CONF_HOST: host, CONF_TOKEN: token}, info

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the IP address and the token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_validate(user_input, errors)
            if result is not None:
                data, info = result
                await self.async_set_unique_id(unique_id_from_info(info))
                self._abort_if_unique_id_configured(updates=data)
                return self.async_create_entry(title=DEFAULT_NAME, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input or {}),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the IP address or the token of the same device."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            result = await self._async_validate(user_input, errors)
            if result is not None:
                data, info = result
                await self.async_set_unique_id(unique_id_from_info(info))
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or dict(entry.data)),
            errors=errors,
        )


class FountainOptionsFlow(OptionsFlowWithReload):
    """Polling interval (the entry reloads when the options change)."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and save the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=1,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
