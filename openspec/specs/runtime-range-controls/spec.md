# runtime-range-controls Specification

## Purpose
TBD - created by archiving change add-runtime-range-controls. Update Purpose after archive.
## Requirements
### Requirement: Entities persist their value across Home Assistant restarts

Each of the four range entities SHALL extend `homeassistant.components.number.RestoreNumber` so that its last known value is preserved across Home Assistant restarts without an explicit `Store` helper. On `async_added_to_hass`, each entity SHALL prefer in order: (1) the value present in `entry.options[CONF_*]` if that value is newer than the restored value (which is the case immediately after an options-flow save), (2) the restored value from `RestoreNumber.async_get_last_number_data()`, (3) the value present in `entry.options[CONF_*]` as the first-creation fallback.

#### Scenario: Slider value survives an HA restart

- **GIVEN** the user has moved `number.adaptive_lighting_<name>_min_brightness` to 30 via the dashboard
- **WHEN** Home Assistant is restarted
- **AND** the integration re-runs `async_setup_entry`
- **THEN** the entity's state SHALL be 30 once it finishes loading

#### Scenario: Options-flow save value wins over restored value

- **GIVEN** the user has previously moved the slider to 30 (restored state)
- **WHEN** the user opens the options flow, sets `min_brightness` to 50, and saves
- **AND** the integration reloads
- **THEN** the entity's state SHALL be 50, not 30

### Requirement: Curve math reads runtime ranges from the number entities

The brightness and color-temperature curve evaluation SHALL read its four bound values (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) by calling `hass.states.get(<entity_id>).state` for the corresponding number entity, casting to `int`, on every curve evaluation. The curve evaluation SHALL NOT read these four values from `entry.options` during normal operation.

When `hass.states.get(<entity_id>)` returns `None` or the state is `unavailable` or `unknown`, the curve evaluation SHALL fall back to the value in `entry.options[CONF_*]` and SHALL log the fallback at `DEBUG` level.

#### Scenario: Slider change takes effect on next curve tick

- **GIVEN** the integration is running with `number.adaptive_lighting_<name>_max_brightness` at 100
- **WHEN** the user moves the slider to 70
- **AND** the next curve evaluation tick fires
- **THEN** the brightness curve SHALL be computed with `value_max = 70`

#### Scenario: Entity-unavailable fallback uses entry.options

- **GIVEN** the four number entities are not yet available (e.g., during early setup race)
- **WHEN** the curve evaluation runs
- **THEN** the curve SHALL be computed using the values from `entry.options[CONF_*]`
- **AND** a `DEBUG` log entry SHALL be emitted naming the missing entity

### Requirement: Slider changes do not trigger an integration reload

Moving a slider on any of the four range entities SHALL NOT call `hass.config_entries.async_update_entry` for the owning config entry. The entity's new value SHALL take effect on the next curve evaluation tick without any reload of the integration, the device, or other entities.

#### Scenario: Slider drag does not reload the integration

- **GIVEN** the integration is loaded
- **WHEN** the user moves `number.adaptive_lighting_<name>_min_brightness` from 10 to 20 via the dashboard
- **THEN** `async_unload_entry` SHALL NOT be invoked
- **AND** `async_setup_entry` SHALL NOT be invoked
- **AND** the profile's switch entity IDs SHALL remain unchanged
- **AND** the entity's state SHALL update to 20

### Requirement: Options-flow save propagates new range values to the entities

When the user saves the options flow with new values for any of the four range fields, the resulting integration reload SHALL cause the four entities to be recreated with the just-saved values as their initial state. Once the reload completes, each entity's state SHALL match the value submitted in the options flow.

#### Scenario: Saving updated ranges in the options flow updates the sliders

- **GIVEN** `number.adaptive_lighting_<name>_min_brightness` is currently at 30
- **WHEN** the user opens the options flow, sets `min_brightness` to 55, and saves
- **THEN** the integration SHALL reload
- **AND** after the reload, the entity state SHALL be 55

