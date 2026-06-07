# options-flow — delta for add-runtime-ramp-width

## MODIFIED Requirements

### Requirement: Brightness and color temperature follow a synthetic tanh curve

For each config entry, the integration SHALL synthesize the daytime brightness and color-temperature values using a hyperbolic-tangent curve anchored at the timestamps from `sunrise_entity` and `sunset_entity`, with a half-width `W` at each event. `W` SHALL be read at evaluation time from the profile's ramp half-width runtime entity as defined in the `runtime-range-controls` capability (default 30 minutes, falling back to `RAMP_HALF_WIDTH_SECONDS = 1800` when the entity is unavailable). The brightness value at time `t` SHALL follow:

- `t ≤ t_sunrise − W`: value = configured minimum
- `t_sunrise − W < t < t_sunrise + W`: value = tanh-interpolated minimum → maximum
- `t_sunrise + W ≤ t ≤ t_sunset − W`: value = configured maximum
- `t_sunset − W < t < t_sunset + W`: value = tanh-interpolated maximum → minimum
- `t ≥ t_sunset + W`: value = configured minimum

The same curve shape SHALL be applied to color temperature using `min_color_temp` and `max_color_temp` as the curve bounds. Both channels SHALL use the same `W` within a single evaluation.

The four bound values (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) SHALL be read at evaluation time from the four runtime range entities defined in the `runtime-range-controls` capability, with fallback to `entry.options[CONF_*]` when an entity is unavailable. The curve evaluation SHALL NOT read these four values directly from `entry.options` during normal operation.

#### Scenario: Brightness is at minimum well before sunrise

- **WHEN** the current time is more than `W` before the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_min_brightness`

#### Scenario: Brightness is exactly at the midpoint at the sunrise event

- **WHEN** the current time equals the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal `(current_min_brightness + current_max_brightness) / 2`
- **WHERE** `current_min_brightness` and `current_max_brightness` are the current states of the corresponding number entities

#### Scenario: Brightness is at maximum during the day

- **WHEN** the current time is between `sunrise_entity + W` and `sunset_entity − W`
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_max_brightness`

#### Scenario: Color temperature follows the same curve shape

- **WHEN** the current time is at any point on the curve
- **THEN** the computed color temperature SHALL follow the same tanh interpolation between the current values of `number.adaptive_lighting_<name>_min_color_temp` and `_max_color_temp` as the brightness curve does between the two brightness entities

#### Scenario: Bound values are taken from runtime entities, not from entry.options

- **GIVEN** `entry.options[CONF_MIN_BRIGHTNESS]` is 5
- **AND** `number.adaptive_lighting_<name>_min_brightness` is at 30
- **WHEN** the curve is evaluated at a time before `sunrise_entity − W`
- **THEN** the computed brightness SHALL equal 30 (the entity state), not 5 (`entry.options`)

#### Scenario: Curve width follows the ramp half-width entity

- **GIVEN** the profile's ramp half-width entity is at 60
- **WHEN** the curve is evaluated 45 minutes before the `sunset_entity` timestamp
- **THEN** the computed brightness SHALL lie strictly between the configured minimum and maximum (inside the widened down-ramp)
- **AND** with the entity at 30 the same instant would have produced the configured maximum (outside the default-width ramp)
