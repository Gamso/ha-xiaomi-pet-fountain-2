"""Keep the water mode of the fountain across power cuts.

The fountain does not remember its mode when it loses mains power: it comes
back in its default mode. The keeper remembers a preferred mode (the last
mode chosen from Home Assistant) and writes it back, after a delay, when:

- the fountain goes from battery to mains power (charging state / USB),
- the fountain answers again after being unavailable,
- the integration starts and reads another mode,
- the preferred mode is changed from the options or the service.

A mode changed elsewhere (button on the device, Mi Home app) outside these
events is left alone, unless the "force" option is on: then any difference
is corrected. Each restoration makes a
bounded number of attempts with an exponential backoff, and the outcome of
the last one is stored, logged and fired on the event bus.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import CALLBACK_TYPE, HassJob, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import FountainError
from .const import (
    CHARGING_NO_CHARGE,
    CONF_FORCE_MODE,
    CONF_RESTORE_DELAY,
    DEFAULT_RESTORE_DELAY,
    DOMAIN,
    EVENT_MODE_RESTORE,
    FORCE_COOLDOWN,
    MODE_TO_VALUE,
    PROP_MODE,
    RESTORE_MAX_ATTEMPTS,
    RESTORE_MAX_BACKOFF,
    RESTORE_MIN_BACKOFF,
    VALUE_TO_MODE,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import FountainCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1

REASON_STARTUP = "startup"
REASON_RECONNECTED = "reconnected"
REASON_POWER_RESTORED = "power_restored"
REASON_FORCED = "forced"
REASON_PREFERENCE_CHANGED = "preference_changed"
REASON_SERVICE = "service"

RESULT_SUCCESS = "success"
RESULT_FAILED = "failed"


def storage_key(entry_id: str) -> str:
    """Key of the store of an entry."""
    return f"{DOMAIN}.{entry_id}"


def on_mains_power(data: dict[str, Any]) -> bool | None:
    """Whether the fountain runs on mains power; None if unknown.

    9.6 usb-insert-state says whether the power cable is plugged; 5.2
    charging-state is "no charge" only when running on battery. Either
    signal saying mains power is enough.
    """
    signals = []
    if (usb := data.get("usb_power")) is not None:
        signals.append(bool(usb))
    if (charging := data.get("charging_state")) is not None:
        signals.append(charging != CHARGING_NO_CHARGE)
    return any(signals) if signals else None


class ModeNotAppliedError(Exception):
    """The device acknowledged the write but reports another mode."""


@dataclass(slots=True)
class RestoreRecord:
    """Outcome of a restoration."""

    time: datetime
    reason: str
    result: str
    from_mode: str | None
    to_mode: str
    attempts: int
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Serializable form."""
        data = asdict(self)
        data["time"] = self.time.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Any) -> RestoreRecord | None:
        """Read a stored record; None if absent or invalid."""
        if not isinstance(data, dict):
            return None
        try:
            parsed = dt_util.parse_datetime(data["time"])
            if parsed is None:
                return None
            return cls(
                time=parsed,
                reason=data["reason"],
                result=data["result"],
                from_mode=data.get("from_mode"),
                to_mode=data["to_mode"],
                attempts=int(data["attempts"]),
                error=data.get("error"),
            )
        except KeyError, TypeError, ValueError:
            return None


@dataclass(slots=True)
class _Episode:
    """A restoration in progress."""

    reason: str
    from_mode: str | None
    attempts: int = 0
    written: bool = False


async def async_store_preferred_mode(hass: HomeAssistant, entry: ConfigEntry, mode: str) -> None:
    """Save the preferred mode of an entry that is not loaded."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id))
    data = await store.async_load() or {}
    data["preferred_mode"] = mode
    await store.async_save(data)


async def async_read_preferred_mode(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Read the preferred mode of an entry that is not loaded."""
    store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, storage_key(entry.entry_id))
    data = await store.async_load() or {}
    mode = data.get("preferred_mode")
    return mode if mode in MODE_TO_VALUE else None


