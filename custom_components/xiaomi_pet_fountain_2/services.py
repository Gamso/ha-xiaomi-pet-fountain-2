"""Services of the integration (mode keeping)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .const import DOMAIN, MODES

if TYPE_CHECKING:
    from . import FountainConfigEntry

SERVICE_RESTORE_MODE = "restore_mode"
SERVICE_SET_PREFERRED_MODE = "set_preferred_mode"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_MODE = "mode"

RESTORE_MODE_SCHEMA = vol.Schema({vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string})
SET_PREFERRED_MODE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Required(ATTR_MODE): vol.In(MODES),
    }
)


def _loaded_entry(hass: HomeAssistant, call: ServiceCall) -> FountainConfigEntry:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"title": entry.title},
        )
    return entry


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services (once, for every fountain)."""

    async def restore_mode(call: ServiceCall) -> None:
        keeper = _loaded_entry(hass, call).runtime_data.keeper
        if keeper.preferred_mode is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="no_preferred_mode"
            )
        await keeper.async_restore_now()

    async def set_preferred_mode(call: ServiceCall) -> None:
        keeper = _loaded_entry(hass, call).runtime_data.keeper
        await keeper.async_set_preferred_mode(call.data[ATTR_MODE], apply=True)

    hass.services.async_register(
        DOMAIN, SERVICE_RESTORE_MODE, restore_mode, schema=RESTORE_MODE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN, SERVICE_SET_PREFERRED_MODE, set_preferred_mode, schema=SET_PREFERRED_MODE_SCHEMA
    )
