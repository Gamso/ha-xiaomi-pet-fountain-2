"""Local MIoT client for the fountain, on top of python-miio.

python-miio is synchronous: every call runs in Home Assistant's executor,
one at a time (the miIO protocol keeps a message id per device), and is
bounded both by the socket timeout and by an asyncio timeout.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from miio import Device, DeviceException
from miio.exceptions import DeviceError

from .const import (
    CALL_TIMEOUT,
    DEVICE_RETRIES,
    DEVICE_TIMEOUT,
    PROP_SERIAL_NUMBER,
    PROPERTIES_PER_REQUEST,
    MiotProperty,
)

_LOGGER = logging.getLogger(__name__)


class FountainError(Exception):
    """Base error of the fountain client."""


class FountainConnectionError(FountainError):
    """The device did not answer (offline, wrong address or wrong token)."""


class FountainAuthError(FountainConnectionError):
    """The device answers the handshake but not the encrypted requests."""


class FountainCommandError(FountainError):
    """The device answered with an error code."""


@dataclass(frozen=True, slots=True)
class FountainInfo:
    """Identity of the device, from miIO.info."""

    model: str | None
    mac: str | None
    firmware: str | None
    hardware: str | None
    serial_number: str | None = None


class FountainClient:
    """Async facade over a python-miio Device."""

    def __init__(self, hass: HomeAssistant, host: str, token: str) -> None:
        """Create the client; no network traffic until the first call."""
        self._hass = hass
        self.host = host
        self._device = Device(host, token, timeout=DEVICE_TIMEOUT)
        self._lock = asyncio.Lock()

    async def _call[T](self, func: Callable[..., T], *args: Any) -> T:
        async with self._lock:
            try:
                async with asyncio.timeout(CALL_TIMEOUT):
                    return await self._hass.async_add_executor_job(func, *args)
            except TimeoutError as err:
                raise FountainConnectionError(
                    f"No answer from {self.host} within {CALL_TIMEOUT} s"
                ) from err
            except DeviceError as err:
                raise FountainCommandError(str(err)) from err
            except DeviceException as err:
                raise FountainConnectionError(str(err)) from err
            except OSError as err:
                raise FountainConnectionError(str(err)) from err

    def _send(self, command: str, parameters: Any) -> Any:
        return self._device.send(command, parameters, retry_count=DEVICE_RETRIES)

    async def async_validate(self) -> FountainInfo:
        """Check the address and the token, and identify the device.

        Raises FountainConnectionError when nothing answers on the address,
        FountainAuthError when the device answers the (unencrypted) handshake
        but not the encrypted request, which means a wrong token.
        """
        await self._call(self._device.send_handshake)
        try:
            info = await self.async_info()
        except FountainConnectionError as err:
            raise FountainAuthError(str(err)) from err
        if not info.mac:
            values, _ = await self.async_get_properties([PROP_SERIAL_NUMBER])
            serial = values.get(PROP_SERIAL_NUMBER.key)
            info = FountainInfo(info.model, info.mac, info.firmware, info.hardware, serial)
        return info

    async def async_info(self) -> FountainInfo:
        """Read miIO.info (model, MAC address, firmware)."""
        raw = await self._call(self._send, "miIO.info", [])
        if not isinstance(raw, dict):
            raise FountainCommandError(f"Unexpected miIO.info answer: {raw!r}")
        return FountainInfo(
            model=raw.get("model"),
            mac=raw.get("mac"),
            firmware=raw.get("fw_ver"),
            hardware=raw.get("hw_ver"),
        )

    async def async_get_properties(
        self, properties: Iterable[MiotProperty]
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Read properties, a few per request.

        Returns (values, errors): values by property key for the properties
        the device returned, and the MIoT error code of the others (property
        missing on this firmware, not readable...).
        """
        props = list(properties)
        return await self._call(self._get_properties, props)

    def _get_properties(self, props: list[MiotProperty]) -> tuple[dict[str, Any], dict[str, int]]:
        values: dict[str, Any] = {}
        errors: dict[str, int] = {}
        by_iid = {(p.siid, p.piid): p for p in props}
        for start in range(0, len(props), PROPERTIES_PER_REQUEST):
            chunk = props[start : start + PROPERTIES_PER_REQUEST]
            request = [{"did": p.key, "siid": p.siid, "piid": p.piid} for p in chunk]
            answer = self._send("get_properties", request)
            if not isinstance(answer, list):
                raise FountainCommandError(f"Unexpected answer: {answer!r}")
            for item in answer:
                prop = by_iid.get((item.get("siid"), item.get("piid")))
                if prop is None:
                    continue
                code = item.get("code", 0)
                if code == 0 and "value" in item:
                    values[prop.key] = item["value"]
                else:
                    errors[prop.key] = code
        return values, errors

    async def async_set_property(self, prop: MiotProperty, value: Any) -> None:
        """Write one property; raise FountainCommandError if refused."""
        answer = await self._call(
            self._send,
            "set_properties",
            [{"did": prop.key, "siid": prop.siid, "piid": prop.piid, "value": value}],
        )
        code = _first_code(answer)
        if code != 0:
            raise FountainCommandError(
                f"Writing {prop.key} ({prop.siid}.{prop.piid}) failed with code {code}"
            )

    async def async_call_action(
        self, siid: int, aiid: int, params: list[Any] | None = None
    ) -> None:
        """Run a MIoT action; raise FountainCommandError if refused."""
        answer = await self._call(
            self._send,
            "action",
            {"did": f"action-{siid}-{aiid}", "siid": siid, "aiid": aiid, "in": params or []},
        )
        code = _first_code(answer)
        if code != 0:
            raise FountainCommandError(f"Action {siid}.{aiid} failed with code {code}")


def _first_code(answer: Any) -> int | None:
    """Error code of a set_properties / action answer (0 = success)."""
    if isinstance(answer, list) and answer and isinstance(answer[0], dict):
        return answer[0].get("code")
    if isinstance(answer, dict):
        return answer.get("code")
    return None
