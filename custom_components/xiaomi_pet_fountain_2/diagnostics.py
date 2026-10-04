"""Diagnostics download (token, address and identifiers redacted)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import HomeAssistant

from . import FountainConfigEntry

TO_REDACT = {CONF_TOKEN, CONF_HOST, "unique_id", "mac", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FountainConfigEntry
) -> dict[str, Any]:
    """Return the diagnostics of a fountain."""
    runtime = entry.runtime_data
    coordinator = runtime.coordinator
    info = coordinator.info
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "device": async_redact_data(asdict(info), TO_REDACT) if info else None,
        "last_update_success": coordinator.last_update_success,
        "supported_properties": sorted(coordinator.supported),
        "unsupported_properties": coordinator.unsupported,
        "data": coordinator.data,
        "mode_keeper": runtime.keeper.as_diagnostics(),
    }
