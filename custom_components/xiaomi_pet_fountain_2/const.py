"""Constants for the Xiaomi Smart Pet Fountain 2 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DOMAIN: Final = "xiaomi_pet_fountain_2"
DEFAULT_NAME: Final = "Xiaomi Smart Pet Fountain 2"
MANUFACTURER: Final = "Xiaomi"
MODEL_NAME: Final = "Smart Pet Fountain 2"
SUPPORTED_MODELS: Final = ("xiaomi.pet_waterer.iv02",)

CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
MIN_SCAN_INTERVAL: Final = 10
MAX_SCAN_INTERVAL: Final = 600

# Network: one miIO request waits at most DEVICE_TIMEOUT seconds and is sent
# at most DEVICE_RETRIES + 1 times; CALL_TIMEOUT bounds a whole call (several
# chunked requests) from the event loop side.
DEVICE_TIMEOUT: Final = 3
DEVICE_RETRIES: Final = 1
CALL_TIMEOUT: Final = 20
PROPERTIES_PER_REQUEST: Final = 10


@dataclass(frozen=True, slots=True)
class MiotProperty:
    """A MIoT property of the fountain (urn ...:xiaomi-iv02:2)."""

    key: str
    siid: int
    piid: int


# siid 1 - device-information
PROP_SERIAL_NUMBER: Final = MiotProperty("serial_number", 1, 3)
# siid 2 - pet-drinking-fountain
PROP_ON: Final = MiotProperty("on", 2, 1)
PROP_FAULT: Final = MiotProperty("fault", 2, 2)
PROP_STATUS: Final = MiotProperty("status", 2, 3)
PROP_MODE: Final = MiotProperty("mode", 2, 4)
PROP_OUT_WATER_INTERVAL: Final = MiotProperty("out_water_interval", 2, 7)
PROP_WATER_SHORTAGE: Final = MiotProperty("water_shortage", 2, 10)
PROP_OUT_WATER_INTERVAL_2: Final = MiotProperty("out_water_interval_2", 2, 11)
# siid 3 - filter
PROP_FILTER_LIFE: Final = MiotProperty("filter_life", 3, 1)
PROP_FILTER_LEFT_TIME: Final = MiotProperty("filter_left_time", 3, 2)
# siid 4 - physical-controls-locked
PROP_CHILD_LOCK: Final = MiotProperty("child_lock", 4, 1)
# siid 5 - battery
PROP_BATTERY_LEVEL: Final = MiotProperty("battery_level", 5, 1)
PROP_CHARGING_STATE: Final = MiotProperty("charging_state", 5, 2)
# siid 6 - no-disturb
PROP_NO_DISTURB: Final = MiotProperty("no_disturb", 6, 1)
# siid 9 - pet-waterer-costom (sic)
PROP_LOW_BATTERY: Final = MiotProperty("low_battery", 9, 5)
PROP_USB_POWER: Final = MiotProperty("usb_power", 9, 6)
PROP_NO_DISTURB_START: Final = MiotProperty("no_disturb_start", 9, 10)
PROP_NO_DISTURB_END: Final = MiotProperty("no_disturb_end", 9, 11)
PROP_PUMP_BLOCKED: Final = MiotProperty("pump_blocked", 9, 12)

# Polled on every update. Left out on purpose: device information (read
# once), the event log properties 9.13-9.16 (cloud event arguments) and
# 9.17 factory-mode-switch (debug/engineering modes, never exposed).
POLLED_PROPERTIES: Final = (
    PROP_ON,
    PROP_FAULT,
    PROP_STATUS,
    PROP_MODE,
    PROP_OUT_WATER_INTERVAL,
    PROP_WATER_SHORTAGE,
    PROP_OUT_WATER_INTERVAL_2,
    PROP_FILTER_LIFE,
    PROP_FILTER_LEFT_TIME,
    PROP_CHILD_LOCK,
    PROP_BATTERY_LEVEL,
    PROP_CHARGING_STATE,
    PROP_NO_DISTURB,
    PROP_LOW_BATTERY,
    PROP_USB_POWER,
    PROP_NO_DISTURB_START,
    PROP_NO_DISTURB_END,
    PROP_PUMP_BLOCKED,
)
PROPERTIES_BY_KEY: Final = {prop.key: prop for prop in POLLED_PROPERTIES}

# siid 3 aiid 1 - reset-filter-life (no argument)
ACTION_RESET_FILTER: Final = (3, 1)

# 2.4 mode
MODE_AUTO: Final = "auto"
MODE_INTERVAL: Final = "interval"
MODE_CONSTANT: Final = "constant"
MODE_TO_VALUE: Final = {MODE_AUTO: 0, MODE_INTERVAL: 1, MODE_CONSTANT: 2}
VALUE_TO_MODE: Final = {value: mode for mode, value in MODE_TO_VALUE.items()}
MODES: Final = list(MODE_TO_VALUE)

# 2.3 status (pump)
STATUS_TO_STATE: Final = {1: "waterless", 2: "watering"}

# 5.2 charging-state
CHARGING_NO_CHARGE: Final = 0
CHARGING_TO_STATE: Final = {0: "no_charge", 1: "charging", 2: "charge_full"}
