# add-runtime-ramp-width — tasks

Annotation legend — requirements in this change's spec deltas, decisions in `design.md`:
- **R1** runtime-range-controls / "Each AL profile exposes five runtime curve entities" (MODIFIED)
- **R2** runtime-range-controls / "Ramp half-width entity drives the curve transition width" (ADDED)
- **R3** options-flow / "Brightness and color temperature follow a synthetic tanh curve" (MODIFIED)
- **D1–D6** design decisions 1–6

## 1. Constants

- [x] 1.1 Add the ramp half-width field key constant (e.g. `CONF_RAMP_HALF_WIDTH = "ramp_half_width"`) and `DEFAULT_RAMP_HALF_WIDTH_MIN = 30` to `const.py`; keep `RAMP_HALF_WIDTH_SECONDS = 1800` as the curve-path fallback. Do NOT add the field to `VALIDATION_TUPLES` (no options-flow surface). [R2, D2]

## 2. Number platform

- [x] 2.1 Add the fifth entity to `number.py` following the existing descriptor/class pattern: unique_id `<entry_id>_ramp_half_width`, `native_min_value=5`, `native_max_value=120`, `native_step=1`, `native_unit_of_measurement="min"`, `mode=SLIDER`, same device record as the switches. [R1, D3]
- [x] 2.2 Naming: `_attr_has_entity_name = True`, `_attr_name = "Ramp half-width"`, `suggested_object_id = "ramp_half_width"`; entity description notes total transition = 2× the value. [R1, D6]
- [x] 2.3 Restore semantics: `RestoreNumber`; on `async_added_to_hass` prefer restored value, else default 30. No `entry.options` tier, no write-back, no reload on change. Exclude this entity from any options-seeding code paths that iterate the four range fields. [R2, D2]

## 3. Curve read path

- [x] 3.1 Add `_get_runtime_ramp_width_seconds()` to `AdaptiveSwitch` in `switch.py`: entity-registry lookup by unique_id, state cast via `int(float(state)) * 60`, fallback to `RAMP_HALF_WIDTH_SECONDS` with a `DEBUG` log naming the missing entity. Dedicated helper — do not generalize `_get_runtime_range`. [R2, D4]
- [x] 3.2 Wire `sun_light_settings` (per-tick rebuild) to feed the live value into `SunLightSettings.ramp_half_width_seconds`. No changes to `color_and_brightness.py` (already parameterized). [R3, D4]
- [x] 3.3 Read the width once per evaluation and pass that same value to both the curve settings and `anchor_sun_events(..., half_width=...)` in `_today_sun_events` (replacing the `RAMP_HALF_WIDTH_SECONDS` constant there). [R2, D5]

## 4. Tests

- [x] 4.1 `test_number_platform.py`: new entry creates five number entities; fifth has minute bounds (5/120/1/"min"/SLIDER), correct unique_id suffix, and shares the switches' device. [R1]
- [x] 4.2 `test_number_platform.py`: fifth entity defaults to 30 on first creation; restored value wins after a simulated restart (mirror the existing restore tests). [R2]
- [x] 4.3 `test_number_platform.py` (or switch-level test): with the entity set to 60, the next curve evaluation uses 3600 s half-width; with the entity unavailable, evaluation falls back to 1800 s and logs at DEBUG; slider change does not reload the entry. [R2, R3]
- [x] 4.4 Regression test for anchor consistency: width 60, both `next_*` sensors flipped to tomorrow, evaluation 45 min after today's sunset → pair anchors to today and brightness is strictly between min and max (uses `anchor_sun_events` with the live width). [R2, D5]
- [x] 4.5 Full suite green: `uv run pytest` (all existing tests must pass unmodified — default behavior is unchanged at width 30). [R1–R3]

## 5. Release

- [x] 5.1 `./scripts/lint` clean. [—]
- [x] 5.2 Bump `manifest.json` to `2.5.0-cdit.1` (additive entity surface → minor). [D2]
- [x] 5.3 Note the new entity + NR-seasonality intent in `README.md`'s fork-features section (one short paragraph). [D2]
