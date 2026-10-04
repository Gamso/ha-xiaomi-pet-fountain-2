"""Select: water mode (auto / interval / constant)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .const import MODE_TO_VALUE, MODES, VALUE_TO_MODE
from .entity import FountainEntity

PARALLEL_UPDATES = 1

MODE_DESCRIPTION = SelectEntityDescription(key="mode", translation_key="mode", options=MODES)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the mode select."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.is_supported("mode"):
        async_add_entities([FountainModeSelect(coordinator, MODE_DESCRIPTION)])


class FountainModeSelect(FountainEntity, SelectEntity):
    """Mode of the pump: sensor (auto), interval or constant.

    A mode chosen here becomes the preferred mode of the mode keeper.
    """

    @property
    def current_option(self) -> str | None:
        """Return the current mode."""
        return VALUE_TO_MODE.get(self._value())

    async def async_select_option(self, option: str) -> None:
        """Change the mode and remember it as the preferred one."""
        keeper = self.coordinator.config_entry.runtime_data.keeper
        keeper.async_cancel()
        await self.coordinator.async_write("mode", MODE_TO_VALUE[option])
        await keeper.async_set_preferred_mode(option, apply=False)
