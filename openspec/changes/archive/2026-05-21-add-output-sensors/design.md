## Context

After `cdit-config-redesign` and `add-runtime-range-controls`, the master switch (`AdaptiveSwitch`) computes the curve outputs — brightness %, color-temperature K — once per `interval` tick (default 90 s) and exposes them as **attributes** via `self._settings` (`brightness_pct`, `color_temp_kelvin`, and a synthetic `sun_position` in [-1, +1] derived from the brightness curve). The values are visible in the master switch's More-info dialog and in diagnostics downloads, but HA's recorder stores `attributes` as text-on-state, not as numeric columns. The History panel, `apexcharts-card`, and `mini-graph-card` all consume entity *state*, not attributes.

The integration does not currently expose actual solar elevation. HA's built-in `sun.sun` entity carries an `elevation` attribute (float degrees, range -90 to +90, updated continuously by HA's `sun` integration). This change adds it as a graphable sensor alongside the curve outputs — useful for visualizing the astronomical driver next to the integration's response.

The fix is to expose those three already-computed values as dedicated `sensor` entities. The curve math doesn't change; the sensor platform is a thin presentation layer over values the switch is already computing.

The architectural question this design resolves is the **read path**: how do three sensor entities access the master switch's computed output without (a) recomputing the curve themselves, (b) tightly coupling to the switch's internal attribute API, or (c) introducing a third source of truth?

## Goals / Non-Goals

**Goals:**
- Three sensor entities per AL profile (`output_brightness`, `output_color_temp`, `sun_elevation`), each `SensorStateClass.MEASUREMENT` so HA's recorder graphs them as numerics.
- Single computation path. Curve evaluation happens once per tick in the master switch's adapt loop; sensors are pure readers.
- Push-based update: when the master switch finishes computing, sensors are notified and write their state. No polling, no duplicated `async_track_time_interval` timers.
- `has_entity_name = True` following the convention from `add-runtime-range-controls` Decision 11. Friendly names compose `<Profile> <Role>` and fit HA's narrow-card truncation window.
- Purely additive — the existing master-switch attributes (`brightness_pct`, `color_temp_kelvin`, `sun_position`, etc.) remain in place. Anyone reading them today keeps working.

