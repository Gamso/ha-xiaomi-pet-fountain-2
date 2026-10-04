"""Config flow for the Xiaomi Smart Pet Fountain 2."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
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
    CONF_FORCE_MODE,
    CONF_PREFERRED_MODE,
    CONF_RESTORE_DELAY,
    CONF_SCAN_INTERVAL,
    DEFAULT_NAME,
    DEFAULT_RESTORE_DELAY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_RESTORE_DELAY,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODES,
    SUPPORTED_MODELS,
)
from .mode_keeper import async_read_preferred_mode, async_store_preferred_mode

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
    """Polling and mode keeping options (the entry reloads when they change).

    The preferred mode is not an option: it lives in the mode keeper store,
    because the mode select also changes it. The form only edits it.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show and save the options."""
        entry = self.config_entry
        loaded = entry.state is ConfigEntryState.LOADED
        if user_input is not None:
            preferred = user_input.pop(CONF_PREFERRED_MODE, None)
            if preferred is not None:
                if loaded:
                    keeper = entry.runtime_data.keeper
                    if preferred != keeper.preferred_mode:
                        await keeper.async_set_preferred_mode(preferred, apply=True)
                else:
                    await async_store_preferred_mode(self.hass, entry, preferred)
            return self.async_create_entry(
                data={
                    CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    CONF_RESTORE_DELAY: int(user_input[CONF_RESTORE_DELAY]),
                    CONF_FORCE_MODE: bool(user_input[CONF_FORCE_MODE]),
                }
            )

        if loaded:
            preferred = entry.runtime_data.keeper.preferred_mode
        else:
            preferred = await async_read_preferred_mode(self.hass, entry)
        options = entry.options
        fields: dict[Any, Any] = {
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
            vol.Optional(
                CONF_PREFERRED_MODE,
                description={"suggested_value": preferred},
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=MODES,
                    translation_key=CONF_PREFERRED_MODE,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_RESTORE_DELAY,
                default=options.get(CONF_RESTORE_DELAY, DEFAULT_RESTORE_DELAY),
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0,
                    max=MAX_RESTORE_DELAY,
                    step=1,
                    unit_of_measurement="s",
                    mode=selector.NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_FORCE_MODE, default=options.get(CONF_FORCE_MODE, False)
            ): selector.BooleanSelector(),
        }
        return self.async_show_form(step_id="init", data_schema=vol.Schema(fields))
