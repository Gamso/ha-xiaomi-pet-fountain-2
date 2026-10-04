# Xiaomi Smart Pet Fountain 2 for Home Assistant

Local integration for the **Xiaomi Smart Pet Fountain 2** (`xiaomi.pet_waterer.iv02`):
no Xiaomi cloud, the fountain is read and controlled on your network with the
miIO/MIoT protocol (UDP 54321), through
[python-miio](https://github.com/rytilahti/python-miio).

Its main feature is **mode keeping**: the fountain forgets its water mode when
it loses mains power and comes back in auto mode. The integration writes your
preferred mode back by itself (see [Mode keeping](#mode-keeping)).

- Config flow: IP address + token, checked against the device
- Local polling (30 s by default, configurable), one device per fountain
- Every useful property of the MIoT spec as an entity, in English and French
- Services, diagnostics (token redacted)

## Installation

### HACS (custom repository)

1. HACS > three dots > **Custom repositories**: add
   `https://github.com/Gamso/ha-xiaomi-pet-fountain-2`, type **Integration**.
2. Install **Xiaomi Smart Pet Fountain 2**, then restart Home Assistant.

### Manual

Copy `custom_components/xiaomi_pet_fountain_2` into the `custom_components`
folder of your Home Assistant configuration, then restart Home Assistant.

Home Assistant 2026.3 or later is required (Python 3.14). The integration is
tested with Home Assistant 2026.9.

## Configuration

**Settings > Devices & services > Add integration > Xiaomi Smart Pet Fountain 2**,
then enter:

- **IP address** of the fountain. Reserve it in your router (DHCP reservation):
  the integration talks to this address only. If it changes, use
  **Reconfigure** on the integration entry.
- **Token**: the 32 hexadecimal characters key of the device.

The integration checks both with a real request. *No answer from this address*
means the fountain did not answer the handshake (wrong IP, other network,
fountain offline); *the fountain answers but rejects the token* means the IP is
right and the token is wrong.

### Getting the token

The token is created when the fountain is paired with the Mi Home app; pairing
it again changes it. Ways to read it:

- [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor):
  log in with your Xiaomi account and pick the server of your region (`de` for
  Europe); it lists every device with its IP and token.
- If you added the fountain to **Xiaomi Miot Auto** in local mode, you already
  entered its token there.
- `miiocli cloud` (python-miio command line) does the same as the extractor.

### Options

| Option | Default | Description |
|---|---|---|
| Polling interval | 30 s | Seconds between two reads (10 to 600) |
| Preferred mode | current mode | Mode written back by mode keeping |
| Restoration delay | 10 s | Wait before writing the mode back (0 to 300) |
| Force permanently | off | Also correct a mode changed on the device or in Mi Home, see below |

Changing an option reloads the integration.

## Entities

Entity IDs below are for a device named *Xiaomi Smart Pet Fountain 2*
(prefix `xiaomi_smart_pet_fountain_2_`). siid/piid refer to the MIoT spec
`urn:miot-spec-v2:device:pet-drinking-fountain:0000A067:xiaomi-iv02:2`.
Entities are only created for the properties the fountain answers.

Entity IDs are always these English ones, whatever the language of Home
Assistant: only the names are translated. Without that, Home Assistant would
build the IDs from the translated names for some languages, French included
(`switch.xiaomi_smart_pet_fountain_2_marche`). A second fountain with the same
name gets the same IDs with a `_2` suffix.

Entities that already have other IDs (French ones from an earlier install, or
IDs you changed) keep them: Home Assistant never renames a registered entity,
and removing then adding the integration again brings the old IDs back. To
switch to the English IDs: **Settings > Devices & services > Devices**, open
the fountain, then in the ⋮ menu choose **Recreate entity IDs** (*Recréer les
identifiants d'entité*). The dialog lists the old and new IDs before
confirming. To do it for some entities only, select them in **Settings >
Devices & services > Entities** and use **Recreate entity IDs of selected**.
Automations, scripts and dashboards are not updated: change them to the new
IDs.

| Entity | MIoT | Notes |
|---|---|---|
| `switch.…_power` | 2.1 on | Pump on/off |
| `select.…_mode` | 2.4 mode | `auto` (water when a pet comes near), `interval`, `constant` |
| `sensor.…_pump_status` | 2.3 status | `watering` / `waterless` |
| `binary_sensor.…_water_shortage` | 2.10 water-shortage-status | on = water missing |
| `binary_sensor.…_fault` | 2.2 fault | on = fault code other than 0 (diagnostic) |
| `binary_sensor.…_pump_blocked` | 9.12 pump-block | |
| `number.…_water_interval` | 2.7 out-water-interval | 0-120 min, step 15 |
| `number.…_water_interval_5_min_steps` | 2.11 out-water-interval | 10-120 min, step 5 (spec v2) |
| `sensor.…_filter_life` | 3.1 filter-life-level | % |
| `sensor.…_filter_time_left` | 3.2 filter-left-time | days |
| `button.…_reset_filter` | action 3.1 reset-filter-life | After changing the filter |
| `switch.…_child_lock` | 4.1 physical-controls-locked | |
| `sensor.…_battery` | 5.1 battery-level | % (diagnostic) |
| `sensor.…_charging_state` | 5.2 charging-state | `no_charge` (on battery) / `charging` / `charge_full` (diagnostic) |
| `binary_sensor.…_low_battery` | 9.5 low-battery | diagnostic |
| `binary_sensor.…_mains_power` | 9.6 usb-insert-state | on = power cable plugged (diagnostic) |
| `switch.…_do_not_disturb` | 6.1 no-disturb | |
| `time.…_do_not_disturb_start` / `_end` | 9.10 / 9.11 | Seconds since midnight on the device |
| `switch.…_keep_mode` | (integration) | Mode keeping on/off |
| `sensor.…_preferred_mode` | (integration) | Mode restored by mode keeping (diagnostic) |
| `sensor.…_last_mode_restoration` | (integration) | Time of the last restoration; attributes `reason`, `result`, `from_mode`, `to_mode`, `attempts`, `error` (diagnostic) |

Left out on purpose: 9.17 factory-mode-switch (debug and engineering modes of
the firmware), the event log properties 9.13 to 9.16 and the MIoT events
(they are pushed to the Xiaomi cloud, not to the local network).

The spec has two *out water interval* properties: 2.7 (since spec v1) and 2.11
(added by spec v2). Which one the firmware applies in interval mode has not
been checked on a device yet; both are exposed when the fountain answers them.

## Mode keeping

The fountain does not remember its water mode after a power cut. With
**Keep mode** on (`switch.…_keep_mode`, on by default), the integration
remembers a **preferred mode** and writes it back, after the restoration delay
(10 s), when:

- the fountain goes from battery to mains power (mains power or charging state
  changes),
- the fountain answers again after being unavailable,
- the integration starts (Home Assistant restart, reload) and reads another
  mode,
- the preferred mode is changed in the options or with the service.

The preferred mode is the last mode chosen from Home Assistant: selecting a
mode with `select.…_mode` changes it. It is stored with the switch state and
the last restoration, so all three survive restarts. At the first setup it is
the mode the fountain is in.

While the fountain runs on battery, the integration waits for mains power
before writing the mode back. Each restoration reads the mode, writes it and
reads it back; it makes at most 3 attempts, 20 s then 40 s apart, then gives up
until the next event. The outcome is in `sensor.…_last_mode_restoration`, in the
log, and fired as a `xiaomi_pet_fountain_2_mode_restore` event (with
`config_entry_id`, `reason`, `result`, `from_mode`, `to_mode`, `attempts`,
`error`).

A mode changed **on the device or in Mi Home** outside these events is left
alone: the integration does not fight it, and restores the preferred mode at
the next power cut. Turn on the **Force permanently** option to correct any
difference at every poll instead, even on battery; after a failed forced
restoration, forcing pauses for 10 minutes.

## Services

| Service | Fields | Effect |
|---|---|---|
| `xiaomi_pet_fountain_2.restore_mode` | `config_entry_id` | Writes the preferred mode now, whatever the Keep mode switch |
| `xiaomi_pet_fountain_2.set_preferred_mode` | `config_entry_id`, `mode` | Changes the preferred mode and restores it if Keep mode is on |

The reset filter action is the `button.…_reset_filter` entity.

## Migrating from Xiaomi Miot Auto

The entity IDs change. Typical equivalents (Miot Auto names from a fountain
called `xiaomi_iv02_xxxx`):

| Xiaomi Miot Auto | This integration |
|---|---|
| `switch.xiaomi_iv02_xxxx_pet_drinking_fountain` | `switch.xiaomi_smart_pet_fountain_2_power` |
| `select.xiaomi_iv02_xxxx_mode` (`Auto`, `Interval`, `Constant`) | `select.xiaomi_smart_pet_fountain_2_mode` (`auto`, `interval`, `constant`) |
| `sensor.xiaomi_iv02_xxxx_status` | `sensor.xiaomi_smart_pet_fountain_2_pump_status` |
| `binary_sensor.xiaomi_iv02_xxxx_water_shortage_status` | `binary_sensor.xiaomi_smart_pet_fountain_2_water_shortage` |
| `sensor.xiaomi_iv02_xxxx_filter_life_level` | `sensor.xiaomi_smart_pet_fountain_2_filter_life` |
| `sensor.xiaomi_iv02_xxxx_filter_left_time` | `sensor.xiaomi_smart_pet_fountain_2_filter_time_left` |
| `button.xiaomi_iv02_xxxx_reset_filter_life` | `button.xiaomi_smart_pet_fountain_2_reset_filter` |
| `sensor.xiaomi_iv02_xxxx_battery_level` | `sensor.xiaomi_smart_pet_fountain_2_battery` |
| `sensor.xiaomi_iv02_xxxx_charging_state` (`no charge`, `charging`, `charge full`) | `sensor.xiaomi_smart_pet_fountain_2_charging_state` (`no_charge`, `charging`, `charge_full`) |
| `switch.xiaomi_iv02_xxxx_physical_control_locked` | `switch.xiaomi_smart_pet_fountain_2_child_lock` |
| `switch.xiaomi_iv02_xxxx_no_disturb` | `switch.xiaomi_smart_pet_fountain_2_do_not_disturb` |
| `number.xiaomi_iv02_xxxx_out_water_interval` | `number.xiaomi_smart_pet_fountain_2_water_interval` |
| `number.xiaomi_iv02_xxxx_out_water_interval_2` | `number.xiaomi_smart_pet_fountain_2_water_interval_5_min_steps` |

States are lowercase keys (translated in the interface): update the
automations and templates that compare states, such as `'Constant'`.

Steps:

1. Note the token of the fountain (see [Getting the token](#getting-the-token)).
2. In Xiaomi Miot Auto, **disable the fountain device** (or remove it): two
   integrations polling the same device double the traffic and their writes
   race each other.
3. Add this integration, then update automations, scripts and dashboards with
   the new entity IDs. You can also rename the new entities to the old IDs
   (entity settings) once the Miot Auto ones are removed.
4. The Lovelace card
   [xiaomi_smart_pet_fountain_2_card](https://github.com/Gamso/xiaomi_smart_pet_fountain_2_card)
   detects this integration by itself: point it at any entity of the fountain,
   for example `entity: switch.xiaomi_smart_pet_fountain_2_power`.

## Not checked on a real device

The integration was developed against the published MIoT spec and a simulated
fountain. Still to confirm on hardware: which interval property (2.7 or 2.11)
the firmware uses; that 9.6 really reports the power cable; whether the
fountain stays on Wi-Fi while on battery (if it does not, the power cut is
seen as an unavailability, which mode keeping handles too); the mode the
fountain falls back to after a power cut. Reports with diagnostics are welcome.

## Credits

- The structure (config flow with IP and token, coordinator, platforms,
  services, translations, tests) follows
  [DerSteph/ha-xiaomi-feeder-2](https://github.com/DerSteph/ha-xiaomi-feeder-2)
  and its library [xiaomi-feeder-2](https://github.com/DerSteph/xiaomi-feeder-2)
  for the Xiaomi Smart Pet Food Feeder 2, which also talk MIoT over python-miio.
  No code was copied from them (GPL-3.0); this integration is written from
  scratch.
- [python-miio](https://github.com/rytilahti/python-miio) (GPL-3.0) for the
  miIO protocol; it is installed by Home Assistant as a requirement, not
  bundled.
- MIoT spec: [home.miot-spec.com](https://home.miot-spec.com/s/xiaomi.pet_waterer.iv02).

## License

MIT, see [LICENSE](LICENSE).
