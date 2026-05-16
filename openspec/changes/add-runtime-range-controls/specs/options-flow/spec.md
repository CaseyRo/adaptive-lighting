## MODIFIED Requirements

### Requirement: Brightness and color temperature follow a synthetic tanh curve

For each config entry, the integration SHALL synthesize the daytime brightness and color-temperature values using a hyperbolic-tangent curve anchored at the timestamps from `sunrise_entity` and `sunset_entity`, with a hardcoded half-width of 30 minutes (`RAMP_HALF_WIDTH_SECONDS = 1800`) at each event. The brightness value at time `t` SHALL follow:

- `t ≤ t_sunrise − 1800s`: value = configured minimum
- `t_sunrise − 1800s < t < t_sunrise + 1800s`: value = tanh-interpolated minimum → maximum
- `t_sunrise + 1800s ≤ t ≤ t_sunset − 1800s`: value = configured maximum
- `t_sunset − 1800s < t < t_sunset + 1800s`: value = tanh-interpolated maximum → minimum
- `t ≥ t_sunset + 1800s`: value = configured minimum

The same curve shape SHALL be applied to color temperature using `min_color_temp` and `max_color_temp` as the curve bounds.

The four bound values (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) SHALL be read at evaluation time from the four runtime range entities defined in the `runtime-range-controls` capability, with fallback to `entry.options[CONF_*]` when an entity is unavailable. The curve evaluation SHALL NOT read these four values directly from `entry.options` during normal operation.

#### Scenario: Brightness is at minimum well before sunrise

- **WHEN** the current time is more than 30 minutes before the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_min_brightness`

#### Scenario: Brightness is exactly at the midpoint at the sunrise event

- **WHEN** the current time equals the `sunrise_entity` timestamp
- **THEN** the computed brightness SHALL equal `(current_min_brightness + current_max_brightness) / 2`
- **WHERE** `current_min_brightness` and `current_max_brightness` are the current states of the corresponding number entities

#### Scenario: Brightness is at maximum during the day

- **WHEN** the current time is between `sunrise_entity + 30min` and `sunset_entity − 30min`
- **THEN** the computed brightness SHALL equal the current value of `number.adaptive_lighting_<name>_max_brightness`

#### Scenario: Color temperature follows the same curve shape

- **WHEN** the current time is at any point on the curve
- **THEN** the computed color temperature SHALL follow the same tanh interpolation between the current values of `number.adaptive_lighting_<name>_min_color_temp` and `_max_color_temp` as the brightness curve does between the two brightness entities

#### Scenario: Bound values are taken from runtime entities, not from entry.options

- **GIVEN** `entry.options[CONF_MIN_BRIGHTNESS]` is 5
- **AND** `number.adaptive_lighting_<name>_min_brightness` is at 30
- **WHEN** the curve is evaluated at a time before `sunrise_entity − 1800s`
- **THEN** the computed brightness SHALL equal 30 (the entity state), not 5 (`entry.options`)
