"""Numbers: water interval (two properties, see the README)."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .entity import FountainEntity

PARALLEL_UPDATES = 1

NUMBERS: tuple[NumberEntityDescription, ...] = (
    # 2.7 out-water-interval: 0-120 min, step 15 (spec v1 and v2)
    NumberEntityDescription(
        key="out_water_interval",
        translation_key="out_water_interval",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=0,
        native_max_value=120,
        native_step=15,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    # 2.11 out-water-interval: 10-120 min, step 5 (added by spec v2)
    NumberEntityDescription(
        key="out_water_interval_2",
        translation_key="out_water_interval_2",
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        native_min_value=10,
        native_max_value=120,
        native_step=5,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the numbers."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        FountainNumber(coordinator, description)
        for description in NUMBERS
        if coordinator.is_supported(description.key)
    )


class FountainNumber(FountainEntity, NumberEntity):
    """A numeric MIoT property."""

    @property
    def native_value(self) -> float | None:
        """Return the value."""
        value = self._value()
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Write the value."""
        await self.coordinator.async_write(self.entity_description.key, round(value))
