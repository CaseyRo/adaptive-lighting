# output-sensors Specification

## Purpose
Per-profile read-only `sensor` entities that expose the curve's current target brightness/color-temperature outputs and the actual solar elevation as graphable HA `MEASUREMENT`-class values. Sensors are pure readers of a runtime cache the master switch publishes to after each curve tick; they do not recompute the curve. The integration's existing master-switch attributes (`brightness_pct`, `color_temp_kelvin`, synthetic `sun_position` in [-1, +1]) are unaffected — the sensors are an additive, graphable surface over the same data plus `sun.sun.elevation`.

## Requirements
### Requirement: Each AL profile exposes three output sensor entities plus two conditional lux sensors

For each Adaptive Lighting config entry, the integration SHALL create the three existing output sensor entities plus two additional lux-related sensors when a `lux_sensor` is configured. All sensors SHALL be registered on the `sensor` platform during `async_setup_entry` and torn down during `async_unload_entry`. Each entity SHALL share the same device record (`(DOMAIN, entry.entry_id)`) as the profile's existing switches and number entities.

| Output | `unique_id` suffix | `_attr_name` | `native_unit_of_measurement` | `state_class` | icon | Condition |
|---|---|---|---|---|---|---|
| Output brightness | `_output_brightness` | `"Output brightness"` | `"%"` | `MEASUREMENT` | `mdi:brightness-percent` | always |
| Output color temperature | `_output_color_temp` | `"Output color temp"` | `"K"` | `MEASUREMENT` | `mdi:thermometer` | always |
| Sun elevation | `_sun_elevation` | `"Sun elevation"` | `"°"` | `MEASUREMENT` | `mdi:weather-sunset` | always |
| Ambient lux | `_ambient_lux` | `"Ambient lux"` | `"lx"` | `MEASUREMENT` | `mdi:brightness-5` | `lux_sensor` configured |
| Lux reduction | `_lux_reduction` | `"Lux reduction"` | `"%"` | `MEASUREMENT` | `mdi:chart-line-variant` | `lux_sensor` configured |

The full `unique_id` SHALL be `<entry.entry_id>_<suffix>`.

#### Scenario: Profile with lux sensor produces five sensor entities

- **WHEN** the user creates an AL config entry with `lux_sensor` set to `sensor.office_illuminance`
- **AND** `async_setup_entry` completes
- **THEN** the entity registry SHALL contain five `sensor` entities owned by this entry
- **AND** their unique_ids SHALL end with `_output_brightness`, `_output_color_temp`, `_sun_elevation`, `_ambient_lux`, and `_lux_reduction`

#### Scenario: Profile without lux sensor produces three sensor entities

- **WHEN** the user creates an AL config entry without a `lux_sensor` configured
- **AND** `async_setup_entry` completes
- **THEN** the entity registry SHALL contain three `sensor` entities owned by this entry
- **AND** the `_ambient_lux` and `_lux_reduction` entities SHALL NOT be created

#### Scenario: Removing lux sensor removes the two conditional sensors

- **GIVEN** an AL profile has `lux_sensor` configured and all five sensors exist
- **WHEN** the user removes `lux_sensor` (sets to empty) and saves options
- **THEN** on reload, the `_ambient_lux` and `_lux_reduction` entities SHALL be removed from the entity registry
- **AND** only the three unconditional sensors SHALL remain

#### Scenario: Sensor metadata matches the design table

- **WHEN** any of the three unconditional sensors is inspected via the entity registry
- **THEN** `output_brightness` SHALL declare `native_unit_of_measurement="%"`, `state_class=SensorStateClass.MEASUREMENT`, no `device_class`
- **AND** `output_color_temp` SHALL declare `native_unit_of_measurement="K"`, `state_class=SensorStateClass.MEASUREMENT`, no `device_class`
- **AND** `sun_elevation` SHALL declare `native_unit_of_measurement="°"`, `state_class=SensorStateClass.MEASUREMENT`, no `device_class`

### Requirement: Curve evaluation publishes outputs to a runtime cache

On every curve evaluation tick, the master switch (`AdaptiveSwitch`) SHALL publish to `hass.data[DOMAIN][entry.entry_id]["outputs"]` a dictionary with keys `output_brightness` (int 0-100, sourced from `self._settings["brightness_pct"]`), `output_color_temp` (int Kelvin, sourced from `self._settings["color_temp_kelvin"]`), `sun_elevation` (float degrees or `None`, sourced from `hass.states.get("sun.sun").attributes.get("elevation")`), and `updated_at` (datetime). This publish SHALL happen after the curve math completes and before any state writes to the switch's own attributes.

If `sun.sun` is missing from the state machine or its `elevation` attribute is absent, `sun_elevation` in the cache SHALL be `None`; the other three keys SHALL still be populated normally.

The cache dict keys SHALL match the `OUTPUT_SENSORS[*]["key"]` values exactly, so sensors read `hass.data[DOMAIN][entry.entry_id]["outputs"][self._output_key]` with no intermediate mapping.

