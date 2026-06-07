# runtime-range-controls — delta for add-runtime-ramp-width

## RENAMED Requirements

- FROM: `### Requirement: Each AL profile exposes four runtime range entities`
- TO: `### Requirement: Each AL profile exposes five runtime curve entities`

## MODIFIED Requirements

### Requirement: Each AL profile exposes five runtime curve entities

For each Adaptive Lighting config entry, the integration SHALL create exactly five `number` entities: one for each of `min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`, and one for the curve's ramp half-width. The entities SHALL be registered on the `number` platform during `async_setup_entry` and torn down during `async_unload_entry`. Each entity SHALL share the same device record as the profile's three switches.

| Field | unique_id suffix | native_min | native_max | step | unit | mode |
|---|---|---|---|---|---|---|
| `min_brightness` | `_min_brightness` | 1 | 100 | 1 | `%` | `SLIDER` |
| `max_brightness` | `_max_brightness` | 1 | 100 | 1 | `%` | `SLIDER` |
| `min_color_temp` | `_min_color_temp` | 1000 | 10000 | 100 | `K` | `SLIDER` |
| `max_color_temp` | `_max_color_temp` | 1000 | 10000 | 100 | `K` | `SLIDER` |
| `ramp_half_width` | `_ramp_half_width` | 5 | 120 | 1 | `min` | `SLIDER` |

The full unique_id SHALL be `<entry.entry_id>_<suffix>`. The device record SHALL be the same `(DOMAIN, entry.entry_id)` identifier used by the profile's switches.

The ramp half-width entity SHALL set `_attr_name = "Ramp half-width"` and `suggested_object_id = "ramp_half_width"`, composing under `has_entity_name` exactly like the four range entities (friendly name for a profile named `Dining MVP`: `Dining MVP Ramp half-width`).

#### Scenario: A new config entry produces five number entities

- **WHEN** the user creates a new Adaptive Lighting config entry
- **AND** `async_setup_entry` completes
- **THEN** the entity registry SHALL contain five `number` entities owned by this entry
- **AND** their unique_ids SHALL end with `_min_brightness`, `_max_brightness`, `_min_color_temp`, `_max_color_temp`, `_ramp_half_width` respectively
- **AND** all five entities SHALL be attached to the same device as the profile's switches

#### Scenario: Number entity bounds match the options-flow selector bounds

- **WHEN** any of the four range number entities are inspected
- **THEN** the brightness entities SHALL declare `native_min_value=1`, `native_max_value=100`, `native_step=1`, `native_unit_of_measurement="%"`, and `mode=NumberMode.SLIDER`
- **AND** the color-temperature entities SHALL declare `native_min_value=1000`, `native_max_value=10000`, `native_step=100`, `native_unit_of_measurement="K"`, and `mode=NumberMode.SLIDER`

#### Scenario: Ramp half-width entity declares minute bounds

- **WHEN** the ramp half-width number entity is inspected
- **THEN** it SHALL declare `native_min_value=5`, `native_max_value=120`, `native_step=1`, `native_unit_of_measurement="min"`, and `mode=NumberMode.SLIDER`

## ADDED Requirements

### Requirement: Ramp half-width entity drives the curve transition width

The ramp half-width entity SHALL be the only user-facing surface for the curve's ramp half-width; the integration SHALL NOT add a corresponding options-flow field, and the entity SHALL be exempt from the options-flow seeding and propagation requirements that govern the four range entities (it has no `entry.options` mirror).

The entity SHALL extend `RestoreNumber`. On `async_added_to_hass` it SHALL prefer, in order: (1) the restored value from `RestoreNumber.async_get_last_number_data()`, (2) the default of 30 minutes (equal to the prior `RAMP_HALF_WIDTH_SECONDS` constant of 1800 seconds).

On every curve evaluation tick, the integration SHALL read the entity's state via the entity-registry lookup pattern (unique_id `<entry.entry_id>_ramp_half_width`), convert minutes to seconds, and use the result as `ramp_half_width_seconds` for that tick's curve computation. The value SHALL be read once per tick and the same number SHALL be supplied to both the curve evaluation and the sun-event day-anchoring (`anchor_sun_events`'s `half_width` parameter). When the entity is missing, `unavailable`, or `unknown`, the integration SHALL fall back to `RAMP_HALF_WIDTH_SECONDS` and SHALL log the fallback at `DEBUG` level.

Moving the slider SHALL NOT trigger an integration reload, matching the no-reload requirement of the four range entities.

#### Scenario: New entity defaults to 30 minutes

- **WHEN** a profile is created and the integration loads
- **THEN** the ramp half-width entity's state SHALL be 30
- **AND** the curve SHALL behave identically to the previous hardcoded 1800-second ramp

#### Scenario: Slider change takes effect on the next curve tick

- **GIVEN** the ramp half-width entity is at 30
- **WHEN** the user (or a Node-RED flow) sets it to 60
- **AND** the next curve evaluation tick fires
- **THEN** the brightness and color-temperature ramps SHALL each span sunrise ± 3600 s and sunset ± 3600 s
- **AND** `async_unload_entry` SHALL NOT be invoked

#### Scenario: Unavailable entity falls back to the constant

- **GIVEN** the ramp half-width entity is not yet available (e.g., early setup race)
- **WHEN** the curve evaluation runs
- **THEN** the curve SHALL be computed with `ramp_half_width_seconds = 1800`
- **AND** a `DEBUG` log entry SHALL be emitted naming the missing entity

#### Scenario: Value survives an HA restart

- **GIVEN** the user has set the ramp half-width entity to 75
- **WHEN** Home Assistant is restarted
- **THEN** the entity's state SHALL be 75 once it finishes loading

#### Scenario: Widened evening ramp completes past the sun-sensor flip

- **GIVEN** the ramp half-width entity is at 60
- **AND** the configured sunset entity has flipped to tomorrow's event (as `sensor.sun_next_setting` does at the sunset moment)
- **WHEN** the curve is evaluated 45 minutes after today's sunset
- **THEN** the day-anchoring SHALL still resolve the pair to today's events
- **AND** the computed brightness SHALL lie strictly between the profile's minimum and maximum (the down-ramp is still in progress, not snapped to minimum)
