<!--
Annotations:
  R1–R7   = ADDED Requirements in specs/runtime-range-controls/spec.md
            R7 = "All AL entities use has_entity_name composition"
  MR4     = MODIFIED Requirement in specs/options-flow/spec.md (curve reads bounds from entities)
  D1–D11  = Decisions in design.md (D11 = entity-naming hygiene)
  polish  = Quality/UX tasks captured during design review, not spec-driven

Build order: group 1 is platform foundation. Group 2 implements the entity class. Groups 3-5 wire reads, writes, and seeding. Group 6 retrofits has_entity_name on existing switches. Group 7 is tests, group 8 docs.
-->

## 1. Platform foundation — `number.py` skeleton and `const.py` constants

- [x] 1.1 Add `Platform.NUMBER` to the `PLATFORMS` list in `__init__.py` so HA forwards `async_setup_entry` to the new platform. [R1]
- [x] 1.2 In `const.py`, add a mapping `RANGE_ENTITIES` (or four explicit constants) covering the four entities: `unique_id` suffix, friendly-name slug, `native_min`, `native_max`, `step`, `unit`, `icon`. One source for both platform setup and tests. [R1, D5, D6]
- [x] 1.3 Create `custom_components/adaptive_lighting/number.py` with an `async_setup_entry(hass, config_entry, async_add_entities)` that instantiates four entities (one per row in `RANGE_ENTITIES`) and calls `async_add_entities(entities)`. [R1]
- [x] 1.4 Update the existing `device_info` block (or shared helper) so the new entities attach to the same `(DOMAIN, entry.entry_id)` device as the three switches. [R1]

## 2. Entity class — `RestoreNumber` subclass with seed logic

- [x] 2.1 Define `AdaptiveRangeNumber(RestoreNumber)` in `number.py` with `_attr_has_entity_name = True`, `_attr_mode = NumberMode.SLIDER`, and `_attr_should_poll = False`. Constructor takes `(entry, field_key, native_min, native_max, step, unit, icon)`. [R1, R7, D6, D11]
- [x] 2.2 Implement `unique_id` property as `f"{entry.entry_id}_{field_key}"`. [R1, D5]
- [x] 2.3 Set `_attr_name` on each instance to the role label per the D11 table: "Min brightness", "Max brightness", "Min color temp", "Max color temp". The device's name carries the profile context — HA composes the full friendly name automatically. [R7, D11]
- [x] 2.4 Implement `async_added_to_hass` with the three-tier seed precedence: (a) prefer `entry.options[CONF_*]` if its value is newer than the restored state (compare via `RestoreNumber.async_get_last_number_data().native_value` against options), (b) restored state, (c) `entry.options[CONF_*]` as the first-creation fallback. [R2, D2, D3]
- [x] 2.5 Implement `async_set_native_value(value)` to set `_attr_native_value`, call `async_write_ha_state()`, and return. The method SHALL NOT call `hass.config_entries.async_update_entry` (no write-through to options). [R4, D1, D2]

## 3. Curve math — read bounds from entities, fallback to options

- [x] 3.1 Add a helper `_get_runtime_range(hass, entry, field_key)` (in `switch.py` or a shared helper module) that does `state = hass.states.get(f"number.adaptive_lighting_{slugify(entry.title)}_{field_key}")` → returns `int(state.state)` if state is set and not unavailable, else `int(entry.options[CONF_*])`, logging the fallback at DEBUG. [R3, D8, D9]
- [x] 3.2 In `AdaptiveSwitch._get_settings()` (or wherever `SunLightSettings` is constructed), replace the four `entry.options[CONF_*]` reads for `min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp` with calls to `_get_runtime_range(...)`. [R3, MR4, D1, D8]
- [x] 3.3 Verify no other reads of these four CONF keys remain in the curve evaluation path (`brightness_pct`, `color_temp_kelvin`, `brightness_and_color`, `sun_position`). Other reads (e.g., the options-flow schema seeding) are intentionally untouched here. [R3, MR4]

## 4. Options flow — seed the 4 range fields from entity state

- [x] 4.1 Modify `_build_options_schema(current, ...)` in `config_flow.py` to accept the four range entity states (or read them inline via `hass.states.get(...)`). When an entity state is available, use it as the field default; otherwise fall back to the matching `entry.options[CONF_*]` value. [R6, D4]
- [x] 4.2 In `async_step_init`, compute the four `current_*` values once (using the helper from 4.1), then pass them into the schema builder. [R6, D4]
- [x] 4.3 Confirm the other ~14 fields still seed from `entry.options` unchanged. [R6]

## 5. Wire-up — `async_setup_entry` sequencing

- [x] 5.1 Confirm the order `async_setup_entry` calls `async_forward_entry_setups(entry, PLATFORMS)` is unchanged — both `switch` and `number` platforms set up in parallel. [R1]
- [x] 5.2 Verify the entity-unavailable fallback (Decision 9) actually fires during the brief race window where the switch starts evaluating before the number platform has registered all four entities. This is the natural state during a fresh `async_setup_entry`; the curve math should not crash. [R3, D9]

## 6. Entity-naming hygiene — retrofit the three existing switches

