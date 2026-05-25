## 1. Constants and config schema

- [x] 1.1 Add `CONF_LUX_SENSOR` / `DEFAULT_LUX_SENSOR` (`""`) and `CONF_TARGET_LUX` / `DEFAULT_TARGET_LUX` (`0`) to `const.py` with `DOCS` entries [R: options-flow selectors, D4]
- [x] 1.2 Add both fields to `VALIDATION_TUPLES` — `lux_sensor` as `cv.entity_id`, `target_lux` as `int_between(0, 10000)` [R: options-flow selectors, D4]
- [x] 1.3 Add `ambient_lux` and `lux_reduction` entries to `OUTPUT_SENSORS` in `const.py` [R: output-sensors entity table, D7]

## 2. Pure lux-reduction math

- [x] 2.1 Implement `lux_reduce(curve_brightness, target_lux, current_lux, min_brightness) → float | None` in `color_and_brightness.py` [R: lux-feedback pure function, D2, D6]
- [x] 2.2 Unit tests for `lux_reduce`: above target, below target, exactly at target, below min_brightness → None, zero/negative current_lux → pass-through [R: lux-feedback pure function scenarios]

## 3. Config flow — Ambient lux section

- [x] 3.1 Add `_lux_sensor_selector()` factory returning `EntitySelector(domain="sensor", device_class="illuminance")` in `config_flow.py` [R: options-flow selectors, D4]
- [x] 3.2 Add `_target_lux_selector()` factory returning `NumberSelector(min=1, max=10000, step=10, unit="lx", mode=BOX)` [R: options-flow selectors, D4]
- [x] 3.3 Build the "Ambient lux" section in `_build_options_schema` — collapsed, `lux_sensor` always shown, `target_lux` conditional on `lux_sensor` being non-empty (same pattern as `send_split_delay`) [R: options-flow sections, options-flow conditionals, D4]
- [x] 3.4 Read the lux sensor's current state in `async_step_init` and pass it to `async_show_form` via `description_placeholders={"current_lux": lux_reading}` [R: options-flow live reading, D5]
- [x] 3.5 Add section, field labels, and description (with `{current_lux}` placeholder) to `strings.json` [R: options-flow live reading, D5]

## 4. Switch adapt path — lux gate integration

- [x] 4.1 In `switch.py` `_prepare_adaptation_data` (or its caller), read `lux_sensor` state from `self.hass.states.get()`, call `lux_reduce`, and replace `brightness_pct` in `self._settings` before service-data assembly [R: lux-feedback reduce-only gate, D1, D2, D6]
- [x] 4.2 Handle `lux_reduce` returning `None`: send `light.turn_off` with `transition`, set per-light `_lux_turned_off` flag [R: lux-feedback auto-off, D3, D9]
- [x] 4.3 Handle lux-off recovery: when `lux_reduce` returns non-`None` and `_lux_turned_off` is set, send `light.turn_on` with adjusted brightness and `initial_transition`, clear flag [R: lux-feedback auto-off recovery, D9]
- [x] 4.4 Register `async_track_state_change_event` on `lux_sensor` when configured, with 5pp significance guard; teardown in `async_will_remove_from_hass` [R: lux-feedback sensor subscription, D8]

## 5. Output sensors — lux values

- [x] 5.1 Publish `ambient_lux` and `lux_reduction` to the `outputs` cache dict alongside existing keys on each curve tick [R: output-sensors ambient lux, output-sensors lux reduction, D7]
- [x] 5.2 Conditionally create `_ambient_lux` and `_lux_reduction` sensor entities only when `lux_sensor` is configured; clean up entities on reconfigure when sensor is removed [R: output-sensors conditional creation]
- [x] 5.3 Ensure both new sensors subscribe to `SIGNAL_OUTPUTS_UPDATED` via the existing dispatcher pattern [R: output-sensors dispatcher pattern]

## 6. Strings and manifest

- [x] 6.1 Add `entity.sensor.ambient_lux` and `entity.sensor.lux_reduction` name entries to `strings.json` [R: output-sensors entity table]
- [x] 6.2 Bump minor version in `manifest.json` [D: non-breaking additive change]

## 7. Integration tests

- [x] 7.1 Test: profile without lux sensor — curve brightness unchanged, no lux output sensors created [R: lux-feedback graceful degradation, output-sensors conditional]
- [x] 7.2 Test: profile with lux sensor above target — brightness reduced by correct factor [R: lux-feedback reduce-only gate]
- [x] 7.3 Test: lux drives brightness below min_brightness — light turns off, turns back on when lux drops [R: lux-feedback auto-off and recovery, D9]
- [x] 7.4 Test: lux sensor becomes unavailable — falls back to curve brightness, warning logged once [R: lux-feedback graceful degradation]
- [x] 7.5 Test: lux sensor state change triggers re-adaptation (crossing target threshold) [R: lux-feedback sensor subscription, D8]
- [x] 7.6 Test: config flow shows live lux reading in description placeholder [R: options-flow live reading, D5]
- [x] 7.7 Test: conditional `target_lux` field visibility in options flow [R: options-flow conditionals]
