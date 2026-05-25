## Why

Adaptive Lighting sets brightness from a sun-curve — it knows the *time of day* but not the *actual light level in the room*. A room with skylights may already be bathed in 600 lux at noon; cranking the ceiling LEDs to 100 % is wasteful and glaring. The curve is right about *intent* but blind to *ambient conditions*. Closing the loop with a lux sensor lets the integration reduce brightness when daylight alone is sufficient, saving energy without sacrificing comfort. Rooms without a sensor keep the existing open-loop behaviour unchanged.

## What Changes

- **Reduce-only lux gate**: when a lux sensor reads *above* the user's target, the integration proportionally dims the lights using `factor = target_lux / current_lux`. When the sensor reads at or below target, the curve stands — the gate never *boosts* brightness. This one-way design eliminates the classic feedback spiral (lights on → sensor reads higher → integration dims → too dark → integration boosts → repeat) because reducing brightness can only lower lux, which self-stabilises.
- **Two new optional per-profile settings**:
  - `lux_sensor` — entity ID, pre-filtered in the UI to `domain=sensor, device_class=illuminance`.
  - `target_lux` — integer (lux). Only shown in the config flow when `lux_sensor` is populated.
- **Auto-off below min_brightness**: if the lux reduction drives the adjusted brightness below the profile's existing `min_brightness`, the lights turn off entirely — they're contributing effectively nothing.
- **Live lux reading in the config flow**: when a `lux_sensor` is already configured, the "Ambient lux" section description shows the sensor's current reading via `description_placeholders`, helping the user calibrate their target to their actual space.
- **Graceful degradation**: if `lux_sensor` is unavailable, unknown, or not configured, the profile falls back to pure curve brightness — no error, no manual intervention needed.
- **Two new output sensors**:
  - `ambient_lux` — pass-through of the configured lux sensor's current reading (unavailable when no sensor configured).
  - `lux_reduction` — the applied reduction factor as a percentage (100 % = no reduction, 50 % = halved). Unavailable when no sensor configured.
- **Color temperature unchanged** — the lux gate only affects brightness. Color temp stays on the sun curve.

## Capabilities

### New Capabilities
- `lux-feedback`: reduce-only ambient-lux gate — sensor binding, `target/current` proportional reduction, auto-off below `min_brightness`, and graceful degradation to curve-only mode.

### Modified Capabilities
- `options-flow`: adds the two new fields (`lux_sensor`, `target_lux`) to the config-flow UI and VALIDATION_TUPLES, in a new collapsed "Ambient lux" section with live-reading description placeholder.
- `output-sensors`: adds `ambient_lux` and `lux_reduction` sensors to the existing output-sensor set.

## Impact

- **`const.py`**: two new `CONF_` / `DEFAULT_` constants; two new entries in `VALIDATION_TUPLES`; two new entries in `OUTPUT_SENSORS`.
- **`config_flow.py`**: new "Ambient lux" section (collapsed) with entity selector filtered to `device_class=illuminance`, conditional `target_lux` number input, and `description_placeholders` for the live reading.
- **`color_and_brightness.py`**: new pure function `lux_reduce(curve_brightness, target_lux, current_lux, min_brightness) → float | None` — returns adjusted brightness or `None` (meaning turn off).
- **`switch.py`**: in the adapt path, read `lux_sensor` state and apply `lux_reduce` before assembling `service_data`. If result is `None`, send `light.turn_off` instead of `light.turn_on`. Subscribe to sensor state changes to trigger re-adaptation when lux shifts.
- **`strings.json`**: new section, field labels, and description with `{current_lux}` placeholder.
- **`manifest.json`**: minor version bump only (additive, non-breaking).
- **Tests**: unit tests for `lux_reduce` math (including edge cases: ratio exactly 1.0, sensor unavailable, result below min_brightness) + integration tests for sensor-available, sensor-unavailable, and no-sensor-configured paths.
