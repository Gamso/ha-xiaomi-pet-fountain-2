"""Base entity of the fountain."""

from __future__ import annotations

from typing import Any, Final

from homeassistant.const import Platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DEFAULT_NAME, DOMAIN, MANUFACTURER, MODEL_NAME
from .coordinator import FountainCoordinator
from .mode_keeper import ModeKeeper

# English entity id of every entity, by entity description key: platform and
# object id after the device name (switch.xiaomi_smart_pet_fountain_2_power).
# They are the ids the README documents: keep them when a name changes.
OBJECT_IDS: Final[dict[str, tuple[Platform, str]]] = {
    "on": (Platform.SWITCH, "power"),
    "child_lock": (Platform.SWITCH, "child_lock"),
    "no_disturb": (Platform.SWITCH, "do_not_disturb"),
    "mode": (Platform.SELECT, "mode"),
    "status": (Platform.SENSOR, "pump_status"),
    "filter_life": (Platform.SENSOR, "filter_life"),
    "filter_left_time": (Platform.SENSOR, "filter_time_left"),
    "battery_level": (Platform.SENSOR, "battery"),
    "charging_state": (Platform.SENSOR, "charging_state"),
    "water_shortage": (Platform.BINARY_SENSOR, "water_shortage"),
    "pump_blocked": (Platform.BINARY_SENSOR, "pump_blocked"),
    "fault": (Platform.BINARY_SENSOR, "fault"),
    "low_battery": (Platform.BINARY_SENSOR, "low_battery"),
    "usb_power": (Platform.BINARY_SENSOR, "mains_power"),
    "out_water_interval": (Platform.NUMBER, "water_interval"),
    "out_water_interval_2": (Platform.NUMBER, "water_interval_5_min_steps"),
    "no_disturb_start": (Platform.TIME, "do_not_disturb_start"),
    "no_disturb_end": (Platform.TIME, "do_not_disturb_end"),
    "reset_filter": (Platform.BUTTON, "reset_filter"),
    # Mode keeping (see mode_keeper.py)
    "keep_mode": (Platform.SWITCH, "keep_mode"),
    "preferred_mode": (Platform.SENSOR, "preferred_mode"),
    "last_mode_restore": (Platform.SENSOR, "last_mode_restoration"),
}


def _device_slug(coordinator: FountainCoordinator) -> str:
    """Slug of the device name, as renamed by the user if it was."""
    entry = coordinator.config_entry
    devices = dr.async_entries_for_config_entry(dr.async_get(coordinator.hass), entry.entry_id)
    renamed = next((device.name_by_user for device in devices if device.name_by_user), None)
    return slugify(renamed or entry.title) or slugify(DEFAULT_NAME)


class FountainEntity(CoordinatorEntity[FountainCoordinator]):
    """An entity of the fountain device, named by its translation key.

    The name follows the language of Home Assistant, but the entity id is
    pinned to the English one: for the languages it supports natively
    (French included), Home Assistant would derive it from the translated
    name (switch.xiaomi_smart_pet_fountain_2_marche), while the documented
    ids, dashboards and shared automations use the English ones. Home
    Assistant takes an entity id set before the entity is added as the
    suggested one: it only applies when the entity is first registered (the
    registry keeps an existing or renamed id, a taken id gets a _2 suffix)
    and it is the id that "Recreate entity IDs" gives back.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: FountainCoordinator, description: EntityDescription) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self.entity_description = description
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.unique_id}_{description.key}"
        info = coordinator.info
        connections = set()
        if info is not None and info.mac:
            connections.add((CONNECTION_NETWORK_MAC, info.mac.lower()))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(entry.unique_id))},
            connections=connections,
            manufacturer=MANUFACTURER,
            model=MODEL_NAME,
            model_id=info.model if info else None,
            sw_version=info.firmware if info else None,
            hw_version=info.hardware if info else None,
            name=entry.title,
        )
        platform, object_id = OBJECT_IDS[description.key]
        self.entity_id = f"{platform}.{_device_slug(coordinator)}_{object_id}"

    def _value(self, key: str | None = None) -> Any:
        """Raw value of a property (the entity's own by default)."""
        data = self.coordinator.data or {}
        return data.get(key or self.entity_description.key)

    @property
    def available(self) -> bool:
        """Unavailable while the device does not answer or omits the value."""
        return super().available and self._value() is not None


class FountainKeeperEntity(FountainEntity):
    """An entity of the mode keeper: local state, available while loaded."""

    @property
    def keeper(self) -> ModeKeeper:
        """The mode keeper of the entry."""
        return self.coordinator.config_entry.runtime_data.keeper

    @property
    def available(self) -> bool:
        """Always available: the state lives in Home Assistant."""
        return True

    async def async_added_to_hass(self) -> None:
        """Follow the keeper state."""
        await super().async_added_to_hass()
        self.async_on_remove(self.keeper.async_add_listener(self.async_write_ha_state))
