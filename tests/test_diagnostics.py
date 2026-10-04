"""Diagnostics."""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_pet_fountain_2.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import HOST, TOKEN, UNIQUE_ID


async def test_diagnostics_redacts_secrets(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The token, the address and the identifiers never leave Home Assistant."""
    diagnostics = await async_get_config_entry_diagnostics(hass, init_integration)
    dumped = json.dumps(diagnostics, default=str)
    for secret in (TOKEN, HOST, UNIQUE_ID, "AA:BB:CC:DD:EE:FF"):
        assert secret not in dumped
    assert diagnostics["entry"]["data"]["token"] == "**REDACTED**"
    assert diagnostics["device"]["model"] == "xiaomi.pet_waterer.iv02"
    assert diagnostics["data"]["mode"] == 2
    assert "out_water_interval_2" in diagnostics["supported_properties"]
    assert diagnostics["mode_keeper"]["preferred_mode"] == "constant"
    assert diagnostics["mode_keeper"]["keep_enabled"] is True
