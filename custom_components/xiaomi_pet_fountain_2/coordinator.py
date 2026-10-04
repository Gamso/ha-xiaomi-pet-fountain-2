"""Polling of the fountain."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import FountainClient, FountainError, FountainInfo
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    POLLED_PROPERTIES,
    PROPERTIES_BY_KEY,
    MiotProperty,
)

if TYPE_CHECKING:
    from . import FountainConfigEntry

_LOGGER = logging.getLogger(__name__)


class FountainCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Reads every polled property; data maps property keys to raw MIoT values."""

    config_entry: FountainConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: FountainConfigEntry, client: FountainClient
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {client.host}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client
        self.info: FountainInfo | None = None
        # Properties this firmware answers; set by the first successful read
        # (entities are only created for them).
        self.supported: set[str] = set()
        self.unsupported: dict[str, int] = {}

    async def _async_setup(self) -> None:
        """Identify the device once, before the first read."""
        try:
            self.info = await self.client.async_info()
        except FountainError as err:
            raise UpdateFailed(f"Cannot read the device information: {err}") from err

    async def _async_update_data(self) -> dict[str, Any]:
        """Read the properties."""
        try:
            values, errors = await self.client.async_get_properties(POLLED_PROPERTIES)
        except FountainError as err:
            raise UpdateFailed(f"Error communicating with the fountain: {err}") from err
        if not self.supported:
            self.supported = set(values)
            self.unsupported = errors
            if errors:
                _LOGGER.debug("Properties not supported by this firmware: %s", errors)
        elif errors:
            _LOGGER.debug("Properties not returned this time: %s", errors)
        return values

    def is_supported(self, key: str) -> bool:
        """Whether the device answered this property on the first read."""
        return key in self.supported

    async def async_write(self, key: str, value: Any) -> None:
        """Write a property, then show the new value right away."""
        prop: MiotProperty = PROPERTIES_BY_KEY[key]
        try:
            await self.client.async_set_property(prop, value)
        except FountainError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"property": key, "error": str(err)},
            ) from err
        self.async_set_value(key, value)

    def async_set_value(self, key: str, value: Any) -> None:
        """Store a value known from a successful write and notify the entities."""
        if self.data is not None:
            self.data[key] = value
            self.async_update_listeners()

    async def async_call_action(self, siid: int, aiid: int) -> None:
        """Run an action, then read the properties again."""
        try:
            await self.client.async_call_action(siid, aiid)
        except FountainError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="action_failed",
                translation_placeholders={"action": f"{siid}.{aiid}", "error": str(err)},
            ) from err
        await self.async_request_refresh()
