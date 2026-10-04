"""Setup, unload and polling."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import FakeFountain


async def test_setup_and_unload(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """The entry loads, reads the device, and unloads cleanly."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED

    coordinator = config_entry.runtime_data.coordinator
    assert coordinator.info is not None
    assert coordinator.info.model == "xiaomi.pet_waterer.iv02"
    assert coordinator.data["mode"] == 2
    assert coordinator.is_supported("out_water_interval_2")

    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_when_offline(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """An unreachable fountain puts the entry in setup retry."""
    fountain.online = False
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unsupported_properties_are_remembered(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """A property the firmware does not answer is marked unsupported."""
    fountain.unsupported[(2, 11)] = -4003
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    coordinator = config_entry.runtime_data.coordinator
    assert not coordinator.is_supported("out_water_interval_2")
    assert coordinator.unsupported == {"out_water_interval_2": -4003}


async def test_polling_failure_and_recovery(
    hass: HomeAssistant,
    fountain: FakeFountain,
    config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A failed poll marks the data stale; the next good poll recovers."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    coordinator.async_add_listener(lambda: None)

    fountain.online = False
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not coordinator.last_update_success

    fountain.online = True
    fountain.set(2, 4, 0)
    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert coordinator.data["mode"] == 0