**Non-Goals:**
- Removing or deprecating the existing master-switch attributes. They are diagnostic surface; their cost is zero and removing them would break diagnostics downloads.
- Per-light sensors (one sensor per controlled light entity). The output values are profile-level, not light-level.
- Historical aggregations (daily min/max, weekly averages). Recorder + statistics-card handles this externally once the values exist as sensor state.
- Mired-scale parallel sensors for color temp. Skipped per the proposal's open-question answer; if anyone ever needs mired, they can compute `1_000_000 / K` in a template.
- `device_class` on any of the three sensors. `SensorDeviceClass.TEMPERATURE` would be wrong for color temp (it's not thermal); brightness % has no fitting device class; sun-position is unitless. Setting a device_class wrongly is worse than setting none.
- Configurable update cadence separate from the curve tick. The curve interval governs both.

## Decisions

### Decision 1: Capability slug is `output-sensors`, scoped tight

**What we chose:** This change defines one new capability — `output-sensors` — covering the three sensor entities, their state-class configuration, the dispatcher-push update path, and the `has_entity_name` composition for sensors. No existing capability is modified.

**Why:** Matches the pattern from `cdit-config-redesign` Decision 10 and `add-runtime-range-controls` Decision 10. Tight scope keeps spec scenarios independently testable. "Output sensors" pairs cleanly with "runtime range controls" (the inputs that bound the curve) — together they form the read/write surface for the curve's value space.

**Alternatives considered:**
- **Roll into `runtime-range-controls`** (since both are entity-platform additions). Rejected — that capability is archived; reopening it conflates inputs with outputs and complicates the spec history.
- **Generic `sensors` capability** anticipating future sensor entities. Rejected — premature. Each future sensor addition can get its own focused capability.

### Decision 2: Master switch publishes outputs to `hass.data`; sensors read from there

**What we chose:** After each curve evaluation in `AdaptiveSwitch._update_attrs_and_maybe_adapt_lights` (where `self._settings` is populated from `SunLightSettings.get_settings()`), publish the values to:

```python
hass.data[DOMAIN][entry.entry_id]["outputs"] = {
    "output_brightness": <int 0-100>,        # from self._settings["brightness_pct"]
    "output_color_temp": <int K>,            # from self._settings["color_temp_kelvin"]
    "sun_elevation": <float degrees | None>, # from hass.states.get("sun.sun").attributes["elevation"]
    "updated_at": <datetime>,
}
```

The cache dict keys match the sensor `OUTPUT_SENSORS[*]["key"]` values exactly, so a sensor reads `hass.data[DOMAIN][entry.entry_id]["outputs"][self._output_key]` with no intermediate mapping. The master switch's existing attributes (`brightness_pct`, `color_temp_kelvin`, `sun_position` in [-1, +1]) are unchanged — the publish step copies the relevant values into the cache under the new key names; the old attributes remain on the switch for backward compatibility (per proposal). The new `sun_elevation` value is read fresh on each tick from `sun.sun` and has no counterpart on the master switch.

Sensors read from this dict at write-state time. The master switch writes; sensors read. One direction.

**Why:** Three options were on the table:
- **(a) Each sensor recomputes the curve.** Rejected — duplicates the curve math three times per tick; introduces drift risk if computation isn't bit-identical; sensors would need access to all the inputs (sun entities, range numbers, options) which inverts the dependency.
- **(b) Sensors read master-switch attributes via `hass.states.get(<master>).attributes["brightness_pct"]`.** Rejected — couples sensor lifecycle to the switch entity's published state, which is async (state lags compute by one event-bus hop), and breaks if the attribute key ever renames. Also doesn't help with `sun_elevation`, which has no source on the master switch.
- **(c) Master publishes to a runtime dict; sensors read from it.** Chosen — single source of computation, single source of truth at runtime, sensors are pure consumers. Tests mock the dict directly.

The `hass.data[DOMAIN][entry.entry_id]` pattern is the HA-idiomatic per-entry runtime cache; the integration already uses it for other state.

**Alternatives considered:** Above.

### Decision 3: Push updates via `async_dispatcher_send` keyed by entry_id

**What we chose:** After publishing to `hass.data`, the master switch calls:

```python
async_dispatcher_send(hass, f"{DOMAIN}_{entry.entry_id}_outputs_updated")
```

Each sensor subscribes to this exact signal in its `async_added_to_hass`. On receiving the signal, the sensor reads the relevant key from `hass.data[DOMAIN][entry.entry_id]["outputs"]` and calls `async_write_ha_state()`.

**Why:** Push beats poll: the data has already been computed when the signal fires, so the sensor's write is O(1) dict lookup + state write. No timer drift, no polling jitter. Keying the signal by `entry.entry_id` prevents profile-A's sensor from waking up when profile-B ticks (a global `DOMAIN`-level signal would do that).

**Alternatives considered:**
- **`should_poll = True` and a 30 s poll loop.** Rejected — polling cadence wouldn't align with the curve tick; sensors would update at a different rhythm than the values they expose; HA would also schedule three polling tasks per profile.
- **Each sensor schedules `async_track_time_interval` matching the curve `interval`.** Rejected — duplicates the master switch's scheduler; if the interval changes mid-run (via options-flow save), three independent timers need to be re-registered.
- **Sensor subscribes to the master switch's `state_changed` event.** Rejected — the master switch's state is on/off; its attributes change without a state_changed firing in HA's strict sense (attribute-only changes don't always emit). Brittle.

### Decision 4: All three sensors use `SensorStateClass.MEASUREMENT`, no `device_class`

**What we chose:**

| Sensor | `unique_id` suffix | `_attr_name` | unit | state_class | device_class | icon |
|---|---|---|---|---|---|---|
| Output brightness | `_output_brightness` | `"Output brightness"` | `"%"` | `MEASUREMENT` | (none) | `mdi:brightness-percent` |
| Output color temperature | `_output_color_temp` | `"Output color temp"` | `"K"` | `MEASUREMENT` | (none) | `mdi:thermometer` |
| Sun elevation | `_sun_elevation` | `"Sun elevation"` | `"°"` | `MEASUREMENT` | (none) | `mdi:weather-sunset` |