### Requirement: Options-flow open seeds range fields from current entity state

When the options dialog is rendered, the default values shown for the four range fields (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) SHALL be read from the corresponding number entity's current state via `hass.states.get(<entity_id>).state` cast to `int`. The dialog SHALL NOT seed these four fields from `entry.options[CONF_*]` when entities exist and are available. If an entity is unavailable, the dialog SHALL fall back to `entry.options[CONF_*]` for that field.

The other ~14 fields in the options dialog SHALL continue to seed from `entry.options` as defined by the `options-flow` capability.

#### Scenario: Open options after live tuning shows live values

- **GIVEN** the user has moved `number.adaptive_lighting_<name>_max_brightness` from 100 (default) to 80 via the dashboard
- **WHEN** the user opens the options flow
- **THEN** the `max_brightness` field in the Daytime curve section SHALL show 80 as its default
- **AND** the other fields in the dialog SHALL show their `entry.options` values

### Requirement: All AL entities use HA's `has_entity_name` composition

Every entity created by this integration — the three switches (`AdaptiveSwitch`, `AdaptBrightnessSwitch`, `AdaptColorSwitch`) and the four range number entities — SHALL set `_attr_has_entity_name = True` and SHALL register under a device whose `name` matches the profile's display name (`entry.title`). The per-entity `_attr_name` SHALL carry only the entity's role, not the integration name or the profile name. The master switch (`AdaptiveSwitch`) SHALL set `_attr_name = None` so HA renders its friendly name as the device name alone.

The resulting friendly names SHALL follow this table for a profile named `Dining MVP`:

| Entity | `_attr_name` | Friendly name |
|---|---|---|
| Master switch | `None` | `Dining MVP` |
| Adapt-brightness switch | `"Brightness"` | `Dining MVP Brightness` |
| Adapt-color switch | `"Color"` | `Dining MVP Color` |
| Min brightness number | `"Brightness lower"` | `Dining MVP Brightness lower` |
| Max brightness number | `"Brightness upper"` | `Dining MVP Brightness upper` |
| Min color temp number | `"Color temp lower"` | `Dining MVP Color temp lower` |
| Max color temp number | `"Color temp upper"` | `Dining MVP Color temp upper` |

The range numbers use "lower/upper" wording (not "Min/Max") so the HA device page — which sorts entities alphabetically by friendly name — lists each quantity's lower bound before its upper bound. The number entities SHALL additionally pin `suggested_object_id` to their field key (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) so newly created profiles slug the same entity_ids as profiles created before the rename.

Existing `unique_id`s SHALL remain unchanged; the entity registry SHALL preserve existing `entity_id`s for any deployed install.

#### Scenario: Friendly names compose from device name + entity role

- **GIVEN** an AL profile is configured with display name "Dining MVP"
- **WHEN** the integration is loaded
- **THEN** the master switch's friendly name SHALL be exactly "Dining MVP"
- **AND** the adapt-brightness switch's friendly name SHALL be exactly "Dining MVP Brightness"
- **AND** the adapt-color switch's friendly name SHALL be exactly "Dining MVP Color"
- **AND** the four range number entities' friendly names SHALL be "Dining MVP Brightness lower", "Dining MVP Brightness upper", "Dining MVP Color temp lower", "Dining MVP Color temp upper"
- **AND** the four range number entities' entity_ids SHALL slug from the field keys (e.g. `number.dining_mvp_min_brightness`), not from the display names

#### Scenario: Existing entity_ids survive the rename

- **GIVEN** an entity registry contains a pre-existing `switch.adaptive_lighting_adapt_brightness_dining_mvp_lights` owned by this integration
- **WHEN** the integration is upgraded to a version that ships this `has_entity_name` change
- **AND** HA reloads the config entry
- **THEN** the entity's `entity_id` SHALL remain `switch.adaptive_lighting_adapt_brightness_dining_mvp_lights` (preserved by the registry via stable `unique_id`)
- **AND** only the entity's friendly name SHALL update to follow the new composition

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

