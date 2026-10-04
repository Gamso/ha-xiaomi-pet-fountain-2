"""Switches: power, child lock, do not disturb."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .entity import FountainEntity

PARALLEL_UPDATES = 1

SWITCHES: tuple[SwitchEntityDescription, ...] = (
    SwitchEntityDescription(key="on", translation_key="power"),
    SwitchEntityDescription(
        key="child_lock", translation_key="child_lock", entity_category=EntityCategory.CONFIG
    ),
    SwitchEntityDescription(
        key="no_disturb", translation_key="no_disturb", entity_category=EntityCategory.CONFIG
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        FountainSwitch(coordinator, description)
        for description in SWITCHES
        if coordinator.is_supported(description.key)
    )


class FountainSwitch(FountainEntity, SwitchEntity):
    """A boolean MIoT property."""

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        value = self._value()
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on."""
        await self.coordinator.async_write(self.entity_description.key, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off."""
        await self.coordinator.async_write(self.entity_description.key, False)