**Why:**
- `state_class: MEASUREMENT` is the trigger that makes HA's recorder graph the entity as a numeric series and surface it in the History panel + `apexcharts-card` automatically. This is the entire reason the change exists.
- No `device_class`: `SensorDeviceClass.TEMPERATURE` is for thermal sensors (°C/°F), not color temperature; brightness % has no fitting device class in HA's enum; HA has no `ELEVATION` or `ANGLE` device class for sun elevation either. Setting a device class wrongly forces HA's UI into the wrong unit-conversion behavior and is worse than setting none.
- Units: `"%"`, `"K"`, and `"°"` are all accepted by HA as free-form `native_unit_of_measurement` strings; they render in the UI without unit conversion. Sun elevation is the angle of the sun above (positive) or below (negative) the horizon, in degrees, range -90 to +90.
- Icons: brightness-percent for brightness pairs visually with the `mdi:brightness-3` / `mdi:brightness-7` already used on the range numbers; thermometer for color temp matches the range-number convention; weather-sunset for sun elevation is self-explanatory.

**Naming rationale (the asymmetric "Output" prefix):**
- `"Output brightness"` — `"Brightness"` collides with the adapt-brightness switch's friendly name ("Dining MVP Brightness") from `add-runtime-range-controls` R7. `"Output"` resolves the collision and parallels the capability name (`output-sensors`).
- `"Output color temp"` — no hard collision (the switch is `"Color"`, not `"Color temp"`), but kept the prefix for parallelism with brightness AND to disambiguate from the existing `"Min color temp"` / `"Max color temp"` number entities on the same device.
- `"Sun elevation"` — no prefix needed; no other entity on the device uses `"Sun"` in its name. Adding `"Output sun elevation"` would be inaccurate — sun elevation is not an integration output, it's a passthrough from `sun.sun`.

**Alternatives considered:**
- **`SensorDeviceClass.ILLUMINANCE`** for brightness. Rejected — illuminance is lux (a measured external value), not a target output percentage.
- **No `state_class`** to leave the recorder behavior implicit. Rejected — explicit `MEASUREMENT` is what makes the recorder treat the values as graphable; omitting it defeats the change.
- **Naming as `"Brightness"` / `"Color temp"` / `"Sun"`.** Rejected — collides with `"Brightness"` switch; `"Color temp"` is also ambiguous next to `"Min/Max color temp"` numbers.
- **Exposing the master switch's synthetic `sun_position` ([-1, +1]) instead of actual elevation.** Rejected — the synthetic value is a curve internal; users grep "where is the sun?" want degrees, not a normalized ratio. (Considered, then explicitly rejected; the synthetic attribute stays available for anyone who wants it.)
- **Symmetric `"Output sun elevation"`.** Rejected — `sun.sun` owns the elevation value; the integration is a passthrough.

### Decision 5: Sensor state before first tick is `STATE_UNKNOWN`

**What we chose:** Sensors do not extend `RestoreEntity`. On HA restart, `_attr_native_value` is `None` until the first curve evaluation publishes a value. The state appears as `unknown` in the UI for at most one `interval` (default 90 s) after startup.

**Why:** Restoring a stale value would be misleading — the sensor's whole purpose is to expose *current* curve output. A restored "65%" from before the restart is wrong if the sun has moved since. Showing `unknown` is honest. The window is short (≤90 s by default).

