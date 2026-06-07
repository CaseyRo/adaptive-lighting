# add-runtime-ramp-width

## Why

The curve's ramp half-width is hardcoded at 30 minutes (`RAMP_HALF_WIDTH_SECONDS = 1800`, design decision 3 of `cdit-config-redesign`). The 2026-06-07 seasonality exploration concluded that seasonal adaptation (slower summer dusks, brisker winter transitions) belongs in Node-RED via runtime entities — and ramp width is the one curve parameter Node-RED cannot reach today. Exposing it as a fifth runtime number completes the orchestration surface without adding any seasonal logic to the integration.

## What Changes

- **Each AL profile gains a fifth `number` entity**: ramp half-width, in minutes (default 30, bounds 5–120, step 1, slider). One value drives **both** the sunrise and sunset ramps — no per-event asymmetry (summer-morning ramps happen while the household sleeps; there is no customer for a split).
- **No new options-flow field.** Decision 3's "no knob in the config dialog" stands; the knob exists only as an entity, intended to be driven seasonally from Node-RED (or tuned ad hoc from a dashboard). Fallback when the entity is unavailable is the `RAMP_HALF_WIDTH_SECONDS` constant — not `entry.options`, because no option exists.
- **Curve evaluation reads the live value per tick**, converted minutes → seconds, through the same registry-lookup mechanism as the four range entities.
- **Day-anchoring stays consistent with the curve**: `anchor_sun_events()` (the post-sunset ramp-tail window) receives the same live half-width instead of the constant, so a widened evening ramp still completes after the sun sensors flip to tomorrow.

## Capabilities

### New Capabilities

_None — this extends an existing capability._

### Modified Capabilities

- `runtime-range-controls`: the "exactly four runtime range entities" requirement becomes five; the new entity has constant-fallback semantics (no `entry.options` mirror) and is exempt from the options-flow seeding/propagation requirements that apply to the four range fields.
- `options-flow`: requirement R4's "hardcoded half-width of 30 minutes (`RAMP_HALF_WIDTH_SECONDS = 1800`)" becomes "runtime half-width from the profile's ramp-width entity, defaulting to 30 minutes".

## Impact

- **`custom_components/adaptive_lighting/number.py`** — fifth entity class/descriptor; minutes unit; restore semantics identical to the existing four minus the options seeding.
- **`custom_components/adaptive_lighting/const.py`** — `CONF_RAMP_HALF_WIDTH`-style field key + default; `RAMP_HALF_WIDTH_SECONDS` retained as the fallback default.
- **`custom_components/adaptive_lighting/switch.py`** — `sun_light_settings` rebuild reads the live half-width (minutes → seconds); `_today_sun_events` passes the same live value to `anchor_sun_events`.
- **`tests/test_number_platform.py`** — entity creation/bounds/restore for the fifth entity; constant fallback when unavailable.
- **`tests/test_color_and_brightness.py`** — unaffected (pure math already parameterized by `half_width`).
- **No manifest-breaking change** — additive entity, existing config entries load unchanged. Patch-level version bump.
- **No new dependencies.**

**Sequencing**: builds directly on the implemented `runtime-range-controls` capability; no other active changes exist.
