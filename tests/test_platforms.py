"""Entities of every platform, read and write."""

from __future__ import annotations

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_pet_fountain_2.const import DOMAIN

from .conftest import UNIQUE_ID, FakeFountain, setup_entry

P = "xiaomi_smart_pet_fountain_2"

# Every entity id the README documents, whatever the instance language.
ENTITY_IDS = sorted(
    [
        f"switch.{P}_power",
        f"switch.{P}_child_lock",
        f"switch.{P}_do_not_disturb",
        f"select.{P}_mode",
        f"sensor.{P}_pump_status",
        f"sensor.{P}_filter_life",
        f"sensor.{P}_filter_time_left",
        f"sensor.{P}_battery",
        f"sensor.{P}_charging_state",
        f"binary_sensor.{P}_water_shortage",
        f"binary_sensor.{P}_pump_blocked",
        f"binary_sensor.{P}_fault",
        f"binary_sensor.{P}_low_battery",
        f"binary_sensor.{P}_mains_power",
        f"number.{P}_water_interval",
        f"number.{P}_water_interval_5_min_steps",
        f"time.{P}_do_not_disturb_start",
        f"time.{P}_do_not_disturb_end",
        f"button.{P}_reset_filter",
        f"switch.{P}_keep_mode",
        f"sensor.{P}_preferred_mode",
        f"sensor.{P}_last_mode_restoration",
    ]
)


@pytest.mark.usefixtures("init_integration")
async def test_states(hass: HomeAssistant) -> None:
    """Every entity reflects the simulated device."""
    expected = {
        f"switch.{P}_power": STATE_ON,
        f"switch.{P}_child_lock": STATE_OFF,
        f"switch.{P}_do_not_disturb": STATE_OFF,
        f"select.{P}_mode": "constant",
        f"sensor.{P}_pump_status": "watering",
        f"sensor.{P}_filter_life": "80",
        f"sensor.{P}_filter_time_left": "45",
        f"sensor.{P}_battery": "100",
        f"sensor.{P}_charging_state": "charge_full",
        f"binary_sensor.{P}_water_shortage": STATE_OFF,
        f"binary_sensor.{P}_pump_blocked": STATE_OFF,
        f"binary_sensor.{P}_fault": STATE_OFF,
        f"binary_sensor.{P}_low_battery": STATE_OFF,
        f"binary_sensor.{P}_mains_power": STATE_ON,
        f"number.{P}_water_interval": "15.0",
        f"number.{P}_water_interval_5_min_steps": "30.0",
        f"time.{P}_do_not_disturb_start": "22:00:00",
        f"time.{P}_do_not_disturb_end": "07:00:00",
    }
    actual = {entity_id: hass.states.get(entity_id) for entity_id in expected}
    assert {k: v.state if v else None for k, v in actual.items()} == expected
    assert hass.states.get(f"button.{P}_reset_filter") is not None


