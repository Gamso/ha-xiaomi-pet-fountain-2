"""Xiaomi Smart Pet Fountain 2 (xiaomi.pet_waterer.iv02), local MIoT."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import HomeAssistant

from .api import FountainClient
from .coordinator import FountainCoordinator


@dataclass
class FountainRuntimeData:
    """Objects of a loaded entry."""

    client: FountainClient
    coordinator: FountainCoordinator


type FountainConfigEntry = ConfigEntry[FountainRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Set up a fountain."""
    client = FountainClient(hass, entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    coordinator = FountainCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = FountainRuntimeData(client=client, coordinator=coordinator)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Unload a fountain."""
    return True
