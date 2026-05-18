## Context

After `cdit-config-redesign` and `add-runtime-range-controls`, the master switch (`AdaptiveSwitch`) computes the curve outputs — brightness %, color-temperature K, and the sun-position float driving the curve — once per `interval` tick (default 90 s) and exposes them as **attributes** (`current_brightness`, `current_color_temp`, `sun_position`). The values are visible in the master switch's More-info dialog and in diagnostics downloads, but HA's recorder stores `attributes` as text-on-state, not as numeric columns. The History panel, `apexcharts-card`, and `mini-graph-card` all consume entity *state*, not attributes.

The fix is to expose those three already-computed values as dedicated `sensor` entities. The curve math doesn't change; the sensor platform is a thin presentation layer over values the switch is already computing.

The architectural question this design resolves is the **read path**: how do three sensor entities access the master switch's computed output without (a) recomputing the curve themselves, (b) tightly coupling to the switch's internal attribute API, or (c) introducing a third source of truth?

## Goals / Non-Goals

**Goals:**
- Three sensor entities per AL profile (`output_brightness`, `output_color_temp`, `sun_position`), each `SensorStateClass.MEASUREMENT` so HA's recorder graphs them as numerics.
- Single computation path. Curve evaluation happens once per tick in the master switch's adapt loop; sensors are pure readers.
- Push-based update: when the master switch finishes computing, sensors are notified and write their state. No polling, no duplicated `async_track_time_interval` timers.
- `has_entity_name = True` following the convention from `add-runtime-range-controls` Decision 11. Friendly names compose `<Profile> <Role>` and fit HA's narrow-card truncation window.
- Purely additive — the existing master-switch attributes (`current_brightness`, etc.) remain in place. Anyone reading them today keeps working.

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

**What we chose:** After each curve evaluation in `AdaptiveSwitch._async_update_attrs` (or wherever the integration currently sets `current_brightness` / `current_color_temp` / `sun_position`), publish the same three values to:

```python
hass.data[DOMAIN][entry.entry_id]["outputs"] = {
    "output_brightness": <int 0-100>,
    "output_color_temp": <int K>,
    "sun_position": <float, degrees of solar elevation>,
    "updated_at": <datetime>,
}
```

The cache dict keys match the sensor `OUTPUT_SENSORS[*]["key"]` values exactly, so a sensor reads `hass.data[DOMAIN][entry.entry_id]["outputs"][self._output_key]` with no intermediate mapping. The master switch's existing attributes (`current_brightness`, `current_color_temp`, `sun_position`) are unchanged — the publish step copies the computed values into the cache under the new key names; the old attributes remain on the switch for backward compatibility (per proposal).

Sensors read from this dict at write-state time. The master switch writes; sensors read. One direction.

**Why:** Three options were on the table:
- **(a) Each sensor recomputes the curve.** Rejected — duplicates the curve math three times per tick; introduces drift risk if computation isn't bit-identical; sensors would need access to all the inputs (sun entities, range numbers, options) which inverts the dependency.
- **(b) Sensors read master-switch attributes via `hass.states.get(<master>).attributes["current_brightness"]`.** Rejected — couples sensor lifecycle to the switch entity's published state, which is async (state lags compute by one event-bus hop), and breaks if the attribute key ever renames.
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
| Sun position | `_sun_position` | `"Sun position"` | `"°"` | `MEASUREMENT` | (none) | `mdi:weather-sunset` |

**Why:**
- `state_class: MEASUREMENT` is the trigger that makes HA's recorder graph the entity as a numeric series and surface it in the History panel + `apexcharts-card` automatically. This is the entire reason the change exists.
- No `device_class`: `SensorDeviceClass.TEMPERATURE` is for thermal sensors (°C/°F), not color temperature; brightness % has no fitting device class in HA's enum; sun-position degrees has no `device_class` enum value (HA has no `ELEVATION` or `ANGLE` class). Setting a device class wrongly forces HA's UI into the wrong unit-conversion behavior and is worse than setting none.
- Units: `"%"`, `"K"`, and `"°"` are all accepted by HA as free-form `native_unit_of_measurement` strings; they render in the UI without unit conversion. Sun position is the solar-elevation angle sourced from the user's configured Sun2 / `sensor.sun_*` entity (range roughly -90 to +90).
- Icons: brightness-percent for brightness pairs visually with the `mdi:brightness-3` / `mdi:brightness-7` already used on the range numbers; thermometer for color temp matches the range-number convention; weather-sunset for sun position is self-explanatory and ties the value to its source.

