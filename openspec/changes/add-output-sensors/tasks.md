<!--
Annotations:
  R1–R5  = ADDED Requirements in specs/output-sensors/spec.md
           R1 = "Each AL profile exposes three output sensor entities"
           R2 = "Curve evaluation publishes outputs to a runtime cache"
           R3 = "Sensors update via a per-entry dispatcher signal"
           R4 = "Sensors report STATE_UNKNOWN before the first curve tick"
           R5 = "Sensors follow the has_entity_name composition"
  D1–D8  = Decisions in design.md
  polish = Quality/UX tasks not directly traceable to a requirement

Build order: group 1 is platform foundation. Group 2 wires the master switch's
output-publish + dispatcher fire. Group 3 implements the sensor class. Group 4 is
tests. Group 5 is strings + docs. Group 6 is manual verification. Group 7 is the
validation gate.
-->

## 1. Platform foundation — `sensor.py` skeleton and `const.py` mapping

- [ ] 1.1 Add `Platform.SENSOR` to the `PLATFORMS` list in `__init__.py` so HA forwards `async_setup_entry` to the new platform. [R1, D7]
- [ ] 1.2 In `const.py`, add an `OUTPUT_SENSORS` list with three entries — each a dict of `key`, `name`, `unit`, `icon`. Keys: `output_brightness` / `output_color_temp` / `sun_position`. Names: `"Output brightness"` / `"Output color temp"` / `"Sun position"`. Units: `"%"` / `"K"` / `"°"`. Icons: `mdi:brightness-percent` / `mdi:thermometer` / `mdi:weather-sunset`. One source for setup + tests. [R1, D4, D7]
- [ ] 1.3 Create `custom_components/adaptive_lighting/sensor.py` with `async_setup_entry(hass, config_entry, async_add_entities)` that instantiates three entities (one per entry in `OUTPUT_SENSORS`) and calls `async_add_entities(entities)`. [R1]
- [ ] 1.4 Use the shared `device_info` helper so the three new entities attach to the same `(DOMAIN, entry.entry_id)` device as the switches and number entities. [R1, R5, D6]

## 2. Output publishing — master switch writes to `hass.data` and fires dispatcher

- [ ] 2.1 In `switch.py`, locate the existing point where `AdaptiveSwitch._async_update_attrs` (or the equivalent compute path) sets `current_brightness`, `current_color_temp`, `sun_position` on itself. Add a publish step immediately after the compute completes and before the switch's own state write. [R2, D2]
- [ ] 2.2 The publish SHALL set `hass.data[DOMAIN][entry.entry_id]["outputs"]` to a dict with keys `output_brightness` (int 0-100), `output_color_temp` (int K), `sun_position` (float degrees), `updated_at` (datetime). The cache dict keys SHALL match the `OUTPUT_SENSORS[*]["key"]` values exactly so sensors read with no intermediate mapping. The master switch's own `current_brightness` / `current_color_temp` / `sun_position` attributes stay unchanged. Ensure `hass.data[DOMAIN][entry.entry_id]` exists (initialize in `async_setup_entry` if needed). [R2, D2]
- [ ] 2.3 Immediately after publishing, call `async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_outputs_updated")`. Import `async_dispatcher_send` from `homeassistant.helpers.dispatcher`. [R3, D3]
- [ ] 2.4 In `async_setup_entry`, initialize `hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})["outputs"] = None` before forwarding platform setups, so sensors that read before the first tick see an empty/`None` slot rather than a `KeyError`. [R2, R4]

## 3. Sensor entity class — `AdaptiveOutputSensor`

- [ ] 3.1 Define `AdaptiveOutputSensor(SensorEntity)` in `sensor.py` with `_attr_has_entity_name = True`, `_attr_should_poll = False`, `_attr_state_class = SensorStateClass.MEASUREMENT`. Constructor takes `(hass, entry, output_key, name, unit, icon)`. [R1, R3, R5, D2, D3, D4, D6]
- [ ] 3.2 Implement `unique_id` property as `f"{entry.entry_id}_{output_key}"`. [R1, D7]
- [ ] 3.3 Set `_attr_name` on each instance to the role label from `OUTPUT_SENSORS` ("Output brightness", "Output color temp", "Sun position"). [R5, D4, D6]
- [ ] 3.4 Set `_attr_native_unit_of_measurement` from the entry's `unit` (or `None` for sun position) and `_attr_icon` from the entry's `icon`. Set `_attr_device_class = None` explicitly so future contributors see this is intentional. [R1, D4]
- [ ] 3.5 Initialize `_attr_native_value = None` in `__init__`. The sensor renders as `unknown` until the first dispatcher signal fires. Do NOT extend `RestoreEntity` or `RestoreSensor`. [R4, D5]
- [ ] 3.6 Implement `async_added_to_hass`: subscribe to `f"{DOMAIN}_{entry.entry_id}_outputs_updated"` via `async_dispatcher_connect`; register the unsubscribe handle via `self.async_on_remove(...)`. [R3, D3]
- [ ] 3.7 Implement the signal handler `_handle_outputs_updated`: read `hass.data[DOMAIN][entry.entry_id]["outputs"][output_key]`, set `_attr_native_value`, call `async_write_ha_state()`. Guard against the `outputs` slot being `None` (early dispatcher fire) — in that case do nothing. [R3, R4, D3]

