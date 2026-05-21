## Why

The integration's runtime outputs — current target brightness %, current target color temperature in K — exist today only as `attributes` on the master switch entity (`brightness_pct`, `color_temp_kelvin`, alongside synthetic `sun_position` and others, all from `self._settings`). HA's recorder stores attribute values as text-on-state, so the History panel, `apexcharts-card`, `mini-graph-card`, and any "show me yesterday's AL curve" automation can't graph them as numerics. The values are visible but not analytically usable.

Separately, the actual solar elevation angle (degrees, sourced from HA's built-in `sun.sun` entity's `elevation` attribute) is genuinely useful to graph alongside the curve outputs — it shows the astronomical driver next to the integration's response. The master switch does not currently expose this value at all (its `sun_position` attribute is a synthetic [-1, +1] float derived from the brightness curve, not real elevation).

This change promotes those three outputs to first-class `sensor` entities per AL profile, with `SensorStateClass.MEASUREMENT` so the recorder graphs them and stock cards consume them natively. This is the explicit complement to the just-killed `add-lovelace-card` proposal: stock Lovelace + `apexcharts-card` becomes the charting story once the data lives on entities the cards can read.

## What Changes

- **Add a `sensor` platform** to the integration. Each AL config entry creates three sensor entities:
  - `sensor.adaptive_lighting_<name>_output_brightness` — current target brightness sourced from `self._settings["brightness_pct"]`, integer `%`, range 0–100, `state_class: measurement`, `icon: mdi:brightness-percent`. "Output" prefix disambiguates from the existing "Brightness" switch and "Min/Max brightness" number entities on the same device.
  - `sensor.adaptive_lighting_<name>_output_color_temp` — current target color temperature sourced from `self._settings["color_temp_kelvin"]`, integer `K`, range 1000–10000, `state_class: measurement`, no `device_class` (`SensorDeviceClass.TEMPERATURE` is wrong; color temp is not thermal), `icon: mdi:thermometer`. "Output" prefix maintains parallelism with brightness and disambiguates from "Min/Max color temp" numbers.
  - `sensor.adaptive_lighting_<name>_sun_elevation` — solar elevation angle in degrees, sourced from HA's built-in `sun.sun` entity's `elevation` attribute (range roughly -90 to +90), `state_class: measurement`, `unit: "°"`, `icon: mdi:weather-sunset`. Read on every curve tick alongside the brightness/color outputs. No prefix needed; no existing entity uses "Sun" in its name. Distinct from the master switch's existing synthetic `sun_position` attribute (which stays unchanged for backward compatibility).
- **Single read path**: sensors read the same curve-math outputs the master switch's adapt loop already computes — no second computation pass. The sensors update on the same tick as the existing curve evaluation (`interval` setting, default 90 s).
- **`has_entity_name = True`** following the convention established in `add-runtime-range-controls` Decision 11. Friendly names become `<Profile> Output brightness`, `<Profile> Output color temp`, `<Profile> Sun elevation`.
- **No removal of the existing master-switch attributes.** They stay for backward compat with anyone reading them today (including the integration's own diagnostics). The sensors are additive; users adopt them at their own pace.
- **No service surface changes.** Sensors are read-only by nature; nothing to call.

## Capabilities

### New Capabilities

- `output-sensors`: per-profile sensor entities exposing the curve's current outputs (brightness %, color temp K, sun position float). Covers entity creation, the read path from curve math, state-class configuration for recorder graphing, naming convention, and removal lifecycle.

### Modified Capabilities

None. Sensors are purely additive: existing switches, number entities, and options flow are unchanged.

## Impact

- **`custom_components/adaptive_lighting/sensor.py`** — new file, `sensor` platform implementation. One sensor class (`AdaptiveOutputSensor`) parameterized by output key (`output_brightness` | `output_color_temp` | `sun_elevation`); three instances per config entry.
- **`custom_components/adaptive_lighting/const.py`** — `Platform.SENSOR` appended to the platform list; sensor unique-id pattern constants; output-key enum.
- **`custom_components/adaptive_lighting/__init__.py`** — `async_setup_entry` forwards setup to the new sensor platform. Master switch's adapt loop publishes its computed outputs to a per-entry runtime data structure (`hass.data[DOMAIN][entry.entry_id]`) that the sensors read on update — or sensors read the master switch's existing computed attributes directly, TBD in design.
- **`custom_components/adaptive_lighting/switch.py`** — no behavioral change; if the design picks the "publish to `hass.data`" approach, the master switch gains one or two lines to update that dict.
- **`tests/test_sensor_platform.py`** — new file. Tests: entity creation on first setup; sensor state matches curve output; state_class and unit attributes are correct; removal cleans up entities; sensors survive an options-flow save (reload via `OptionsFlowWithReload`); `has_entity_name` produces the expected friendly names.
- **No new runtime dependencies.** No external services. No new config fields.

**Sequencing**: depends on `cdit-config-redesign` (3-switch model, `has_entity_name` convention) and `add-runtime-range-controls` (the curve math reads from the four `number` entities, which is what these sensors expose the output of). Both archived. No other in-flight dependencies. Net version bump: minor (`v2.2.0-cdit.1` or similar — no breaking change, the existing master-switch attributes stay).