The integration SHALL NOT cause the sensor entities to recompute the curve. Sensors are pure readers of the published cache.

#### Scenario: Each curve tick refreshes the runtime cache

- **GIVEN** the integration is loaded and the master switch's adapt loop is running
- **AND** `sun.sun.attributes.elevation` is populated
- **WHEN** a curve evaluation tick completes
- **THEN** `hass.data[DOMAIN][entry.entry_id]["outputs"]` SHALL contain the four keys `output_brightness`, `output_color_temp`, `sun_elevation`, `updated_at`
- **AND** the values SHALL be the just-computed curve outputs (for the first two) and the current `sun.sun` elevation (for the third)
- **AND** `updated_at` SHALL be a `datetime` no older than the previous tick's `updated_at` value

#### Scenario: `sun.sun` unavailability does not block the publish

- **GIVEN** the integration is loaded and the master switch's adapt loop is running
- **AND** `hass.states.get("sun.sun")` returns `None` (or its `elevation` attribute is absent)
- **WHEN** a curve evaluation tick completes
- **THEN** `hass.data[DOMAIN][entry.entry_id]["outputs"]["sun_elevation"]` SHALL be `None`
- **AND** `output_brightness` and `output_color_temp` SHALL still hold their computed values
- **AND** no exception SHALL propagate out of the publish step

#### Scenario: Sensors do not perform their own curve math

- **WHEN** a sensor entity's `async_added_to_hass` and `_handle_outputs_updated` methods are inspected
- **THEN** neither method SHALL import `SunLightSettings` or any curve-computation helper
- **AND** neither method SHALL call `hass.states.get` for the sun-time entities, the four range number entities, or `sun.sun`

### Requirement: Sensors update via a per-entry dispatcher signal

After publishing outputs to the runtime cache, the master switch SHALL emit a dispatcher signal `f"{DOMAIN}_{entry.entry_id}_outputs_updated"` via `homeassistant.helpers.dispatcher.async_dispatcher_send`. Each of the three sensors SHALL subscribe to this exact signal in its `async_added_to_hass` method. On receiving the signal, the sensor SHALL read its key from `hass.data[DOMAIN][entry.entry_id]["outputs"]`, update `_attr_native_value`, and call `async_write_ha_state()`.

Sensors SHALL NOT poll. `_attr_should_poll` SHALL be `False`.

The dispatcher unsubscribe handle SHALL be tracked via `async_on_remove` so that listener cleanup happens automatically on entity removal or integration reload.

#### Scenario: Curve tick wakes all three sensors

- **GIVEN** the integration is loaded with the master switch's adapt loop running
- **WHEN** a curve evaluation completes and fires the dispatcher signal
- **THEN** each of the three sensor entities SHALL execute its outputs-updated handler exactly once
- **AND** the three sensor states SHALL reflect the values just written to `hass.data[DOMAIN][entry.entry_id]["outputs"]`

#### Scenario: Per-entry signal isolation

- **GIVEN** two AL profiles A and B are both loaded
- **WHEN** profile A's curve tick fires its signal `f"{DOMAIN}_{entry_a.entry_id}_outputs_updated"`
- **THEN** profile A's three sensors SHALL update their state
- **AND** profile B's three sensors SHALL NOT execute their outputs-updated handler

#### Scenario: Sensor cleans up its dispatcher subscription on removal

- **GIVEN** an AL profile's sensors are subscribed to the dispatcher signal
- **WHEN** the config entry is unloaded
- **THEN** each sensor's dispatcher subscription SHALL be removed via the `async_on_remove`-registered unsubscribe handle
- **AND** subsequent fires of the dispatcher signal (during HA shutdown sequencing) SHALL NOT invoke the sensor's outputs-updated handler

### Requirement: Sensors report `STATE_UNKNOWN` before the first curve tick

Sensors SHALL NOT extend `RestoreEntity` or `RestoreSensor`. On entity addition (HA startup, integration reload, or config-entry creation), `_attr_native_value` SHALL be `None` until the first dispatcher signal fires after the first curve evaluation. HA will render `_attr_native_value=None` as the state value `unknown`.

#### Scenario: Fresh setup shows unknown until first tick

- **GIVEN** Home Assistant has just started and the integration is loading
- **WHEN** the three sensor entities first appear in the state machine
- **AND** the master switch has not yet completed its first curve evaluation
- **THEN** each sensor's state SHALL be `unknown`

#### Scenario: First curve tick after restart populates sensor state

- **GIVEN** the three sensors are in state `unknown` immediately after HA restart
- **WHEN** the master switch's first post-restart curve evaluation fires the dispatcher signal
- **THEN** each sensor's state SHALL update to its corresponding value from `hass.data[DOMAIN][entry.entry_id]["outputs"]`
- **AND** none of the sensors SHALL retain `unknown` after this tick

### Requirement: Sensors follow the `has_entity_name` composition