async def test_device_and_unique_ids(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """One device, identified by its MAC; unique_ids derive from it."""
    devices = dr.async_entries_for_config_entry(device_registry, init_integration.entry_id)
    assert len(devices) == 1
    device = devices[0]
    assert device.identifiers == {("xiaomi_pet_fountain_2", UNIQUE_ID)}
    assert device.model_id == "xiaomi.pet_waterer.iv02"
    assert device.sw_version == "1.0.0_0042"
    assert (dr.CONNECTION_NETWORK_MAC, UNIQUE_ID) in device.connections
    entry = entity_registry.async_get(f"select.{P}_mode")
    assert entry is not None
    assert entry.unique_id == f"{UNIQUE_ID}_mode"
    assert entry.translation_key == "mode"


@pytest.mark.parametrize("language", ["en", "fr"])
async def test_entity_ids_in_english(
    hass: HomeAssistant,
    fountain: FakeFountain,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    language: str,
) -> None:
    """The entity ids are the English ones, whatever the instance language.

    Names follow the language, but Home Assistant would derive the French
    ids from them (switch.xiaomi_smart_pet_fountain_2_marche).
    """
    hass.config.language = language
    await setup_entry(hass, config_entry)
    entries = er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    assert sorted(entry.entity_id for entry in entries) == ENTITY_IDS
    state = hass.states.get(f"switch.{P}_power")
    assert state is not None
    assert state.name == (
        "Xiaomi Smart Pet Fountain 2 Marche"
        if language == "fr"
        else "Xiaomi Smart Pet Fountain 2 Power"
    )


async def test_second_fountain_entity_ids(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """A second fountain with the same name gets distinct ids (_2 suffix)."""
    hass.config.language = "fr"
    await setup_entry(hass, config_entry)
    fountain.mac = None  # its own device, not merged by the MAC connection
    second = MockConfigEntry(
        domain=DOMAIN,
        title=config_entry.title,
        unique_id="11:22:33:44:55:66",
        data=dict(config_entry.data),
    )
    await setup_entry(hass, second)
    assert hass.states.get(f"switch.{P}_power") is not None
    assert hass.states.get(f"switch.{P}_power_2") is not None
    assert hass.states.get(f"select.{P}_mode_2") is not None


async def test_existing_entity_id_kept_then_recreated(
    hass: HomeAssistant,
    fountain: FakeFountain,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """A registered French id is not renamed; recreating it gives the English one.

    async_regenerate_entity_id is what "Recreate entity IDs" of the device
    page uses. It follows a device renamed by the user.
    """
    hass.config.language = "fr"
    config_entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "switch",
        DOMAIN,
        f"{UNIQUE_ID}_on",
        config_entry=config_entry,
        suggested_object_id=f"{P}_marche",
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    entry = entity_registry.async_get(f"switch.{P}_marche")
    assert entry is not None
    assert hass.states.get(f"switch.{P}_marche") is not None
    assert hass.states.get(f"switch.{P}_power") is None
    assert entity_registry.async_regenerate_entity_id(entry) == f"switch.{P}_power"

    [device] = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    device_registry.async_update_device(device.id, name_by_user="Fontaine salon")
    assert await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    entry = entity_registry.async_get(f"switch.{P}_marche")
    assert entry is not None
    assert entity_registry.async_regenerate_entity_id(entry) == "switch.fontaine_salon_power"


async def test_unsupported_property_has_no_entity(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """No entity for a property the firmware does not answer (spec v1 device)."""
    fountain.unsupported[(2, 11)] = -4003
    await setup_entry(hass, config_entry)
    assert hass.states.get(f"number.{P}_water_interval_5_min_steps") is None
    assert hass.states.get(f"number.{P}_water_interval") is not None


@pytest.mark.usefixtures("init_integration")
async def test_switches_write(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Switches write their boolean property."""
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: f"switch.{P}_power"}, blocking=True
    )
    await hass.services.async_call(
        "switch", "turn_on", {ATTR_ENTITY_ID: f"switch.{P}_child_lock"}, blocking=True
    )
    assert fountain.get(2, 1) is False
    assert fountain.get(4, 1) is True
    assert hass.states.get(f"switch.{P}_power").state == STATE_OFF
    assert hass.states.get(f"switch.{P}_child_lock").state == STATE_ON


@pytest.mark.usefixtures("init_integration")
async def test_select_mode_write(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """The mode select writes 0/1/2 to 2.4."""
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "interval"},
        blocking=True,
    )
    assert fountain.get(2, 4) == 1
    assert hass.states.get(f"select.{P}_mode").state == "interval"


@pytest.mark.usefixtures("init_integration")
async def test_write_refused_raises(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """A refused write surfaces as an error and keeps the state."""
    fountain.refuse_writes[(2, 4)] = -4002
    with pytest.raises(HomeAssistantError, match="-4002"):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "auto"},
            blocking=True,
        )
    assert hass.states.get(f"select.{P}_mode").state == "constant"


@pytest.mark.usefixtures("init_integration")
async def test_number_and_time_write(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Numbers write minutes; times write seconds since midnight."""
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: f"number.{P}_water_interval", "value": 45},
        blocking=True,
    )
    await hass.services.async_call(
        "time",
        "set_value",
        {ATTR_ENTITY_ID: f"time.{P}_do_not_disturb_start", "time": "21:30:00"},
        blocking=True,
    )
    assert fountain.get(2, 7) == 45
    assert fountain.get(9, 10) == 21 * 3600 + 30 * 60
    assert hass.states.get(f"time.{P}_do_not_disturb_start").state == "21:30:00"


@pytest.mark.usefixtures("init_integration")
async def test_reset_filter_button(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """The button runs action 3.1 and the new filter values are read back."""
    await hass.services.async_call(
        "button", "press", {ATTR_ENTITY_ID: f"button.{P}_reset_filter"}, blocking=True
    )
    await hass.async_block_till_done()
    assert fountain.actions == [(3, 1)]
    assert hass.states.get(f"sensor.{P}_filter_life").state == "100"


async def test_enum_values_and_missing_value(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """Enum sensors map the raw values; a value missing later is unavailable."""
    fountain.set(5, 2, 0)
    fountain.set(2, 3, 1)
    fountain.set(2, 10, True)
    entry = await setup_entry(hass, config_entry)
    assert hass.states.get(f"sensor.{P}_charging_state").state == "no_charge"
    assert hass.states.get(f"sensor.{P}_pump_status").state == "waterless"
    assert hass.states.get(f"binary_sensor.{P}_water_shortage").state == STATE_ON

    fountain.unsupported[(3, 1)] = -4001
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{P}_filter_life").state == STATE_UNAVAILABLE


async def test_entities_unavailable_when_offline(
    hass: HomeAssistant, fountain: FakeFountain, init_integration: MockConfigEntry
) -> None:
    """A failed poll makes the entities unavailable."""
    fountain.online = False
    await init_integration.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"select.{P}_mode").state == STATE_UNAVAILABLE
    assert hass.states.get(f"button.{P}_reset_filter").state == STATE_UNAVAILABLE
