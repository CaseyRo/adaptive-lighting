## MODIFIED Requirements

### Requirement: Options dialog presents fields in named collapsible sections

The integration options dialog SHALL group its configurable fields into seven named sections, rendered using Home Assistant's `section()` schema helper. Section names and field membership SHALL match the layout below.

| Section | Default state | Fields |
|---|---|---|
| Targets | expanded | `lights` |
| Daytime curve | expanded | `min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`, `prefer_rgb_color` |
| Sun schedule | expanded | `sunrise_entity`, `sunset_entity` |
| Ambient lux | collapsed | `lux_sensor`, `target_lux` |
| Light control | expanded | `intercept`, `multi_light_intercept` |
| Advanced | collapsed | `interval`, `transition`, `initial_transition`, `adapt_delay`, `separate_turn_on_commands`, `send_split_delay`, `skip_redundant_commands` |
| Diagnostics | collapsed | `include_config_in_attributes` |

#### Scenario: User opens options dialog on a UI-managed entry

- **WHEN** the user navigates to Settings → Devices & Services → Adaptive Lighting → Configure
- **THEN** the form SHALL render seven sections in the order: Targets, Daytime curve, Sun schedule, Ambient lux, Light control, Advanced, Diagnostics
- **AND** the Ambient lux, Advanced, and Diagnostics sections SHALL be rendered in their collapsed state
- **AND** the Targets, Daytime curve, Sun schedule, and Light control sections SHALL be rendered expanded

#### Scenario: Each section contains only the fields specified for it

- **WHEN** the user expands any section in the options dialog
- **THEN** the fields shown in that section SHALL exactly match the field list in the table above for that section
- **AND** no field SHALL appear in more than one section

### Requirement: Conditional fields hide when their driver makes them irrelevant

Fields whose configuration is meaningful only under a specific value of another field ("driver") SHALL be omitted from the rendered schema when the driver value makes them inapplicable. When the driver value changes, the form SHALL be re-submitted to re-render with the updated field set.

The conditional pairs are:
- `send_split_delay` is conditional on `separate_turn_on_commands` being `true`.
- `target_lux` is conditional on `lux_sensor` being a non-empty string.

#### Scenario: send_split_delay hidden when transport mode disables it

- **WHEN** the user opens the options dialog with `separate_turn_on_commands` set to `false`
- **THEN** the Advanced section SHALL NOT include the `send_split_delay` field

#### Scenario: send_split_delay revealed when transport mode enables it

- **WHEN** the user toggles `separate_turn_on_commands` to `true` and submits the form
- **THEN** the options dialog SHALL re-render with `send_split_delay` present in the Advanced section
- **AND** the field SHALL accept values in the range 0–10000 milliseconds

#### Scenario: target_lux hidden when no lux sensor is selected

- **WHEN** the user opens the options dialog with `lux_sensor` set to `""` (empty)
- **THEN** the Ambient lux section SHALL show only the `lux_sensor` entity selector
- **AND** `target_lux` SHALL NOT appear

#### Scenario: target_lux revealed when lux sensor is selected

- **WHEN** the user selects a `lux_sensor` entity and submits the form
- **THEN** the options dialog SHALL re-render with `target_lux` present in the Ambient lux section
- **AND** the field SHALL accept values in the range 1–10000 lux

### Requirement: All configurable fields use native HA selectors

Every field in the options dialog SHALL be rendered using a class from `homeassistant.helpers.selector`. The selector mapping includes:

| Field type | Selector |
|---|---|
| Numeric range (brightness, color temp) | `NumberSelector` with explicit `min`, `max`, `step`, `unit_of_measurement`, `mode=SLIDER` |
| Duration (seconds) | `NumberSelector` with `unit_of_measurement="s"`, `mode=BOX` |
| Duration (milliseconds) | `NumberSelector` with `unit_of_measurement="ms"`, `mode=BOX` |
| Boolean | `BooleanSelector` |
| Entity (lights) | `EntitySelector` with `domain="light"`, `multiple=True` |
| Entity (sun events) | `EntitySelector` with `domain="sensor"`, `device_class="timestamp"` |
| Entity (lux sensor) | `EntitySelector` with `domain="sensor"`, `device_class="illuminance"` |
| Lux target | `NumberSelector` with `min=1`, `max=10000`, `step=10`, `unit_of_measurement="lx"`, `mode=BOX` |

#### Scenario: Lux sensor selector filters to illuminance sensors only

- **WHEN** the user opens the entity picker for `lux_sensor`
- **THEN** only entities with `domain == "sensor"` and `device_class == "illuminance"` SHALL appear in the picker
- **AND** temperature sensors, humidity sensors, and other non-illuminance sensors SHALL NOT appear

#### Scenario: Target lux renders as a number box with lux unit

- **WHEN** the user expands the Ambient lux section with a lux sensor configured
- **THEN** `target_lux` SHALL render as a numeric box input with range 1–10000, step 10
- **AND** the field SHALL display the unit "lx"

### Requirement: Ambient lux section shows the sensor's current reading

When a `lux_sensor` is configured and its state is numeric, the Ambient lux section description SHALL include the sensor's current reading via `description_placeholders`. This helps the user calibrate their `target_lux` to their actual space.

#### Scenario: Current lux reading shown in section description

- **GIVEN** `lux_sensor` is set to `sensor.office_illuminance`
- **AND** that sensor's current state is `"340"`
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL include the text "340 lx"

#### Scenario: No reading shown when sensor is not configured

- **GIVEN** `lux_sensor` is empty (not configured)
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL NOT include any lux reading number

#### Scenario: Fallback when sensor is unavailable

- **GIVEN** `lux_sensor` is configured but its state is `"unavailable"`
- **WHEN** the user opens the options dialog
- **THEN** the Ambient lux section description SHALL show a dash or "unavailable" in place of a numeric reading