**Naming rationale (the asymmetric "Output" prefix):**
- `"Output brightness"` — `"Brightness"` collides with the adapt-brightness switch's friendly name ("Dining MVP Brightness") from `add-runtime-range-controls` R7. `"Output"` resolves the collision and parallels the capability name (`output-sensors`).
- `"Output color temp"` — no hard collision (the switch is `"Color"`, not `"Color temp"`), but kept the prefix for parallelism with brightness AND to disambiguate from the existing `"Min color temp"` / `"Max color temp"` number entities on the same device.
- `"Sun position"` — no prefix needed; no other entity on the device uses `"Sun"` in its name. Adding `"Output sun position"` would be inaccurate anyway — sun position is the curve's *input*, not its output.

**Alternatives considered:**
- **`SensorDeviceClass.ILLUMINANCE`** for brightness. Rejected — illuminance is lux (a measured external value), not a target output percentage.
- **No `state_class`** to leave the recorder behavior implicit. Rejected — explicit `MEASUREMENT` is what makes the recorder treat the values as graphable; omitting it defeats the change.
- **Naming as `"Brightness"` / `"Color temp"` / `"Sun"`.** Rejected — collides with `"Brightness"` switch; `"Color temp"` is also ambiguous next to `"Min/Max color temp"` numbers.
- **Naming as `"Current brightness"` / `"Current color temp"` / `"Sun position"`.** Considered (matches existing master-switch attribute keys `current_brightness`, `current_color_temp`). Rejected in favor of `"Output X"` — capability name parallel, and "current" is redundant when HA's More-info dialog already shows a current value.
- **Symmetric `"Output sun position"`.** Rejected — sun position is an input to the curve, not an output; the prefix would be inaccurate.

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
    {"key": "sun_position",      "name": "Sun position",      "unit": "°", "icon": "mdi:weather-sunset"},
]
```

Sensor platform iterates this list. Tests reference it.

**Why:** Same data-driven pattern as the range entities — one source for setup + tests, no per-sensor class proliferation. Three instances of one class (`AdaptiveOutputSensor`) parameterized by the dict entry.

**Alternatives considered:**
- **Three separate sensor classes** (`BrightnessSensor`, `ColorTempSensor`, `SunPositionSensor`). Rejected — each class would be 90% identical; the dict-driven instantiation is shorter and easier to extend.
- **Class hierarchy with a base + three subclasses.** Rejected — overengineering for three uniform sensors with no behavioral divergence.

### Decision 8: No service surface, no options-flow surface

**What we chose:** This change adds no services, no options-flow fields, no new config keys. The integration's `services.yaml`, `config_flow.py`, `strings.json` (apart from the three sensor name keys) are untouched.

**Why:** Sensors are read-only. Nothing to configure. The cadence is governed by the existing `interval` option, which already exists. Adding a "show sun_position" toggle, for example, is dead-code complexity — anyone who doesn't want the entity can hide it via HA's entity registry.

**Alternatives considered:**
- **Option to disable individual sensors.** Rejected — HA's entity registry already allows hiding entities per-user. Don't reinvent.

## Risks / Trade-offs

- **[Master switch and sensor compute paths could diverge in a future refactor]** → Mitigation: the master switch is the only place curve math runs; sensors do not duplicate it. Anyone moving curve math out of the master switch in the future will see the `hass.data[DOMAIN][entry_id]["outputs"]` publish line and the dispatcher signal as the explicit handoff; refactoring without preserving this contract would visibly break the sensors. Test 5.x asserts the contract.
- **[Sensor state stays `unknown` if the master switch's curve loop never runs]** → Possible if the switch fails to set up. Mitigation: that failure mode is already user-visible (the master switch entity itself shows as `unavailable`); the sensors merely echo it. No new debugging surface.
- **[Recorder explosion: 3 sensors × N profiles × MEASUREMENT state_class]** → For a 6-profile household (CDiT's case), that's 18 new sensors writing one row every 90 s = ~17 280 rows/day. Recorder + statistics handle this without strain; the values compress well. Mitigation: `recorder` config's `purge_keep_days` default (10 days) bounds disk usage; no action needed.
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

**Rollback:** revert the PR. The three sensor entities disappear from the entity registry; the master switch attributes (`current_brightness` etc.) remain unchanged because they were never removed. Any History/`apexcharts-card` configs pointing at the new sensors will show "entity not found" until the rollback is reverted again. No data loss.

## Open Questions

None. All eight decisions resolved. The "should sensors be `RestoreSensor`?" question is settled by Decision 5 (no — stale data is misleading; `unknown` for one tick is honest).
