## Context

The CDiT Adaptive Lighting fork computes brightness from a tanh sun-curve (`color_and_brightness.py`) and dispatches it to lights every `interval` seconds via the adapt loop in `switch.py`. The curve is purely time-based — it has no awareness of ambient light conditions. This design adds an optional lux-feedback gate that can only *reduce* brightness when a room is already bright enough from daylight. The gate sits between the curve output and the service-data assembly, touching a narrow slice of the adapt path.

Existing infrastructure this builds on:
- **`OUTPUT_SENSORS`** in `const.py` — declarative list driving `sensor.py` entity creation. Adding entries here is the established pattern (see `add-output-sensors`).
- **Sectioned options flow** in `config_flow.py` — collapsed sections, conditional field visibility (`send_split_delay` pattern), `EntitySelectorConfig` with `device_class` filtering.
- **`VALIDATION_TUPLES`** in `const.py` — single source for field validation and YAML schema.
- **Dispatcher signal** `SIGNAL_OUTPUTS_UPDATED` — already wakes output sensors on each curve tick.

## Goals / Non-Goals

**Goals:**
- Reduce energy waste when daylight already meets or exceeds the user's comfort threshold.
- Keep configuration minimal: two fields (`lux_sensor`, `target_lux`), no new concepts.
- Self-stabilising — no oscillation, no feedback spiral, no tuning required.
- Zero-impact on profiles without a lux sensor configured.
- Show the user their current lux reading in the config flow so they can set a sensible target.
- Turn lights off entirely when their contribution would be negligible.

**Non-Goals:**
- Full closed-loop illuminance control (boosting lights when room is too dark). The curve already handles that adequately; adding a boost path introduces the feedback spiral.
- Per-light lux sensors. One sensor per AL profile is sufficient — rooms typically have one ambient-light characteristic.
- Adjusting color temperature based on lux. Color temp is circadian, not energy-related.
- Hysteresis or PID control. The `1/ratio` reduction is inherently smooth and self-stabilising; adding control-theory complexity is not warranted for the problem size.

## Decisions

### D1: Reduce-only gate, never boost

**Choice**: The lux gate can only multiply brightness by a factor in `(0, 1]`. When `current_lux ≤ target_lux`, the factor is 1.0 (pass-through).

**Rejected alternative**: Bidirectional offset (boost when too dark, reduce when too bright). This creates positive feedback — lights turn on, lux rises, integration reduces, lux drops, integration boosts. The reduce-only design avoids this entirely because reducing brightness can only lower lux, which relaxes the gate. Self-stabilising by construction.

### D2: Reduction function is `target_lux / current_lux`

**Choice**: `factor = target_lux / current_lux` when `current_lux > target_lux`, else `1.0`.

Properties:
- At `current = 2 × target`, factor = 0.50 (halve brightness).
- At `current = 10 × target`, factor = 0.10 (10% brightness).
- Monotonically decreasing, smooth, no discontinuities.
- Physically intuitive: if you have twice the light you need, halving the artificial contribution is the right response.

**Rejected alternatives**:
- `1 / (1 + ln(ratio))` — gentler curve, but less energy-efficient and harder to reason about.
- `1 / ratio²` — too aggressive; at 1.5× overshoot the lights are already at 44%.
- Linear ramp with cutoff — discontinuity at the cutoff threshold.

### D3: Auto-off below `min_brightness`

**Choice**: When `curve_brightness × factor < min_brightness`, send `light.turn_off` instead of `light.turn_on` with a tiny brightness value. When lux drops back below target on the next interval tick, the normal adapt cycle turns lights back on.

**Rationale**: `min_brightness` already expresses "the lowest I ever want my lights." If daylight is so abundant that the artificial contribution would be below that floor, the lights are contributing effectively nothing — turning off is the logical conclusion and saves the most energy.

**No new setting needed**: reuses `min_brightness` as the threshold.

### D4: Two config fields, one new section

**Choice**:
- `lux_sensor`: `EntitySelector(domain="sensor", device_class="illuminance")`. Optional, default `""` (empty string = feature disabled).
- `target_lux`: `NumberSelector(min=1, max=10000, step=10, unit="lx", mode=BOX)`. Only shown when `lux_sensor` is populated (same conditional pattern as `send_split_delay` / `separate_turn_on_commands`).

Both live in a new "Ambient lux" section, collapsed by default. The section description uses `description_placeholders` to show the sensor's current reading when configured: `"Your sensor currently reads: {current_lux}"`.

**Rejected alternative**: putting lux fields in the existing "Daytime curve" section. These are conceptually separate — the curve sets intent, the lux gate adjusts for reality. A dedicated section with its own description keeps the mental model clean.

### D5: Live lux reading in config flow via `description_placeholders`

**Choice**: In `OptionsFlowHandler.async_step_init`, before calling `async_show_form`, read the configured lux sensor's state and pass it into `description_placeholders`:

```python
lux_reading = "—"
sensor_id = current.get(CONF_LUX_SENSOR)
if sensor_id:
    state = self.hass.states.get(sensor_id)
    if state and state.state not in ("unavailable", "unknown"):
        lux_reading = f"{state.state} lx"
```

