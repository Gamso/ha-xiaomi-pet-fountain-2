"""Sensors: pump status, filter, battery, charging state, mode keeping."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import FountainConfigEntry
from .const import CHARGING_TO_STATE, MODES, STATUS_TO_STATE
from .entity import FountainEntity, FountainKeeperEntity

PARALLEL_UPDATES = 0


def _identity(value: Any) -> Any:
    return value


@dataclass(frozen=True, kw_only=True)
class FountainSensorDescription(SensorEntityDescription):
    """Sensor reading one MIoT property."""

    value_fn: Callable[[Any], Any] = _identity


SENSORS: tuple[FountainSensorDescription, ...] = (
    FountainSensorDescription(
        key="status",
        translation_key="pump_status",
        device_class=SensorDeviceClass.ENUM,
        options=list(STATUS_TO_STATE.values()),
        value_fn=STATUS_TO_STATE.get,
    ),
    FountainSensorDescription(
        key="filter_life",
        translation_key="filter_life",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FountainSensorDescription(
        key="filter_left_time",
        translation_key="filter_left_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    FountainSensorDescription(
        key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    FountainSensorDescription(
        key="charging_state",
        translation_key="charging_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(CHARGING_TO_STATE.values()),
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=CHARGING_TO_STATE.get,
    ),
)

PREFERRED_MODE = SensorEntityDescription(
    key="preferred_mode",
    translation_key="preferred_mode",
    device_class=SensorDeviceClass.ENUM,
    options=MODES,
    entity_category=EntityCategory.DIAGNOSTIC,
)
LAST_RESTORE = SensorEntityDescription(
    key="last_mode_restore",
    translation_key="last_mode_restore",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FountainConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        FountainSensor(coordinator, description)
        for description in SENSORS
        if coordinator.is_supported(description.key)
    )
    if coordinator.is_supported("mode"):
        async_add_entities(
            [
                FountainPreferredModeSensor(coordinator, PREFERRED_MODE),
                FountainLastRestoreSensor(coordinator, LAST_RESTORE),
            ]
        )


class FountainSensor(FountainEntity, SensorEntity):
    """A read-only MIoT property."""

    entity_description: FountainSensorDescription

    @property
    def native_value(self) -> Any:
        """Return the converted value."""
        value = self._value()
        return None if value is None else self.entity_description.value_fn(value)


class FountainPreferredModeSensor(FountainKeeperEntity, SensorEntity):
    """Mode the keeper restores."""

    @property
    def native_value(self) -> str | None:
        """Return the preferred mode."""
        return self.keeper.preferred_mode


class FountainLastRestoreSensor(FountainKeeperEntity, SensorEntity):
    """Time and outcome of the last mode restoration."""

    @property
    def native_value(self) -> datetime | None:
        """Return when the last restoration ended."""
        record = self.keeper.last_restore
        return record.time if record else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Reason, outcome, modes and attempts of the last restoration."""
        record = self.keeper.last_restore
        if record is None:
            return {}
        return {
            "reason": record.reason,
            "result": record.result,
            "from_mode": record.from_mode,
            "to_mode": record.to_mode,
            "attempts": record.attempts,
            "error": record.error,
        }
