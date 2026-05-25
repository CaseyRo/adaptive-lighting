# lux-feedback Specification

## Purpose
Reduce-only ambient-lux gate that dims lights when daylight alone exceeds a user-set target. Uses a proportional `target/current` factor, turns lights off below `min_brightness`, and degrades gracefully when the sensor is unavailable or unconfigured. The gate only reduces brightness — it never boosts above the sun curve.

## Requirements
### Requirement: Reduce-only lux gate dims lights when ambient lux exceeds target

When a profile has both `lux_sensor` and `target_lux` configured, the integration SHALL apply a reduction factor to the curve-computed brightness on every adapt cycle. The factor SHALL be `target_lux / current_lux` when `current_lux > target_lux`, and `1.0` otherwise. The gate SHALL NOT increase brightness above the curve value under any circumstances.

The adjusted brightness SHALL be `curve_brightness × factor`, clamped to `[min_brightness, curve_brightness]`.

Color temperature SHALL NOT be affected by the lux gate — it SHALL remain on the sun curve.

#### Scenario: Ambient lux above target reduces brightness

- **WHEN** the curve computes brightness at 85%
- **AND** `target_lux` is 500
- **AND** `lux_sensor` reads 700
- **THEN** the integration SHALL send brightness of `85 × (500 / 700)` = 60.7%, rounded to the nearest integer (61%)

#### Scenario: Ambient lux at or below target passes curve through

- **WHEN** the curve computes brightness at 85%
- **AND** `target_lux` is 500
- **AND** `lux_sensor` reads 300
- **THEN** the integration SHALL send brightness of 85% (unchanged)

#### Scenario: Reduction never boosts above curve

- **WHEN** the curve computes brightness at 40%
- **AND** `target_lux` is 500
- **AND** `lux_sensor` reads 200
- **THEN** the integration SHALL send brightness of 40% (factor is 1.0, not 2.5)

#### Scenario: Exactly at target means no reduction

- **WHEN** `target_lux` is 500
- **AND** `lux_sensor` reads exactly 500
- **THEN** the factor SHALL be 1.0 and brightness SHALL equal the curve value

### Requirement: Lights turn off when lux reduction drives brightness below min_brightness

When the lux-adjusted brightness falls below the profile's `min_brightness`, the integration SHALL turn the light off instead of sending a negligible brightness value.

#### Scenario: Adjusted brightness below min_brightness turns light off

- **WHEN** the curve computes brightness at 80%
- **AND** `min_brightness` is 5
- **AND** `target_lux` is 500
- **AND** `lux_sensor` reads 10000
- **THEN** the adjusted brightness would be `80 × (500 / 10000)` = 4%, which is below `min_brightness` (5%)
- **AND** the integration SHALL send `light.turn_off` with the profile's `transition` time

#### Scenario: Lights turn back on when lux drops below target

- **GIVEN** the integration previously turned a light off due to lux reduction
- **WHEN** the next adapt cycle computes an adjusted brightness at or above `min_brightness`
- **THEN** the integration SHALL send `light.turn_on` with the adjusted brightness and the profile's `initial_transition` time

#### Scenario: Only lux-turned-off lights are restored

- **GIVEN** a light was manually turned off by the user
- **AND** the lux gate did not trigger the turn-off
- **WHEN** the lux sensor drops below target on a subsequent tick
- **THEN** the integration SHALL NOT turn that light back on
- **AND** only lights with the internal `_lux_turned_off` flag SHALL be eligible for lux-initiated turn-on

### Requirement: Graceful degradation when lux sensor is unavailable or unconfigured

When `lux_sensor` is not configured (empty string), OR the configured sensor's state is `unavailable` or `unknown`, the integration SHALL use the curve brightness without any lux adjustment. No error SHALL be logged for unconfigured sensors. A `WARNING`-level log SHALL be emitted once when a previously-available sensor becomes unavailable.

#### Scenario: No lux sensor configured

- **WHEN** `lux_sensor` is empty (not configured)
- **THEN** the integration SHALL skip the lux gate entirely
- **AND** brightness SHALL equal the curve value
- **AND** no error or warning SHALL be logged about lux

#### Scenario: Configured sensor becomes unavailable

- **GIVEN** `lux_sensor` is configured and was previously reporting a numeric value
- **WHEN** the sensor state changes to `unavailable`
- **THEN** the integration SHALL fall back to curve brightness
- **AND** a `WARNING` log SHALL be emitted once indicating the lux sensor is unavailable

#### Scenario: Sensor returns non-numeric state

- **GIVEN** `lux_sensor` is configured
- **WHEN** the sensor state is a non-numeric string (e.g. `"unknown"`)
- **THEN** the integration SHALL treat it as unavailable and fall back to curve brightness

### Requirement: Lux sensor state changes trigger re-adaptation

When `lux_sensor` is configured, the integration SHALL register an `async_track_state_change_event` listener on the lux sensor entity. On significant state changes, the listener SHALL trigger `_update_attrs_and_maybe_adapt_lights`.

A state change is significant when the resulting reduction factor changes by more than 5 percentage points compared to the last applied factor, OR the change crosses the target threshold (was below, now above — or vice versa).

The listener SHALL be removed during `async_will_remove_from_hass`.

#### Scenario: Lux crossing target triggers immediate re-adaptation

- **GIVEN** the lux sensor was reading 400 (below target of 500)
- **WHEN** the sensor reports 600 (above target)
- **THEN** the integration SHALL trigger a re-adaptation within the same event loop cycle
- **AND** the lights SHALL be dimmed according to the new factor

#### Scenario: Small lux fluctuation does not trigger re-adaptation

- **GIVEN** the lux sensor was reading 700 (factor = 500/700 = 71.4%)
- **WHEN** the sensor reports 710 (factor = 500/710 = 70.4%)
- **THEN** the change in factor is 1.0 percentage points, which is below the 5 pp threshold
- **AND** the integration SHALL NOT trigger a re-adaptation

#### Scenario: Listener is cleaned up on unload

- **GIVEN** the integration registered a state listener on the lux sensor
- **WHEN** the config entry is unloaded
- **THEN** the listener SHALL be removed
- **AND** subsequent sensor state changes SHALL NOT invoke the handler

### Requirement: `lux_reduce` is a pure function in `color_and_brightness.py`

The lux reduction logic SHALL be implemented as a standalone pure function `lux_reduce(curve_brightness, target_lux, current_lux, min_brightness)` in `color_and_brightness.py`. The function SHALL return a `float` (adjusted brightness) or `None` (turn off). It SHALL NOT access HA state, entity registries, or any global mutable state.

#### Scenario: Function returns None when below min_brightness

- **WHEN** `lux_reduce(80.0, 500, 10000, 5)` is called
- **THEN** the return value SHALL be `None` (80 × 0.05 = 4.0, below min 5)

#### Scenario: Function returns adjusted brightness when above min

- **WHEN** `lux_reduce(85.0, 500, 700, 5)` is called
- **THEN** the return value SHALL be approximately 60.7

#### Scenario: Function returns curve brightness when current ≤ target

- **WHEN** `lux_reduce(85.0, 500, 300, 5)` is called
- **THEN** the return value SHALL be 85.0

#### Scenario: Function handles zero and negative current_lux safely

- **WHEN** `lux_reduce(85.0, 500, 0, 5)` is called
- **THEN** the return value SHALL be 85.0 (treat zero/negative as "no data", pass through)