Section description in `strings.json`: `"Save energy when daylight is bright enough. Your sensor currently reads: {current_lux}."` — where `{current_lux}` is filled by the placeholder. When no sensor is configured, the placeholder shows "—".

**Limitation**: On the very first configuration (sensor not yet saved), the reading won't appear until the user saves and reopens options. Acceptable — it's a one-time thing.

### D6: `lux_reduce` as a pure function in `color_and_brightness.py`

**Choice**: Add a single pure function:

```python
def lux_reduce(
    curve_brightness: float,
    target_lux: int,
    current_lux: float,
    min_brightness: int,
) -> float | None:
    """Apply reduce-only lux gate to curve brightness.

    Returns adjusted brightness, or None if lights should turn off.
    """
    if current_lux <= target_lux:
        return curve_brightness
    adjusted = curve_brightness * (target_lux / current_lux)
    if adjusted < min_brightness:
        return None
    return adjusted
```

Lives in `color_and_brightness.py` alongside the existing curve math. No class, no state — just a function that takes numbers and returns a number. Easy to unit-test in isolation.

**Rejected alternative**: method on `SunLightSettings`. That dataclass is intentionally HA-free (no sensor access). The lux reduction depends on live sensor state, so it belongs in the call chain between curve output and service-data assembly, not inside the curve math itself.

### D7: Two new output sensors: `ambient_lux` and `lux_reduction`

**Choice**: Add two entries to `OUTPUT_SENSORS` in `const.py`:

| key | name | unit | icon |
|---|---|---|---|
| `ambient_lux` | Ambient lux | lx | `mdi:brightness-5` |
| `lux_reduction` | Lux reduction | % | `mdi:chart-line-variant` |

`ambient_lux` is a pass-through of the configured sensor's reading — value is in `outputs["ambient_lux"]`, updated each tick. `lux_reduction` is `factor × 100` (100 = no reduction, 50 = halved).

Both show `unavailable` when no `lux_sensor` is configured (the existing sensor platform already handles `None` values as `unavailable`).

**Rationale for `ambient_lux`**: mirrors the lux reading into the AL profile's entity set so a single dashboard card tells the full story — curve output, ambient conditions, and the reduction factor — without the user correlating separate entities.

### D8: Sensor state subscription for responsive adaptation

**Choice**: In `switch.py`, when `lux_sensor` is configured, register an `async_track_state_change_event` listener on the lux sensor entity. On state change, trigger `_update_attrs_and_maybe_adapt_lights` (the same path the interval timer uses). This makes the reduction responsive to rapid lux changes (cloud passing, blinds opening) rather than waiting up to `interval` seconds.

**Guard against churn**: only trigger re-adaptation if the lux change crosses the target threshold (was below, now above — or vice versa), OR if the change in lux would alter the reduction factor by more than 5 percentage points. This prevents thrashing on noisy sensors.

**Teardown**: the listener is removed in `async_will_remove_from_hass`, same pattern as the existing interval timer removal.

### D9: Turn-off and turn-back-on behaviour

**Choice**: When `lux_reduce` returns `None` (below `min_brightness`):
- If the light is currently on, send `light.turn_off` with the profile's `transition` time for a graceful fade.
- Set an internal flag `_lux_turned_off` per light entity.
- On subsequent ticks, if `lux_reduce` returns a non-`None` value and `_lux_turned_off` is set, send `light.turn_on` with the adjusted brightness and `initial_transition`.
- Clear the flag.

This ensures the integration only turns lights back on that *it* turned off due to lux — not lights the user manually turned off. The flag is reset on HA restart (lights default to curve behaviour, which is correct).

**Rejected alternative**: relying on the existing `intercept` mechanism to handle turn-on. Intercept fires on user-initiated `turn_on` calls, not integration-initiated ones. The flag approach is explicit and doesn't tangle with intercept logic.

## Risks / Trade-offs

**[Noisy sensors]** → Cheap lux sensors can fluctuate ±50 lx between reads. The 5%-factor guard in D8 mitigates this. If still problematic, users can add a template sensor with a moving average — but that's external to AL, keeping the integration simple.

**[Sensor lag]** → Some sensors report every 30–60 seconds. The interval timer still fires independently, so the worst case is one interval tick with stale lux data — the next tick corrects. Not a problem in practice.

**[User turns off lights manually, lux drops, integration turns them back on]** → The existing `intercept` and context-tracking logic in `switch.py` already handles this: manually-turned-off lights are excluded from adaptation until the user turns them on again. The lux gate doesn't change this — `_lux_turned_off` is a separate flag only for lux-initiated turn-offs.

**[Breaking change risk]** → None. Both fields are optional with empty/zero defaults. Existing config entries are unaffected. Minor version bump only.

## Open Questions

1. **Suggested default for `target_lux`**: 500 lx (typical office/living room comfort level per EN 12464-1) or 0 (disabled)? Leaning toward 0 (disabled) since the feature requires a sensor to be meaningful — a non-zero default without a sensor configured would be confusing.
2. **Should `lux_reduce` round to the nearest 5% to reduce command churn?** The existing `skip_redundant_commands` logic may already cover this, but worth verifying during implementation.