**Alternatives considered:**
- **`RestoreSensor` for continuity.** Rejected — restored value is by definition stale; the recorder already has the historical value for graphing purposes (it's stored persistently).
- **Compute an immediate first value during `async_added_to_hass` by reading the master switch's attributes.** Rejected — couples sensor setup ordering to switch setup ordering (which is the foot-gun Decision 2 explicitly avoids).

### Decision 6: Sensors use `has_entity_name = True`, same device record as switches and numbers

**What we chose:** Every sensor sets `_attr_has_entity_name = True` and attaches to the existing per-profile device record (`(DOMAIN, entry.entry_id)`). HA composes friendly names as `<entry.title> <_attr_name>`. Per Decision 4, the names become "Dining MVP Current brightness", "Dining MVP Current color temp", "Dining MVP Sun position".

**Why:** Consistency with `add-runtime-range-controls` Decision 11. All ten entities per profile (3 switches + 4 numbers + 3 sensors) appear on one device card; their friendly names compose uniformly; entity-ID slugs follow HA's standard pattern.

**Alternatives considered:** None worth listing — this is just applying the established convention.

### Decision 7: Platform forwarded in `__init__.py`; no new `const.py` constants beyond enumeration

**What we chose:** In `__init__.py`, `PLATFORMS` becomes `[Platform.SWITCH, Platform.NUMBER, Platform.SENSOR]`. In `const.py`, add an `OUTPUT_SENSORS` mapping (or three explicit dicts) capturing per-sensor metadata — exactly mirroring the `RANGE_ENTITIES` pattern from `add-runtime-range-controls`:

```python
OUTPUT_SENSORS = [
    {"key": "output_brightness", "name": "Output brightness", "unit": "%", "icon": "mdi:brightness-percent"},
    {"key": "output_color_temp", "name": "Output color temp", "unit": "K", "icon": "mdi:thermometer"},
    {"key": "sun_elevation",     "name": "Sun elevation",     "unit": "°", "icon": "mdi:weather-sunset"},
]
```

Sensor platform iterates this list. Tests reference it.

**Why:** Same data-driven pattern as the range entities — one source for setup + tests, no per-sensor class proliferation. Three instances of one class (`AdaptiveOutputSensor`) parameterized by the dict entry.

**Alternatives considered:**
- **Three separate sensor classes** (`BrightnessSensor`, `ColorTempSensor`, `SunPositionSensor`). Rejected — each class would be 90% identical; the dict-driven instantiation is shorter and easier to extend.
- **Class hierarchy with a base + three subclasses.** Rejected — overengineering for three uniform sensors with no behavioral divergence.

### Decision 8: `sun_elevation` is read from `sun.sun.attributes["elevation"]` on every curve tick

**What we chose:** During the master switch's curve-tick publish step, the integration reads `hass.states.get("sun.sun")` and writes `state.attributes.get("elevation")` (a float in degrees, range -90 to +90) into the cache as `outputs["sun_elevation"]`. If `sun.sun` is missing or the attribute is absent, the cache value is `None` and the sensor renders as `unknown`.

**Why:** `sun.sun` is a built-in HA entity present in every install — no integration check needed. Its `elevation` attribute is updated continuously by HA's `sun` integration (every ~30 s by default), so reading it once per AL curve tick (every 90 s default) is fresh enough. Reading at tick-time keeps all three sensors on the same update rhythm — one dispatcher signal, all three sensors update together.

**Alternatives considered:**
- **Subscribe to `state_changed` on `sun.sun` and update `sun_elevation` independently of the curve tick.** Rejected — adds a second update path with a different rhythm. Two sensors updating at 90 s and one at 30 s in the same dashboard card looks like a bug. The 60 s latency penalty is invisible (the sun moves about 0.25° in 60 s; below the integration's already-coarse "degree" rendering).
- **Use the configured `CONF_SUNRISE_ENTITY` / `CONF_SUNSET_ENTITY` source.** Rejected — those are timestamp sensors (next-rising / next-setting), not elevation sensors. Different domain.
- **Add a new `CONF_SUN_ELEVATION_ENTITY` config field defaulting to `sun.sun`.** Rejected — yet another knob; `sun.sun` works for everyone. Re-evaluate if anyone ever has a Sun2 elevation override use case.
- **Drop the `sun_elevation` sensor entirely.** Considered (option C from Q&A) and rejected — actual sun elevation is the canonical "where in the day are we?" data the user wants alongside the brightness/CT curve. Without it, the third sensor slot is missing the most-asked-for value.

### Decision 9: No service surface, no options-flow surface

**What we chose:** This change adds no services, no options-flow fields, no new config keys. The integration's `services.yaml`, `config_flow.py`, `strings.json` (apart from the three sensor name keys) are untouched.

**Why:** Sensors are read-only. Nothing to configure. The cadence is governed by the existing `interval` option, which already exists. Adding a "show sun_position" toggle, for example, is dead-code complexity — anyone who doesn't want the entity can hide it via HA's entity registry.

**Alternatives considered:**
- **Option to disable individual sensors.** Rejected — HA's entity registry already allows hiding entities per-user. Don't reinvent.

## Risks / Trade-offs

- **[Master switch and sensor compute paths could diverge in a future refactor]** → Mitigation: the master switch is the only place curve math runs; sensors do not duplicate it. Anyone moving curve math out of the master switch in the future will see the `hass.data[DOMAIN][entry_id]["outputs"]` publish line and the dispatcher signal as the explicit handoff; refactoring without preserving this contract would visibly break the sensors. Test 5.x asserts the contract.
- **[Sensor state stays `unknown` if the master switch's curve loop never runs]** → Possible if the switch fails to set up. Mitigation: that failure mode is already user-visible (the master switch entity itself shows as `unavailable`); the sensors merely echo it. No new debugging surface.
- **[Recorder explosion: 3 sensors × N profiles × MEASUREMENT state_class]** → For a 6-profile household (CDiT's case), that's 18 new sensors writing one row every 90 s = ~17 280 rows/day. Recorder + statistics handle this without strain; the values compress well. Mitigation: `recorder` config's `purge_keep_days` default (10 days) bounds disk usage; no action needed.
- **[`sun.sun` entity missing or `elevation` attribute absent]** → Possible during very early HA startup before the `sun` integration finishes loading, or in unusual deployments that disable `sun`. Mitigation: read with `.attributes.get("elevation")` so the cache value is `None`; the sensor renders as `unknown` until the next tick where `sun.sun` is populated. No exception is raised; the other two sensors continue updating normally.
- **[Two "sun" values present: `sensor.adaptive_lighting_<name>_sun_elevation` (degrees) vs. master switch's `sun_position` attribute ([-1, +1])]** → Could confuse users grepping for "sun" in diagnostics. Mitigation: the names are distinct ("elevation" vs "position") and the units differ; the README change should call out both with a one-line "these are different things" note.
- **[Dispatcher signal name collision across integrations or future changes]** → The signal `{DOMAIN}_{entry_id}_outputs_updated` is keyed both by domain and entry ID, so collisions are impossible across integrations (domain prefix) and across profiles (entry_id suffix). Future intra-domain signals should follow the same pattern.
- **[Sensor entities appear during the brief window when the master switch hasn't yet computed]** → Sensors show `unknown` for up to 90 s. Mitigation: documented; this is the recorder-correct behavior. Users seeing `unknown` in a dashboard for the first time after a restart can re-check in a minute.
- **[Friendly-name "Output brightness" / "Output color temp" approaches HA's narrow-card truncation point (~28 char window)]** → For a profile titled "Dining MVP", "Dining MVP Output brightness" is exactly 28 characters; longer profile titles will truncate to "Dining MVP Output bright…" or worse. Mitigation: users can rename the entity in HA's UI if truncation bothers them; the entity-ID slug is independent of the friendly name. This is the same trade-off accepted in `add-runtime-range-controls` R7 for the four range numbers.

## Migration Plan

Single PR on the fork's `main` branch. Depends on `cdit-config-redesign` and `add-runtime-range-controls` (both archived). Additive — no breaking changes.

1. Add the `sensor` platform per the decisions above.
2. Wire the master switch's compute loop to publish outputs + fire the dispatcher signal.
3. Add the three sensor entities, the `OUTPUT_SENSORS` mapping in `const.py`, the new `strings.json` keys.
4. Add `tests/test_sensor_platform.py` covering entity creation, state-class assertions, push-update flow, fallback to `unknown`, and friendly-name composition.
5. Tag release (`v2.3.0-cdit.1` or whatever the next minor is) — minor bump, no breaking change.
6. Existing config entries pick up three new sensors on next HA restart. No user action required.

**Rollback:** revert the PR. The three sensor entities disappear from the entity registry; the master switch attributes (`brightness_pct`, `color_temp_kelvin`, `sun_position`, etc. — all from `self._settings`) remain unchanged because they were never removed. Any History/`apexcharts-card` configs pointing at the new sensors will show "entity not found" until the rollback is reverted again. No data loss.

## Open Questions

None. All nine decisions resolved. The "should sensors be `RestoreSensor`?" question is settled by Decision 5 (no — stale data is misleading; `unknown` for one tick is honest). The "where does sun elevation come from?" question is settled by Decision 8 (`sun.sun.attributes.elevation`).
