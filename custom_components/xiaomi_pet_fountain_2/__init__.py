"""Xiaomi Smart Pet Fountain 2 (xiaomi.pet_waterer.iv02), local MIoT."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant

from .api import FountainClient
from .coordinator import FountainCoordinator
from .mode_keeper import ModeKeeper, async_remove_store

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TIME,
]


@dataclass
class FountainRuntimeData:
    """Objects of a loaded entry."""

    client: FountainClient
    coordinator: FountainCoordinator
    keeper: ModeKeeper


type FountainConfigEntry = ConfigEntry[FountainRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Set up a fountain."""
    client = FountainClient(hass, entry.data[CONF_HOST], entry.data[CONF_TOKEN])
    coordinator = FountainCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    keeper = ModeKeeper(hass, entry, coordinator)
    await keeper.async_load()
    entry.runtime_data = FountainRuntimeData(client=client, coordinator=coordinator, keeper=keeper)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    keeper.async_start()
    entry.async_on_unload(keeper.async_stop)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> bool:
    """Unload a fountain."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: FountainConfigEntry) -> None:
    """Delete the stored preferred mode of a removed fountain."""
    await async_remove_store(hass, entry.entry_id)
