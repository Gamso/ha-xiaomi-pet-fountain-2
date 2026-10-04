"""Button: reset the filter life."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .const import ACTION_RESET_FILTER
from .entity import FountainEntity

PARALLEL_UPDATES = 1

RESET_FILTER = ButtonEntityDescription(
    key="reset_filter", translation_key="reset_filter", entity_category=EntityCategory.CONFIG
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button."""
    async_add_entities([FountainResetFilterButton(entry.runtime_data.coordinator, RESET_FILTER)])


class FountainResetFilterButton(FountainEntity, ButtonEntity):
    """Run the reset-filter-life action (siid 3, aiid 1)."""

    @property
    def available(self) -> bool:
        """Available while the device answers (no property behind it)."""
        return self.coordinator.last_update_success

    async def async_press(self) -> None:
        """Reset the filter life."""
        await self.coordinator.async_call_action(*ACTION_RESET_FILTER)
