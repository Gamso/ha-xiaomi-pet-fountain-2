"""Times: start and end of the do-not-disturb period."""

from __future__ import annotations

from datetime import time

from homeassistant.components.time import TimeEntity, TimeEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .entity import FountainEntity

PARALLEL_UPDATES = 1

SECONDS_PER_DAY = 86400

TIMES: tuple[TimeEntityDescription, ...] = (
    TimeEntityDescription(
        key="no_disturb_start",
        translation_key="no_disturb_start",
        entity_category=EntityCategory.CONFIG,
    ),
    TimeEntityDescription(
        key="no_disturb_end",
        translation_key="no_disturb_end",
        entity_category=EntityCategory.CONFIG,
    ),
)


def seconds_to_time(seconds: int) -> time:
    """Seconds since midnight (0-86400) to a time of day."""
    seconds = int(seconds) % SECONDS_PER_DAY
    return time(seconds // 3600, seconds % 3600 // 60, seconds % 60)


def time_to_seconds(value: time) -> int:
    """Time of day to seconds since midnight."""
    return value.hour * 3600 + value.minute * 60 + value.second


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the time entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        FountainTime(coordinator, description)
        for description in TIMES
        if coordinator.is_supported(description.key)
    )


class FountainTime(FountainEntity, TimeEntity):
    """A time-of-day MIoT property stored in seconds."""

    @property
    def native_value(self) -> time | None:
        """Return the time."""
        value = self._value()
        return None if value is None else seconds_to_time(value)

    async def async_set_value(self, value: time) -> None:
        """Write the time."""
        await self.coordinator.async_write(self.entity_description.key, time_to_seconds(value))
