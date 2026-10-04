"""Xiaomi Smart Pet Fountain 2 (xiaomi.pet_waterer.iv02), local MIoT."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import HomeAssistant

from .api import FountainClient


@dataclass
class FountainRuntimeData:
    """Objects of a loaded entry."""

    client: FountainClient


type FountainConfigEntry = ConfigEntry[FountainRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Set up a fountain."""
    client = FountainClient(hass, entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    entry.runtime_data = FountainRuntimeData(client=client)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Unload a fountain."""
    return True