async def async_remove_store(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the store of a removed entry."""
    await Store(hass, STORAGE_VERSION, storage_key(entry_id)).async_remove()


class ModeKeeper:
    """Remembers the preferred mode and restores it."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: FountainCoordinator
    ) -> None:
        """Initialize from the entry options; call async_load next."""
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.delay: float = entry.options.get(CONF_RESTORE_DELAY, DEFAULT_RESTORE_DELAY)
        self.force: bool = entry.options.get(CONF_FORCE_MODE, False)
        self.preferred_mode: str | None = None
        self.keep_enabled = True
        self.last_restore: RestoreRecord | None = None
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, storage_key(entry.entry_id)
        )
        self._listeners: list[CALLBACK_TYPE] = []
        self._prev_available: bool | None = None
        self._prev_on_mains: bool | None = None
        self._episode: _Episode | None = None
        self._cancel_timer: CALLBACK_TYPE | None = None
        self._force_paused_until: datetime | None = None
        self._unsub_coordinator: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------
    # Lifecycle and persistence
    # ------------------------------------------------------------------
    async def async_load(self) -> None:
        """Load the stored state; adopt the current mode if none is stored."""
        data = await self._store.async_load() or {}
        mode = data.get("preferred_mode")
        self.preferred_mode = mode if mode in MODE_TO_VALUE else None
        self.keep_enabled = bool(data.get("keep_mode", True))
        self.last_restore = RestoreRecord.from_dict(data.get("last_restore"))
        if self.preferred_mode is None:
            current = VALUE_TO_MODE.get((self.coordinator.data or {}).get("mode"))
            if current is not None:
                _LOGGER.debug("No preferred mode stored, adopting the current one: %s", current)
                self.preferred_mode = current
                await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save(
            {
                "preferred_mode": self.preferred_mode,
                "keep_mode": self.keep_enabled,
                "last_restore": self.last_restore.as_dict() if self.last_restore else None,
            }
        )

    @callback
    def async_start(self) -> None:
        """Follow the coordinator; the first evaluation is the startup check."""
        self._unsub_coordinator = self.coordinator.async_add_listener(
            self._handle_coordinator_update
        )
        self._handle_coordinator_update()

    @callback
    def async_stop(self) -> None:
        """Stop following the coordinator and cancel a pending restoration."""
        if self._unsub_coordinator is not None:
            self._unsub_coordinator()
            self._unsub_coordinator = None
        self._cancel_episode()

    @callback
    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> Callable[[], None]:
        """Call update_callback whenever the keeper state changes."""
        self._listeners.append(update_callback)

        @callback
        def remove() -> None:
            self._listeners.remove(update_callback)

        return remove

    @callback
    def _notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()

    @property
    def restoring(self) -> bool:
        """Whether a restoration is pending."""
        return self._episode is not None

    # ------------------------------------------------------------------
    # User actions
    # ------------------------------------------------------------------
    async def async_set_preferred_mode(self, mode: str, *, apply: bool) -> None:
        """Remember a mode chosen by the user.

        apply=False: the mode was just written to the device (mode select).
        apply=True: options or service; restore it if the device differs.
        """
        self.preferred_mode = mode
        self._cancel_episode()
        await self._async_save()
        self._notify()
        if apply and self.coordinator.last_update_success:
            data = self.coordinator.data or {}
            self._async_request(REASON_PREFERENCE_CHANGED, data, on_mains_power(data))

    async def async_set_keep_enabled(self, enabled: bool) -> None:
        """Switch the mode keeping on or off."""
        self.keep_enabled = enabled
        if not enabled:
            self._cancel_episode()
        await self._async_save()
        self._notify()

    async def async_restore_now(self) -> None:
        """Restore the preferred mode right away (service), whatever the switch."""
        if self.preferred_mode is None:
            return
        self._cancel_episode()
        current = VALUE_TO_MODE.get((self.coordinator.data or {}).get("mode"))
        self._episode = _Episode(REASON_SERVICE, current)
        await self._async_attempt()

    # ------------------------------------------------------------------
    # Event detection
    # ------------------------------------------------------------------
    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.last_update_success:
            if self._prev_available is not False:
                _LOGGER.debug("Fountain unavailable")
            self._prev_available = False
            return

        data = self.coordinator.data or {}
        on_mains = on_mains_power(data)
        reason: str | None = None
        if self._prev_available is None:
            reason = REASON_STARTUP
        elif self._prev_available is False:
            reason = REASON_RECONNECTED
        elif self._prev_on_mains is False and on_mains is True:
            reason = REASON_POWER_RESTORED
        self._prev_available = True
        if on_mains is not None:
            self._prev_on_mains = on_mains
        if reason is None and self.force:
            reason = REASON_FORCED
        if reason is not None:
            self._async_request(reason, data, on_mains)

    @callback
    def _async_request(self, reason: str, data: dict[str, Any], on_mains: bool | None) -> None:
        """Start a restoration if the mode differs and none is running."""
        if not self.keep_enabled or self.preferred_mode is None or self._episode is not None:
            return
        current = VALUE_TO_MODE.get(data.get("mode"))
        if current == self.preferred_mode:
            return
        if reason == REASON_FORCED:
            if self._force_paused_until is not None and dt_util.utcnow() < self._force_paused_until:
                return
        elif on_mains is False:
            _LOGGER.info(
                "Mode is %s instead of %s but the fountain is on battery: "
                "waiting for mains power before restoring it",
                current,
                self.preferred_mode,
            )
            return
        _LOGGER.info(
            "Mode is %s instead of %s (%s): restoring it in %s s",
            current,
            self.preferred_mode,
            reason,
            self.delay,
        )
        self._episode = _Episode(reason, current)
        self._schedule(self.delay)
        self._notify()

    # ------------------------------------------------------------------
    # Restoration
    # ------------------------------------------------------------------
    @callback
    def _schedule(self, delay: float) -> None:
        self._cancel_timer = async_call_later(
            self.hass, delay, HassJob(self._timer_fired, cancel_on_shutdown=True)
        )

    @callback
    def _timer_fired(self, _now: datetime) -> None:
        self._cancel_timer = None
        self.entry.async_create_background_task(
            self.hass, self._async_attempt(), f"{DOMAIN} mode restoration"
        )

    @callback
    def async_cancel(self) -> None:
        """Cancel a pending restoration (the user is changing the mode)."""
        self._cancel_episode()

    @callback
    def _cancel_episode(self) -> None:
        if self._cancel_timer is not None:
            self._cancel_timer()
            self._cancel_timer = None
        if self._episode is not None:
            self._episode = None
            self._notify()

    async def _async_attempt(self) -> None:
        episode = self._episode
        target = self.preferred_mode
        if episode is None or target is None:
            return
        if not self.keep_enabled and episode.reason != REASON_SERVICE:
            self._cancel_episode()
            return
        episode.attempts += 1
        value = MODE_TO_VALUE[target]
        try:
            if not await self._async_apply(episode, value):
                return  # cancelled meanwhile (the user picked a mode)
        except (FountainError, ModeNotAppliedError) as err:
            if self._episode is not episode:
                return  # cancelled meanwhile
            if episode.attempts >= RESTORE_MAX_ATTEMPTS:
                _LOGGER.warning(
                    "Could not restore mode %s after %s attempts: %s",
                    target,
                    episode.attempts,
                    err,
                )
                if episode.reason == REASON_FORCED:
                    self._force_paused_until = dt_util.utcnow() + timedelta(seconds=FORCE_COOLDOWN)
                await self._async_finish(episode, target, RESULT_FAILED, str(err))
                return
            backoff = min(
                max(self.delay, RESTORE_MIN_BACKOFF) * 2**episode.attempts, RESTORE_MAX_BACKOFF
            )
            _LOGGER.info(
                "Restoring mode %s failed (attempt %s/%s): %s; retrying in %s s",
                target,
                episode.attempts,
                RESTORE_MAX_ATTEMPTS,
                err,
                backoff,
            )
            self._schedule(backoff)
            return

        if self._episode is not episode:
            return
        self.coordinator.async_set_value(PROP_MODE.key, value)
        if not episode.written:
            _LOGGER.debug("Mode already %s, nothing to restore", target)
            self._episode = None
            self._notify()
            return
        _LOGGER.info(
            "Mode restored to %s (%s, was %s, %s attempt(s))",
            target,
            episode.reason,
            episode.from_mode,
            episode.attempts,
        )
        self._force_paused_until = None
        await self._async_finish(episode, target, RESULT_SUCCESS)

    async def _async_apply(self, episode: _Episode, value: int) -> bool:
        """Read the mode, write it if needed and read it back.

        Returns False if the episode was cancelled before the write.
        """
        client = self.coordinator.client
        values, _ = await client.async_get_properties([PROP_MODE])
        if self._episode is not episode:
            return False
        if values.get(PROP_MODE.key) != value:
            await client.async_set_property(PROP_MODE, value)
            episode.written = True
            values, _ = await client.async_get_properties([PROP_MODE])
            readback = values.get(PROP_MODE.key)
            if readback != value:
                raise ModeNotAppliedError(
                    f"the fountain reports {VALUE_TO_MODE.get(readback, readback)}"
                )
        return True

    async def _async_finish(
        self, episode: _Episode, target: str, result: str, error: str | None = None
    ) -> None:
        self._episode = None
        self.last_restore = RestoreRecord(
            time=dt_util.utcnow(),
            reason=episode.reason,
            result=result,
            from_mode=episode.from_mode,
            to_mode=target,
            attempts=episode.attempts,
            error=error,
        )
        self.hass.bus.async_fire(
            EVENT_MODE_RESTORE,
            {"config_entry_id": self.entry.entry_id, **self.last_restore.as_dict()},
        )
        await self._async_save()
        self._notify()

    def as_diagnostics(self) -> dict[str, Any]:
        """State for the diagnostics download."""
        return {
            "preferred_mode": self.preferred_mode,
            "keep_enabled": self.keep_enabled,
            "force": self.force,
            "delay": self.delay,
            "restoring": self.restoring,
            "on_mains_power": self._prev_on_mains,
            "force_paused_until": (
                self._force_paused_until.isoformat() if self._force_paused_until else None
            ),
            "last_restore": self.last_restore.as_dict() if self.last_restore else None,
        }
