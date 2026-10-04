"""Config flow, reconfigure flow and options flow."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_pet_fountain_2.const import DOMAIN

from .conftest import HOST, TOKEN, UNIQUE_ID, FakeFountain


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result["flow_id"]


async def test_user_flow_success(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """A reachable fountain with the right token creates the entry."""
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: f" {HOST} ", CONF_TOKEN: TOKEN.upper()}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Xiaomi Smart Pet Fountain 2"
    assert result["data"] == {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    assert result["result"].unique_id == UNIQUE_ID
    # The validation really talked to the device
    assert ("miIO.info", []) in fountain.requests


@pytest.mark.parametrize("token", ["1234", "z" * 32, "0123456789abcdef0123456789abcdef0"])
async def test_user_flow_bad_token_format(
    hass: HomeAssistant, fountain: FakeFountain, token: str
) -> None:
    """A malformed token is rejected before any network call."""
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: token}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_TOKEN: "invalid_token_format"}
    assert fountain.requests == []


async def test_user_flow_cannot_connect(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """No handshake answer: cannot_connect, then the user can retry."""
    fountain.online = False
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}

    fountain.online = True
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_invalid_token(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Handshake answered but encrypted request ignored: invalid_token."""
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: "f" * 32}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_token"}


async def test_user_flow_unsupported_model(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Another Xiaomi device is refused."""
    fountain.model = "xiaomi.pet_waterer.70m2"
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "unsupported_model"}


async def test_user_flow_unique_id_without_mac(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Without a MAC address, the device ID (1.3) identifies the fountain."""
    fountain.mac = None
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "did_123456789"


async def test_user_flow_cannot_identify(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Neither MAC nor device ID: no stable unique_id, no entry."""
    fountain.mac = None
    fountain.unsupported[(1, 3)] = -4003
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["errors"] == {"base": "cannot_identify"}


async def test_user_flow_unknown_error(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """An unexpected exception is reported as unknown."""
    flow_id = await _start(hass)
    with patch(
        "custom_components.xiaomi_pet_fountain_2.config_flow.FountainClient.async_validate",
        side_effect=RuntimeError("boom"),
    ):
        result = await hass.config_entries.flow.async_configure(
            flow_id, {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
        )
    assert result["errors"] == {"base": "unknown"}


async def test_user_flow_duplicate_updates_host(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """The same fountain at a new address aborts and updates the address."""
    config_entry.add_to_hass(hass)
    flow_id = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        flow_id, {CONF_HOST: "192.168.1.99", CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert config_entry.data[CONF_HOST] == "192.168.1.99"


async def test_reconfigure(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """Reconfigure changes the address of the same device."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.77", CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data[CONF_HOST] == "192.168.1.77"

    # The flow reloads the entry in the background: let the reload finish,
    # then unload so its coordinator timer does not outlive the test.
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.LOADED
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_reconfigure_wrong_device(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """Reconfigure refuses another device."""
    config_entry.add_to_hass(hass)
    fountain.mac = "11:22:33:44:55:66"
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"


async def test_reconfigure_error(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """Reconfigure shows the validation errors."""
    config_entry.add_to_hass(hass)
    fountain.online = False
    result = await config_entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST, CONF_TOKEN: TOKEN}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_options_flow(
    hass: HomeAssistant, fountain: FakeFountain, config_entry: MockConfigEntry
) -> None:
    """The polling interval is saved in the options."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"scan_interval": 60}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["scan_interval"] == 60
