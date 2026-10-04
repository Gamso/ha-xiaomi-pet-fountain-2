"""MIoT client over python-miio (simulated device)."""

from __future__ import annotations

import time
from unittest.mock import patch

from homeassistant.core import HomeAssistant
from miio.exceptions import DeviceError
import pytest

from custom_components.xiaomi_pet_fountain_2.api import (
    FountainAuthError,
    FountainClient,
    FountainCommandError,
    FountainConnectionError,
)
from custom_components.xiaomi_pet_fountain_2.const import (
    POLLED_PROPERTIES,
    PROP_MODE,
    PROPERTIES_PER_REQUEST,
)

from .conftest import HOST, TOKEN, FakeFountain


async def test_get_properties_chunks_and_codes(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Properties are read a few per request; error codes are reported apart."""
    fountain.unsupported[(2, 11)] = -4003
    client = FountainClient(hass, HOST, TOKEN)
    values, errors = await client.async_get_properties(POLLED_PROPERTIES)

    requests = [params for command, params in fountain.requests if command == "get_properties"]
    assert len(requests) == -(-len(POLLED_PROPERTIES) // PROPERTIES_PER_REQUEST)
    assert all(len(r) <= PROPERTIES_PER_REQUEST for r in requests)
    assert values["mode"] == 2
    assert values["usb_power"] is True
    assert "out_water_interval_2" not in values
    assert errors == {"out_water_interval_2": -4003}


async def test_set_property_and_refusal(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """A write answered with a non-zero code raises FountainCommandError."""
    client = FountainClient(hass, HOST, TOKEN)
    await client.async_set_property(PROP_MODE, 0)
    assert fountain.get(2, 4) == 0

    fountain.refuse_writes[(2, 4)] = -4002
    with pytest.raises(FountainCommandError, match="-4002"):
        await client.async_set_property(PROP_MODE, 1)
    assert fountain.get(2, 4) == 0


async def test_action(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Actions are sent as MIoT actions."""
    client = FountainClient(hass, HOST, TOKEN)
    await client.async_call_action(3, 1)
    assert fountain.actions == [(3, 1)]


async def test_errors_are_mapped(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """python-miio errors become FountainConnectionError / FountainCommandError."""
    client = FountainClient(hass, HOST, TOKEN)
    fountain.online = False
    with pytest.raises(FountainConnectionError):
        await client.async_get_properties([PROP_MODE])
    with pytest.raises(FountainConnectionError) as exc:
        await client.async_validate()
    assert not isinstance(exc.value, FountainAuthError)

    fountain.online = True
    with (
        patch.object(fountain, "send", side_effect=DeviceError({"code": -1, "message": "x"})),
        pytest.raises(FountainCommandError),
    ):
        await client.async_get_properties([PROP_MODE])


async def test_wrong_token_is_auth_error(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """Handshake answered, encrypted request not: FountainAuthError."""
    client = FountainClient(hass, HOST, "f" * 32)
    with pytest.raises(FountainAuthError):
        await client.async_validate()


async def test_call_timeout(hass: HomeAssistant, fountain: FakeFountain) -> None:
    """A call that hangs is cut by the asyncio timeout."""
    client = FountainClient(hass, HOST, TOKEN)

    def slow(*args: object) -> None:
        time.sleep(0.3)

    with (
        patch("custom_components.xiaomi_pet_fountain_2.api.CALL_TIMEOUT", 0.05),
        patch.object(fountain, "send", side_effect=slow),
        pytest.raises(FountainConnectionError, match="within"),
    ):
        await client.async_get_properties([PROP_MODE])
