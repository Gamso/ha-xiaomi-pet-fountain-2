"""Services restore_mode and set_preferred_mode."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.xiaomi_pet_fountain_2.const import DOMAIN

from .conftest import FakeFountain, setup_entry


async def test_services_registered(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Both services exist once the integration is set up."""
    assert hass.services.has_service(DOMAIN, "restore_mode")
    assert hass.services.has_service(DOMAIN, "set_preferred_mode")


async def test_restore_mode_now(
    hass: HomeAssistant, fountain: FakeFountain, init_integration: MockConfigEntry
) -> None:
    """restore_mode writes the preferred mode immediately, even with keeping off."""
    await init_integration.runtime_data.keeper.async_set_keep_enabled(False)
    fountain.set(2, 4, 0)
    await hass.services.async_call(
        DOMAIN, "restore_mode", {"config_entry_id": init_integration.entry_id}, blocking=True
    )
    assert fountain.mode_writes() == [2]
    state = hass.states.get("sensor.xiaomi_smart_pet_fountain_2_last_mode_restoration")
    assert state.attributes["reason"] == "service"


async def test_set_preferred_mode_applies(
    hass: HomeAssistant,
    fountain: FakeFountain,
    init_integration: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """set_preferred_mode stores the mode and restores it after the delay."""
    await hass.services.async_call(
        DOMAIN,
        "set_preferred_mode",
        {"config_entry_id": init_integration.entry_id, "mode": "auto"},
        blocking=True,
    )
    assert init_integration.runtime_data.keeper.preferred_mode == "auto"
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert fountain.mode_writes() == [0]


async def test_service_validation(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """Unknown or unloaded entries and invalid modes are rejected."""
    entry = await setup_entry(hass, config_entry)
    with pytest.raises(ServiceValidationError, match="unknown"):
        await hass.services.async_call(
            DOMAIN, "restore_mode", {"config_entry_id": "unknown"}, blocking=True
        )
    with pytest.raises(Exception, match="mode"):
        await hass.services.async_call(
            DOMAIN,
            "set_preferred_mode",
            {"config_entry_id": entry.entry_id, "mode": "turbo"},
            blocking=True,
        )

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as exc:
        await hass.services.async_call(
            DOMAIN, "restore_mode", {"config_entry_id": entry.entry_id}, blocking=True
        )
    assert exc.value.translation_key == "entry_not_loaded"