Every sensor entity created by this change SHALL set `_attr_has_entity_name = True` and SHALL register under the existing per-profile device record whose `name` matches the profile's display name (i.e. attached to the same device as the profile's switches and number entities). Each sensor's `_attr_name` SHALL be exactly the role label from the table in the first requirement of this spec: `"Output brightness"`, `"Output color temp"`, `"Sun elevation"`.

The resulting friendly names SHALL follow this table for a profile named `Dining MVP`:

| Sensor | `_attr_name` | Friendly name |
|---|---|---|
| Output-brightness sensor | `"Output brightness"` | `Dining MVP Output brightness` |
| Output-color-temp sensor | `"Output color temp"` | `Dining MVP Output color temp` |
| Sun-elevation sensor | `"Sun elevation"` | `Dining MVP Sun elevation` |

The chosen role labels SHALL NOT collide with any existing entity's `_attr_name` on the same device (specifically: not `"Brightness"`, which is the adapt-brightness switch's role per `add-runtime-range-controls`, and not `"Min color temp"` / `"Max color temp"`, which are the range-number roles).

#### Scenario: Friendly names compose from device name + sensor role

- **GIVEN** an AL profile is configured with display name "Dining MVP"
- **WHEN** the integration loads and the three sensors are registered
- **THEN** the output-brightness sensor's friendly name SHALL be exactly "Dining MVP Output brightness"
- **AND** the output-color-temp sensor's friendly name SHALL be exactly "Dining MVP Output color temp"
- **AND** the sun-elevation sensor's friendly name SHALL be exactly "Dining MVP Sun elevation"

#### Scenario: Sensor friendly names do not collide with switch or number friendly names

- **GIVEN** an AL profile exposes its three switches and four range numbers (per `add-runtime-range-controls` R7) and its three new output sensors
- **WHEN** all ten entities' friendly names are inspected
- **THEN** no two entities SHALL share the same friendly name
- **AND** specifically the adapt-brightness switch ("Dining MVP Brightness") and the output-brightness sensor ("Dining MVP Output brightness") SHALL be distinguishable strings
- **AND** the output-color-temp sensor ("Dining MVP Output color temp") SHALL be distinguishable from the "Min color temp" and "Max color temp" number entities

### Requirement: Ambient lux sensor mirrors the configured lux sensor's reading

The `ambient_lux` output sensor SHALL read the configured `lux_sensor` entity's numeric state on each curve tick and publish the value to `hass.data[DOMAIN][entry.entry_id]["outputs"]["ambient_lux"]`. If the source sensor is unavailable or non-numeric, the value SHALL be `None` (rendered as `unknown` in HA).

#### Scenario: Ambient lux reflects source sensor

- **GIVEN** `lux_sensor` is `sensor.office_illuminance` with state `"340"`
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["ambient_lux"]` SHALL be `340.0`
- **AND** the `ambient_lux` sensor entity state SHALL be `"340.0"`

#### Scenario: Source sensor unavailable results in unknown state

- **GIVEN** `lux_sensor` is configured but its state is `"unavailable"`
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["ambient_lux"]` SHALL be `None`
- **AND** the `ambient_lux` sensor entity state SHALL be `unknown`

### Requirement: Lux reduction sensor exposes the applied reduction as a percentage

The `lux_reduction` output sensor SHALL publish the brightness reduction the lux gate is applying, as a percentage, to `hass.data[DOMAIN][entry.entry_id]["outputs"]["lux_reduction"]`. The value SHALL be `100 − round(factor × 100)`, where `factor` is the retained brightness factor computed by the lux gate (`target_lux / current_lux`, capped at `1.0`). A value of `0` means no reduction (curve passes through); `50` means brightness was halved; values approaching `100` mean the lights are almost fully cut. When ambient lux is at or below target, the value SHALL be `0`. When the lux gate is inactive (no sensor configured, sensor unavailable, or `target_lux` is 0), the value SHALL be `None` (the sensor renders `unknown`).

#### Scenario: Lux reduction shows the applied reduction

- **GIVEN** `target_lux` is 500 and `lux_sensor` reads 700
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `29` (100 − 71, the retained 71.4% rounded)
- **AND** the `lux_reduction` sensor entity state SHALL be `"29"`

#### Scenario: No reduction shows 0%

- **GIVEN** `target_lux` is 500 and `lux_sensor` reads 300
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `0`

#### Scenario: Gate inactive shows unknown

- **GIVEN** no `lux_sensor` is configured (or it is unavailable, or `target_lux` is 0)
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `None`

### Requirement: Lux output sensors follow the same dispatcher pattern as existing sensors

The `ambient_lux` and `lux_reduction` sensors SHALL use the same `SIGNAL_OUTPUTS_UPDATED` dispatcher subscription as the three existing sensors. They SHALL NOT poll. `_attr_should_poll` SHALL be `False`. The dispatcher unsubscribe handle SHALL be tracked via `async_on_remove`.

#### Scenario: Lux sensors update on the same signal as existing sensors

- **GIVEN** the integration is loaded with `lux_sensor` configured
- **WHEN** a curve evaluation completes and fires the dispatcher signal
- **THEN** all five sensor entities SHALL execute their outputs-updated handler exactly once