- [x] 6.1 In `switch.py`, set `_attr_has_entity_name = True` on `AdaptiveSwitch`, `AdaptColorSwitch`, and `AdaptBrightnessSwitch`. [R7, D11]
- [x] 6.2 Set `_attr_name` per the D11 table: `AdaptiveSwitch._attr_name = None` (master takes device name), `AdaptBrightnessSwitch._attr_name = "Brightness"`, `AdaptColorSwitch._attr_name = "Color"`. Delete any code that hand-composes "Adaptive Lighting …" into the friendly name. [R7, D11]
- [x] 6.3 Confirm the shared `device_info` block sets `name = entry.title` (or `entry.data[CONF_NAME]`, whichever is the user-facing string). This is the anchor for the composed friendly names. [R7, D11]
- [x] 6.4 Verify `unique_id`s are NOT changed by this group — only `_attr_name` and `_attr_has_entity_name`. The entity registry must keep existing entity_ids stable. [R7, D11]
- [x] 6.5 Manual check on live HA after deploy: pre-existing entity_ids unchanged (no duplicates, no broken automations), friendly names now read as "Dining MVP Brightness" / "Dining MVP Color" instead of "Adaptive Lighting Adapt Brightness dining_mvp_lights". [R7, D11]

## 7. Tests — `tests/test_number_platform.py`

- [x] 7.1 New test file `tests/test_number_platform.py` with autouse PHACC fixture from `conftest.py`. [R1]
- [x] 7.2 Add test: creating a new config entry registers exactly four `number` entities owned by the entry. Assert the suffixes are `_min_brightness`, `_max_brightness`, `_min_color_temp`, `_max_color_temp`. [R1]
- [x] 7.3 Add test: each of the four entities is attached to the same device as the profile's switches. [R1]
- [x] 7.4 Add test: brightness entities expose `native_min_value=1`, `native_max_value=100`, `native_step=1`, `native_unit_of_measurement="%"`, `mode=NumberMode.SLIDER`. Color-temp entities expose `1000`/`10000`/`100`/`"K"`/`SLIDER`. [R1, D6]
- [x] 7.5 Add test: `async_set_native_value` updates `state` but does not call `hass.config_entries.async_update_entry` (use a mock spy). [R4, D2]
- [x] 7.6 Add test: slider change does not invoke `async_unload_entry` / `async_setup_entry`. [R4]
- [x] 7.7 Add test: simulating an HA restart — pre-seed `RestoreNumber` state to 30 for `min_brightness`, set up the entry, assert entity state is 30 (not the default 5 from `entry.options`). [R2]
- [x] 7.8 Add test: options-flow save with new range values triggers a reload, and after the reload the entity state reflects the just-saved values (not the previously-restored values). [R5, D3]
- [x] 7.9 Add test: opening the options flow seeds the four range fields from `hass.states.get(<entity_id>).state`, not from `entry.options`. Set the entity to 80, leave options at 100, assert the flow's schema default is 80. [R6, D4]
- [x] 7.10 Add test: opening the options flow when an entity is unavailable falls back to `entry.options[CONF_*]`. [R6, D9]
- [x] 7.11 Add test: curve math reads runtime values — set `number.adaptive_lighting_<name>_max_brightness` to 70, set `entry.options[CONF_MAX_BRIGHTNESS]` to 100, run a curve evaluation at "peak day," assert the returned brightness is 70. [R3, MR4]
- [x] 7.12 Add test: curve math fallback — make the entity `unavailable`, set `entry.options[CONF_MAX_BRIGHTNESS]` to 90, evaluate at peak day, assert brightness is 90 and a DEBUG log line names the missing entity. [R3, D9]

## 8. Translations and docs

- [x] 8.1 Add `entity.number.min_brightness.name`, `_max_brightness`, `_min_color_temp`, `_max_color_temp` keys to `strings.json` with plain-language labels ("Min brightness," "Max brightness," etc.). [R1, polish]
- [x] 8.2 Mirror the additions in `translations/en.json`. Other locales out of scope (covered by `complete-i18n-translations` follow-up). [R1, polish]
- [x] 8.3 Add an `entity.number.<key>.unit_of_measurement` mapping if HA's frontend requires it for slider display (verify against current HA — likely auto-derived from `native_unit_of_measurement`). [R1]
- [x] 8.4 Add a short section to `README.md` under "What's new in 2.1" naming the four entities, explaining the slider-vs-options-flow split ("sliders tune live; options-flow sets defaults; saving the dialog resets the sliders to the saved values"), and showing a one-line Lovelace YAML snippet (`type: entities` with the four range entities). [R5, R6, D3, polish]
- [x] 8.5 Append a `2.1.0-cdit.1` entry to `CHANGELOG.md` listing: 4 new entities per profile, RestoreNumber persistence, curve math now reads from entities, options-flow open seeds from entities, no reload on slider change. [polish]

## 9. Manual verification on live HA

- [x] 9.1 Deploy to `homeassistant.onca-blenny.ts.net` via HACS. Verify the four `number.adaptive_lighting_*` entities appear under each of the 6 profiles' devices. [R1]
- [x] 9.2 Move a slider on one profile via the dashboard. Verify (a) no integration reload occurs (check Integration page → no "reloading" banner; entity IDs unchanged), (b) the next curve tick uses the new value (watch the master switch's `brightness_pct` attribute over ~90 s). [R3, R4]
- [x] 9.3 Open the options flow on the same profile. Verify the four range fields show the just-moved slider values, not the original setup defaults. [R6]
- [x] 9.4 Save the options flow with different values. Verify the sliders snap to the new values after reload. [R5, D3]
- [x] 9.5 Restart HA. Verify the slider values persist (RestoreNumber works). [R2]

## 10. Validation gate

- [x] 10.1 `openspec validate add-runtime-range-controls --strict` returns green. [polish]
- [x] 10.2 `uv run pytest tests/test_number_platform.py` passes. Existing tests stay green (`uv run pytest`). [polish]
- [x] 10.3 `./scripts/lint` clean. [polish]