## 4. Tests — `tests/test_sensor_platform.py`

- [ ] 4.1 New test file `tests/test_sensor_platform.py` with the existing autouse PHACC fixture from `conftest.py`. [R1]
- [ ] 4.2 Test: creating a new config entry registers exactly three `sensor` entities owned by the entry, with unique-id suffixes `_output_brightness`, `_output_color_temp`, `_sun_position`. [R1]
- [ ] 4.3 Test: each of the three sensors is attached to the same device as the profile's switches and number entities. [R1, R5]
- [ ] 4.4 Test: sensor metadata — `output_brightness` declares `unit="%"`, `state_class=MEASUREMENT`, no `device_class`; `output_color_temp` declares `unit="K"`, `state_class=MEASUREMENT`, no `device_class`; `sun_position` declares `unit="°"`, `state_class=MEASUREMENT`, no `device_class`. [R1, D4]
- [ ] 4.5 Test: `_attr_should_poll` is `False` on all three sensors. [R3]
- [ ] 4.6 Test: master switch's curve tick publishes the four expected keys (`output_brightness`, `output_color_temp`, `sun_position`, `updated_at`) into `hass.data[DOMAIN][entry.entry_id]["outputs"]`. Use a synthetic tick (call the compute path directly) and assert the dict state. [R2]
- [ ] 4.7 Test: firing `async_dispatcher_send(hass, f"{DOMAIN}_{entry_id}_outputs_updated")` causes the three sensor states to update to the values currently in `hass.data[DOMAIN][entry_id]["outputs"]`. [R3]
- [ ] 4.8 Test: signal isolation — for two profiles A and B, firing A's signal updates A's three sensors but does NOT update B's. [R3]
- [ ] 4.9 Test: sensors do not import or call curve math. Inspect the sensor class's `async_added_to_hass` and signal handler for absence of `SunLightSettings` references and absence of `hass.states.get` for sun-time / range-number entities. [R2]
- [ ] 4.10 Test: before the first dispatcher signal, all three sensor states are `unknown`. After firing the signal with a populated `outputs` dict, the states match the dict values. [R4]
- [ ] 4.11 Test: friendly-name composition produces "Dining MVP Output brightness", "Dining MVP Output color temp", "Dining MVP Sun position" for a profile titled "Dining MVP". Assert no friendly name collides with the adapt-brightness switch's "Dining MVP Brightness" or the "Min/Max color temp" number entities. [R5, D4, D6]
- [ ] 4.12 Test: unloading the config entry removes the three sensor entities AND removes their dispatcher subscriptions (firing the signal post-unload does not invoke the handler). Use a spy on the handler or count handler invocations. [R3]
- [ ] 4.13 Verify existing `tests/test_switch_platform.py` (or equivalent) still passes after the master switch gains the output-publish + dispatcher-fire step. [R2, polish]

## 5. Translations and docs

- [ ] 5.1 Add `entity.sensor.output_brightness.name`, `entity.sensor.output_color_temp.name`, `entity.sensor.sun_position.name` keys to `strings.json` matching the `_attr_name` values. [R5, polish]
- [ ] 5.2 Mirror the additions in `translations/en.json`. Other locales out of scope. [R5, polish]
- [ ] 5.3 Add a short section to `README.md` under "What's new in 2.x" naming the three sensors, explaining they enable History-panel and `apexcharts-card` graphing of the curve outputs, and showing a one-line YAML example of an `apexcharts-card` consuming `sensor.adaptive_lighting_<name>_output_brightness`. [polish, D4]
- [ ] 5.4 Append a release entry to `CHANGELOG.md` listing: 3 new sensor entities per profile, `SensorStateClass.MEASUREMENT` for recorder graphing, push-update via dispatcher, no behavioral change to existing switches / number entities. [polish]

## 6. Manual verification on live HA

- [ ] 6.1 Deploy to `homeassistant.onca-blenny.ts.net` via HACS. Verify the three `sensor.adaptive_lighting_*` entities (`_output_brightness`, `_output_color_temp`, `_sun_position`) appear under each profile's device. [R1, polish]
- [ ] 6.2 Open the History panel for one profile's `output_brightness` sensor. Verify the curve over ~10 minutes shows numeric values graphed as a continuous line (proves `state_class=MEASUREMENT` is honored by the recorder). Repeat for `output_color_temp` and `sun_position` (the last should range roughly -90° to +90° over a day). [R1, D4]
- [ ] 6.3 Add a temporary `apexcharts-card` to a dashboard pointing at one profile's three sensors. Verify all three render as numeric series. [R1, D4]
- [ ] 6.4 Restart HA. Verify each sensor briefly shows `unknown`, then populates with a value within one curve interval (default 90 s). [R4]
- [ ] 6.5 Verify the existing master switch attributes (`current_brightness`, `current_color_temp`, `sun_position`) are still present and unchanged on the switch entity's state — the sensors are additive, not a replacement. [polish, D2]

## 7. Validation gate

- [ ] 7.1 `openspec validate add-output-sensors --strict` returns green. [polish]
- [ ] 7.2 `uv run pytest tests/test_sensor_platform.py` passes. Existing tests stay green (`uv run pytest`). [polish]
- [ ] 7.3 `./scripts/lint` clean. [polish]
