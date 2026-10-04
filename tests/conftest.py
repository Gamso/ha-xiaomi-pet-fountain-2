"""Fixtures: a simulated fountain behind python-miio's Device class."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from miio import DeviceException
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xiaomi_pet_fountain_2.const import DOMAIN

HOST = "192.168.1.50"
TOKEN = "0123456789abcdef0123456789abcdef"
MAC = "AA:BB:CC:DD:EE:FF"
UNIQUE_ID = "aa:bb:cc:dd:ee:ff"

# siid, piid -> value: a fountain on mains power, in constant mode.
DEFAULT_PROPERTIES: dict[tuple[int, int], Any] = {
    (1, 3): "123456789",
    (2, 1): True,
    (2, 2): 0,
    (2, 3): 2,
    (2, 4): 2,
    (2, 7): 15,
    (2, 10): False,
    (2, 11): 30,
    (3, 1): 80,
    (3, 2): 45,
    (4, 1): False,
    (5, 1): 100,
    (5, 2): 2,
    (6, 1): False,
    (9, 5): False,
    (9, 6): True,
    (9, 10): 79200,
    (9, 11): 25200,
    (9, 12): False,
}


class FakeFountain:
    """State and behaviour of the simulated device, shared by every client."""

    def __init__(self) -> None:
        self.properties = dict(DEFAULT_PROPERTIES)
        self.token = TOKEN
        self.model = "xiaomi.pet_waterer.iv02"
        self.mac: str | None = MAC
        self.online = True
        # (siid, piid) -> MIoT error code returned by get_properties
        self.unsupported: dict[tuple[int, int], int] = {}
        # (siid, piid) -> error code returned by set_properties
        self.refuse_writes: dict[tuple[int, int], int] = {}
        # properties whose writes are acknowledged but not applied
        self.ignore_writes: set[tuple[int, int]] = set()
        # number of upcoming requests that time out (then it answers again)
        self.fail_next = 0
        self.requests: list[tuple[str, Any]] = []
        self.writes: list[tuple[int, int, Any]] = []
        self.actions: list[tuple[int, int]] = []

    def set(self, siid: int, piid: int, value: Any) -> None:
        """Change a property as the device itself would."""
        self.properties[(siid, piid)] = value

    def get(self, siid: int, piid: int) -> Any:
        """Current value of a property."""
        return self.properties[(siid, piid)]

    def mode_writes(self) -> list[Any]:
        """Values written to the mode property (2.4)."""
        return [v for s, p, v in self.writes if (s, p) == (2, 4)]

    def handshake(self) -> None:
        if not self.online:
            raise DeviceException("Unable to discover the device")

    def send(self, token: str, command: str, params: Any) -> Any:
        self.requests.append((command, params))
        if not self.online or token != self.token:
            raise DeviceException("No response from the device")
        if self.fail_next > 0:
            self.fail_next -= 1
            raise DeviceException("No response from the device")
        if command == "miIO.info":
            return {"model": self.model, "mac": self.mac, "fw_ver": "1.0.0_0042", "hw_ver": "esp32"}
        if command == "get_properties":
            answer = []
            for item in params:
                key = (item["siid"], item["piid"])
                if key in self.unsupported or key not in self.properties:
                    answer.append({**item, "code": self.unsupported.get(key, -4003)})
                else:
                    answer.append({**item, "code": 0, "value": self.properties[key]})
            return answer
        if command == "set_properties":
            answer = []
            for item in params:
                key = (item["siid"], item["piid"])
                code = self.refuse_writes.get(key, 0)
                if code == 0:
                    self.writes.append((*key, item["value"]))
                    if key not in self.ignore_writes:
                        self.properties[key] = item["value"]
                answer.append({"did": item["did"], "siid": key[0], "piid": key[1], "code": code})
            return answer
        if command == "action":
            self.actions.append((params["siid"], params["aiid"]))
            if (params["siid"], params["aiid"]) == (3, 1):
                self.properties[(3, 1)] = 100
                self.properties[(3, 2)] = 60
            return {
                "did": params["did"],
                "siid": params["siid"],
                "aiid": params["aiid"],
                "code": 0,
                "out": [],
            }
        raise AssertionError(f"Unexpected command {command}")


class FakeMiioDevice:
    """Stands for miio.Device: forwards to the FakeFountain."""

    def __init__(self, fountain: FakeFountain, token: str) -> None:
        self._fountain = fountain
        self._token = token

    def send_handshake(self) -> None:
        self._fountain.handshake()

    def send(self, command: str, parameters: Any = None, retry_count: int | None = None) -> Any:
        return self._fountain.send(self._token, command, parameters)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def fountain() -> Generator[FakeFountain]:
    """A simulated fountain; every FountainClient talks to it."""
    fake = FakeFountain()

    def factory(ip: str, token: str, timeout: int | None = None) -> FakeMiioDevice:
        return FakeMiioDevice(fake, token)

    with patch("custom_components.xiaomi_pet_fountain_2.api.Device", side_effect=factory):
        yield fake


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the simulated fountain."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Xiaomi Smart Pet Fountain 2",
        unique_id=UNIQUE_ID,
        data={"host": HOST, "token": TOKEN},
    )
