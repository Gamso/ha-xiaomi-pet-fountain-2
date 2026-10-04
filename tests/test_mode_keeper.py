"""Mode keeping: the fountain forgets its mode after a power cut.

Reference scenario: the fountain runs in constant mode, loses mains
power (it comes back in auto mode), and the integration puts
constant back 10 s after mains power returns.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
)

from custom_components.xiaomi_pet_fountain_2.const import DOMAIN, EVENT_MODE_RESTORE
from custom_components.xiaomi_pet_fountain_2.mode_keeper import storage_key

from .conftest import HOST, TOKEN, UNIQUE_ID, FakeFountain, setup_entry

P = "xiaomi_smart_pet_fountain_2"
AUTO, INTERVAL, CONSTANT = 0, 1, 2
ENTRY_ID = "mock-entry"


def make_entry(**options: Any) -> MockConfigEntry:
    """Entry with a long polling interval: the tests poll by hand."""
    return MockConfigEntry(
        domain=DOMAIN,
        entry_id=ENTRY_ID,
        title="Xiaomi Smart Pet Fountain 2",
        unique_id=UNIQUE_ID,
        data={"host": HOST, "token": TOKEN},
        options={"scan_interval": 600, **options},
    )


def power_cut(fountain: FakeFountain) -> None:
    """Mains power lost: on battery, and the mode falls back to auto."""
    fountain.set(9, 6, False)
    fountain.set(5, 2, 0)
    fountain.set(2, 4, AUTO)


def power_back(fountain: FakeFountain) -> None:
    """Mains power back: charging, still in auto mode."""
    fountain.set(9, 6, True)
    fountain.set(5, 2, 1)


async def poll(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """One coordinator update."""
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def wait(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    """Let time pass."""
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def stored(hass_storage: dict[str, Any], **data: Any) -> None:
    """Pre-fill the keeper store of the test entry."""
    hass_storage[storage_key(ENTRY_ID)] = {
        "version": 1,
        "minor_version": 1,
        "key": storage_key(ENTRY_ID),
        "data": data,
    }


async def test_power_cut_restores_constant(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Battery -> mains: constant is written back after 10 s, once."""
    events = async_capture_events(hass, EVENT_MODE_RESTORE)
    entry = await setup_entry(hass, make_entry())
    keeper = entry.runtime_data.keeper
    assert keeper.preferred_mode == "constant"  # adopted from the device
    assert hass.states.get(f"switch.{P}_keep_mode").state == STATE_ON

    power_cut(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []  # on battery: wait for mains power

    power_back(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 9)
    assert fountain.mode_writes() == []  # the delay is not over

    await wait(hass, freezer, 2)
    assert fountain.mode_writes() == [CONSTANT]
    assert fountain.get(2, 4) == CONSTANT
    assert hass.states.get(f"select.{P}_mode").state == "constant"

    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["reason"] == "power_restored"
    assert state.attributes["result"] == "success"
    assert state.attributes["from_mode"] == "auto"
    assert state.attributes["to_mode"] == "constant"
    assert state.attributes["attempts"] == 1
    assert len(events) == 1
    assert events[0].data["reason"] == "power_restored"

    # Nothing more to do on the next polls
    await poll(hass, entry)
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == [CONSTANT]


async def test_charging_state_alone_detects_mains(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Without the USB property, the charging state tells the power source."""
    fountain.unsupported[(9, 6)] = -4003
    entry = await setup_entry(hass, make_entry())

    fountain.set(5, 2, 0)
    fountain.set(2, 4, AUTO)
    await poll(hass, entry)
    fountain.set(5, 2, 2)
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [CONSTANT]


async def test_reconnected_after_unavailable(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Back after being unavailable in another mode: restored."""
    entry = await setup_entry(hass, make_entry())

    fountain.online = False
    await poll(hass, entry)
    fountain.online = True
    fountain.set(2, 4, AUTO)
    await poll(hass, entry)
    await wait(hass, freezer, 11)

    assert fountain.mode_writes() == [CONSTANT]
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["reason"] == "reconnected"


async def test_startup_restores_stored_mode(
    hass: HomeAssistant,
    fountain: FakeFountain,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """At startup, a mode other than the stored preferred one is restored."""
    stored(hass_storage, preferred_mode="constant", keep_mode=True)
    fountain.set(2, 4, AUTO)
    await setup_entry(hass, make_entry())
    assert fountain.mode_writes() == []

    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [CONSTANT]
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["reason"] == "startup"


@pytest.mark.parametrize(
    ("last_restore", "expected"),
    [
        (
            {
                "time": "2026-10-01T08:00:00+00:00",
                "reason": "power_restored",
                "result": "success",
                "from_mode": "auto",
                "to_mode": "constant",
                "attempts": 1,
                "error": None,
            },
            "2026-10-01T08:00:00+00:00",
        ),
        ({"time": "not a date", "reason": "x"}, "unknown"),
        ("garbage", "unknown"),
    ],
)
async def test_last_restore_survives_restart(
    hass: HomeAssistant,
    fountain: FakeFountain,
    hass_storage: dict[str, Any],
    last_restore: Any,
    expected: str,
) -> None:
    """The last restoration is read back from the store; bad data is ignored."""
    stored(hass_storage, preferred_mode="constant", keep_mode=True, last_restore=last_restore)
    await setup_entry(hass, make_entry())
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.state == expected
    if expected != "unknown":
        assert state.attributes["reason"] == "power_restored"


async def test_startup_same_mode_does_nothing(
    hass: HomeAssistant,
    fountain: FakeFountain,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """At startup in the preferred mode, nothing is written."""
    stored(hass_storage, preferred_mode="constant")
    await setup_entry(hass, make_entry())
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []
    assert hass.states.get(f"sensor.{P}_last_mode_restoration").state == "unknown"


async def test_startup_on_battery_waits_for_mains(
    hass: HomeAssistant,
    fountain: FakeFountain,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    """Started on battery: nothing until mains power is back."""
    stored(hass_storage, preferred_mode="constant")
    power_cut(fountain)
    entry = await setup_entry(hass, make_entry())
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []

    power_back(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [CONSTANT]


async def test_mode_chosen_in_ha_becomes_preferred(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """The preferred mode follows the select; it is the one restored."""
    entry = await setup_entry(hass, make_entry())
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "interval"},
        blocking=True,
    )
    assert entry.runtime_data.keeper.preferred_mode == "interval"
    assert hass.states.get(f"sensor.{P}_preferred_mode").state == "interval"

    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [INTERVAL, INTERVAL]


async def test_refused_selection_keeps_preferred(
    hass: HomeAssistant, fountain: FakeFountain
) -> None:
    """A selection the device refuses does not change the preferred mode."""
    entry = await setup_entry(hass, make_entry())
    fountain.refuse_writes[(2, 4)] = -4002
    with pytest.raises(Exception, match="-4002"):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "auto"},
            blocking=True,
        )
    assert entry.runtime_data.keeper.preferred_mode == "constant"


async def test_selection_cancels_pending_restoration(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Choosing a mode during the delay cancels the restoration."""
    entry = await setup_entry(hass, make_entry())
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    assert entry.runtime_data.keeper.restoring

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "auto"},
        blocking=True,
    )
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == [AUTO]
    assert entry.runtime_data.keeper.preferred_mode == "auto"


async def test_external_change_is_left_alone(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Without "force", a mode changed on the device is not fought."""
    entry = await setup_entry(hass, make_entry())
    fountain.set(2, 4, AUTO)  # button on the fountain, on mains power
    for _ in range(5):
        await poll(hass, entry)
        await wait(hass, freezer, 120)
    assert fountain.mode_writes() == []
    assert hass.states.get(f"select.{P}_mode").state == "auto"
    assert entry.runtime_data.keeper.preferred_mode == "constant"


async def test_external_change_with_force(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """With "force", any difference is corrected after the delay, once."""
    entry = await setup_entry(hass, make_entry(force_mode=True))
    fountain.set(2, 4, AUTO)
    await poll(hass, entry)
    await poll(hass, entry)  # a second poll during the delay: no second episode
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [CONSTANT]
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["reason"] == "forced"

    # Even on battery
    power_cut(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [CONSTANT, CONSTANT]


async def test_attempts_are_bounded(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """A device that keeps its mode gets 3 attempts with backoff, then a failure."""
    events = async_capture_events(hass, EVENT_MODE_RESTORE)
    entry = await setup_entry(hass, make_entry())
    fountain.ignore_writes.add((2, 4))
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)

    await wait(hass, freezer, 11)
    assert len(fountain.mode_writes()) == 1
    await wait(hass, freezer, 15)  # backoff 20 s: not yet
    assert len(fountain.mode_writes()) == 1
    await wait(hass, freezer, 6)
    assert len(fountain.mode_writes()) == 2
    await wait(hass, freezer, 41)  # backoff 40 s
    assert len(fountain.mode_writes()) == 3

    await wait(hass, freezer, 3600)
    assert len(fountain.mode_writes()) == 3
    assert not entry.runtime_data.keeper.restoring
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["result"] == "failed"
    assert state.attributes["attempts"] == 3
    assert "auto" in state.attributes["error"]
    assert [e.data["result"] for e in events] == ["failed"]


async def test_retry_succeeds(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """A timeout on the first attempt is retried."""
    entry = await setup_entry(hass, make_entry())
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)

    fountain.fail_next = 1
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == []
    await wait(hass, freezer, 21)
    assert fountain.mode_writes() == [CONSTANT]
    state = hass.states.get(f"sensor.{P}_last_mode_restoration")
    assert state.attributes["result"] == "success"
    assert state.attributes["attempts"] == 2


async def test_forced_failure_pauses_forcing(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """After a failed forced restoration, forcing pauses for 10 minutes."""
    entry = await setup_entry(hass, make_entry(force_mode=True))
    fountain.ignore_writes.add((2, 4))
    fountain.set(2, 4, AUTO)
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    await wait(hass, freezer, 21)
    await wait(hass, freezer, 41)
    assert len(fountain.mode_writes()) == 3

    await poll(hass, entry)
    await wait(hass, freezer, 60)
    assert len(fountain.mode_writes()) == 3  # paused

    await wait(hass, freezer, 600)
    fountain.ignore_writes.clear()
    await poll(hass, entry)
    await wait(hass, freezer, 11)
    assert fountain.mode_writes()[-1] == CONSTANT
    assert fountain.get(2, 4) == CONSTANT


async def test_keep_switch_off(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """With the switch off, nothing is restored; the choice survives a reload."""
    entry = await setup_entry(hass, make_entry())
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: f"switch.{P}_keep_mode"}, blocking=True
    )
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []

    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(f"switch.{P}_keep_mode").state == STATE_OFF
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []


async def test_switch_off_cancels_pending(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Turning the switch off during the delay cancels the restoration."""
    entry = await setup_entry(hass, make_entry())
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: f"switch.{P}_keep_mode"}, blocking=True
    )
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []


async def test_preferred_mode_survives_restart(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """The preferred mode is stored: a reload restores it, not the device mode."""
    entry = await setup_entry(hass, make_entry())
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: f"select.{P}_mode", "option": "interval"},
        blocking=True,
    )
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    fountain.set(2, 4, AUTO)  # changed while Home Assistant was down
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.keeper.preferred_mode == "interval"
    await wait(hass, freezer, 11)
    assert fountain.get(2, 4) == INTERVAL


async def test_restore_delay_option(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """The delay comes from the options."""
    entry = await setup_entry(hass, make_entry(restore_delay=30))
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    await wait(hass, freezer, 25)
    assert fountain.mode_writes() == []
    await wait(hass, freezer, 6)
    assert fountain.mode_writes() == [CONSTANT]


async def test_unload_cancels_pending(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """Unloading the entry cancels a pending restoration."""
    entry = await setup_entry(hass, make_entry())
    power_cut(fountain)
    await poll(hass, entry)
    power_back(fountain)
    await poll(hass, entry)
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    await wait(hass, freezer, 60)
    assert fountain.mode_writes() == []


async def test_options_flow_sets_preferred_mode(
    hass: HomeAssistant, fountain: FakeFountain, freezer: FrozenDateTimeFactory
) -> None:
    """The preferred mode is editable in the options and applied."""
    entry = await setup_entry(hass, make_entry())
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "scan_interval": 600,
            "preferred_mode": "interval",
            "restore_delay": 10,
            "force_mode": False,
        },
    )
    await hass.async_block_till_done()
    assert entry.options == {"scan_interval": 600, "restore_delay": 10, "force_mode": False}
    assert entry.runtime_data.keeper.preferred_mode == "interval"
    await wait(hass, freezer, 11)
    assert fountain.mode_writes() == [INTERVAL]


async def test_options_flow_when_not_loaded(
    hass: HomeAssistant, fountain: FakeFountain, hass_storage: dict[str, Any]
) -> None:
    """Options of an entry that is not loaded still save the preferred mode."""
    entry = make_entry()
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"scan_interval": 60, "preferred_mode": "auto", "restore_delay": 5, "force_mode": True},
    )
    await hass.async_block_till_done()
    assert entry.options == {"scan_interval": 60, "restore_delay": 5, "force_mode": True}
    assert hass_storage[storage_key(entry.entry_id)]["data"]["preferred_mode"] == "auto"


async def test_removal_deletes_store(
    hass: HomeAssistant, fountain: FakeFountain, hass_storage: dict[str, Any]
) -> None:
    """Removing the entry deletes its store."""
    entry = await setup_entry(hass, make_entry())
    assert storage_key(entry.entry_id) in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert storage_key(entry.entry_id) not in hass_storage
