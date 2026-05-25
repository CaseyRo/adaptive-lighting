## MODIFIED Requirements

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

### Requirement: Lux reduction sensor exposes the applied factor as a percentage

The `lux_reduction` output sensor SHALL publish `factor × 100` to `hass.data[DOMAIN][entry.entry_id]["outputs"]["lux_reduction"]`, where `factor` is the value computed by the lux gate. A value of `100` means no reduction (curve passes through); `50` means brightness was halved. When the lux gate is inactive (sensor below target or unavailable), the value SHALL be `100`.

When the lights were turned off due to lux reduction (factor drove brightness below `min_brightness`), the value SHALL be `0`.

#### Scenario: Lux reduction shows the applied factor

- **GIVEN** `target_lux` is 500 and `lux_sensor` reads 700
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `71` (rounded from 71.4)
- **AND** the `lux_reduction` sensor entity state SHALL be `"71"`

#### Scenario: No reduction shows 100%

- **GIVEN** `target_lux` is 500 and `lux_sensor` reads 300
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `100`

#### Scenario: Lights-off due to lux shows 0%

- **GIVEN** the lux gate drove brightness below `min_brightness`
- **WHEN** a curve evaluation tick completes
- **THEN** `outputs["lux_reduction"]` SHALL be `0`

### Requirement: Lux output sensors follow the same dispatcher pattern as existing sensors

The `ambient_lux` and `lux_reduction` sensors SHALL use the same `SIGNAL_OUTPUTS_UPDATED` dispatcher subscription as the three existing sensors. They SHALL NOT poll. `_attr_should_poll` SHALL be `False`. The dispatcher unsubscribe handle SHALL be tracked via `async_on_remove`.

#### Scenario: Lux sensors update on the same signal as existing sensors

- **GIVEN** the integration is loaded with `lux_sensor` configured
- **WHEN** a curve evaluation completes and fires the dispatcher signal
- **THEN** all five sensor entities SHALL execute their outputs-updated handler exactly once
