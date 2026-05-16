<!--
Annotations:
  R1–R9  = Requirements in specs/options-flow/spec.md
  D1–D15 = Decisions in design.md

Build order: groups 1 and 2 are foundation (run sequentially or in parallel,
no shared file). Groups 3-5 layer on top. Group 6 is the setup-entry guard.
Group 7-9 are tests, translations, and docs (final polish).
-->

## 1. Foundation — `const.py` and `manifest.json`

- [ ] 1.1 Remove the 21 retired `CONF_*` / `DEFAULT_*` constants from `const.py`: `sleep_brightness`, `sleep_rgb_or_color_temp`, `sleep_color_temp`, `sleep_rgb_color`, `sleep_transition`, `adapt_until_sleep`, `sunrise_time`, `min_sunrise_time`, `max_sunrise_time`, `sunrise_offset`, `sunset_time`, `min_sunset_time`, `max_sunset_time`, `sunset_offset`, `brightness_mode`, `brightness_mode_time_dark`, `brightness_mode_time_light`, `take_over_control`, `take_over_control_mode`, `detect_non_ha_changes`, `autoreset_control`, `only_once`, `adapt_only_on_bare_turn_on`. [R8]
- [ ] 1.2 Trim `VALIDATION_TUPLES` to the 16 retained upstream entries plus 2 new sun-entity entries (target: 18 total). Also prune `EXTRA_VALIDATION` of orphaned keys. [R8]
- [ ] 1.3 Add `CONF_SUNRISE_ENTITY = "sunrise_entity"` / `DEFAULT_SUNRISE_ENTITY = "sensor.sun_next_rising"` and the `_SUNSET_` pair. [R3]
- [ ] 1.4 Add `RAMP_HALF_WIDTH_SECONDS = 1800` with an inline comment naming the design choice (30-min eye-friendly transition). [R4, D15]
- [ ] 1.5 Bump `manifest.json` to `version: "2.0.0-cdit.1"`, add `"homeassistant": "2025.1.0"`, update `codeowners` to CDiT-dev maintainers, point `documentation` / `issue_tracker` at the fork URL. [R8, D4, D13]

## 2. Foundation — strip dead code from `switch.py`

- [ ] 2.1 Delete the sleep-mode switch entity class and its `unique_id` pattern from `switch.py`. The integration now creates 3 switches per AL config (master, adapt_brightness, adapt_color), not 4. [D7]
- [ ] 2.2 Remove sleep-mode state machine from the master `AdaptiveSwitch` class (sleep transition logic, sleep brightness override, `adapt_until_sleep` handling). [D7]
- [ ] 2.3 Remove the take-over-control state machine: `_manual_control` tracking, `_autoreset_handle`, `detect_non_ha_changes` polling, `only_once` short-circuits, `adapt_only_on_bare_turn_on` checks. [D8]
- [ ] 2.4 Audit remaining `switch.py` for references to removed `CONF_*` keys and delete dead branches. Lint must pass. [D7, D8]

## 3. Config flow — sectioned schema

- [ ] 3.1 Replace the flat `VALIDATION_TUPLES` loop in `config_flow.py` with a hand-shaped builder that returns a `vol.Schema` containing six `section()`-wrapped subschemas: Targets, Daytime curve, Sun schedule, Light control, Advanced (collapsed), Diagnostics (collapsed). [R1, D1]
- [ ] 3.2 Wire each field's selector per the table in R5: `NumberSelector` (slider mode for brightness 1–100 / step 1 / %; box-or-slider for color temp 1000–10000 / step 100 / K), `BooleanSelector`, `EntitySelector(domain="light", multiple=True)` for `lights`, `EntitySelector(domain="sensor", device_class="timestamp")` for the two sun entities. [R5, D5, D14]
- [ ] 3.3 Implement conditional visibility for `send_split_delay` (driver: `separate_turn_on_commands`). The schema builder reads the current options/draft state and omits `send_split_delay` when the driver is false. [R2, D9]
- [ ] 3.4 Move `include_config_in_attributes` into the Diagnostics collapsed subsection. [R1]
- [ ] 3.5 Verify that no field appears in more than one section (spec R1 scenario 2). [R1]

## 4. Config flow — reload-on-save and YAML-managed abort

- [ ] 4.1 Change `OptionsFlow` → `OptionsFlowWithReload` in `config_flow.py`. Drop any custom `async_reload` / `async_unload_entry` plumbing that exists today for reload purposes. [R6, D6]
- [ ] 4.2 In the options flow's `async_step_init`, detect `config_entry.source == SOURCE_IMPORT` and return `self.async_abort(reason="yaml_managed")`. [R7]
- [ ] 4.3 Confirm via manual test that toggling a field and saving reloads the integration with no "restart HA" prompt, and that entity IDs of the AL switches are preserved across the reload. [R6]

## 5. Curve math — entity reads + synthetic tanh

- [ ] 5.1 Add a `today_sun_events(hass, entry)` helper in `__init__.py` (or a new `sun.py` module) that reads `entry.options[CONF_SUNRISE_ENTITY]` and `_SUNSET_ENTITY`, fetches their state via `hass.states.get(...)`, parses the timestamp, and handles the "next_rising flipped to tomorrow after sunrise" case by anchoring today's curve from whichever event is in the past. Returns `(today_sunrise_dt, today_sunset_dt)`. [R3, D2]
- [ ] 5.2 Add a pure `tanh_curve(now, t_start, t_end, value_min, value_max, half_width=RAMP_HALF_WIDTH_SECONDS)` function. Returns `value_min` outside the active window, ramps via `tanh` between (`t_start - half_width`, `t_start + half_width`), holds at `value_max` between (`t_start + half_width`, `t_end - half_width`), ramps back via `tanh` between (`t_end - half_width`, `t_end + half_width`). [R4, D11]
- [ ] 5.3 Replace upstream's `astral`-driven brightness and color-temp computation with two calls to `tanh_curve` — one for brightness using `min_brightness` / `max_brightness`, one for color temp using `min_color_temp` / `max_color_temp`. Same `(t_sunrise, t_sunset)` inputs for both. [R4]
- [ ] 5.4 Verify the curve evaluation path no longer imports `astral.sun`. (`astral` may remain a transitive dep for now; pruning it is a follow-up.) [D2]

## 6. `async_setup_entry` guards

- [ ] 6.1 At the top of `async_setup_entry` in `__init__.py`, check `config_entry.version` against the current major (2). If older, raise `ConfigEntryError` with a user-facing message: "Adaptive Lighting v2 (CDiT fork) is incompatible with the existing config entry. Delete and recreate the entry from Settings → Devices & Services." [R8, D4]
- [ ] 6.2 Add a sleep-switch tombstone helper: scan `entity_registry` for entities whose `unique_id` matches the historical `<entry.entry_id>_sleep_mode_*` pattern, call `entity_registry.async_remove(entity_id)` on each match, log `INFO` per removal with the entity ID. [R9, D12]
- [ ] 6.3 Ensure the tombstone helper is idempotent — a second `async_setup_entry` call finds nothing and emits no log lines. [R9]
- [ ] 6.4 Confirm the helper only removes entities whose `config_entry_id` matches the current entry (does not touch foreign entities matching the name pattern). [R9, D12]

## 7. Tests

- [ ] 7.1 Delete obsolete test files: `tests/test_*sleep*`, `tests/test_*take_over*`, `tests/test_*manual_control*`. Update `tests/conftest.py` to drop fixtures that referenced those features. [D7, D8]
- [ ] 7.2 Add test: section layout — opening options on a UI-managed entry returns a flow result with six labeled sections in the specified order; Advanced and Diagnostics collapsed. [R1]
- [ ] 7.3 Add test: each field appears in exactly one section, matching the R1 table. [R1]
- [ ] 7.4 Add test: `send_split_delay` is absent from the schema when `separate_turn_on_commands` is false; present when true. [R2]
- [ ] 7.5 Add test: `sunrise_entity` / `sunset_entity` default to `sensor.sun_next_rising` / `sensor.sun_next_setting` on a freshly created entry. [R3]
- [ ] 7.6 Add test: entity selectors for the two sun fields are configured with `domain="sensor"` and `device_class="timestamp"`. [R3, D14]
- [ ] 7.7 Add test: `tanh_curve` returns `value_min` more than `half_width` before `t_start`, midpoint at exactly `t_start`, `value_max` more than `half_width` after `t_start` (and the symmetric trio around `t_end`). [R4]
- [ ] 7.8 Add test: color temperature uses the same curve shape as brightness, with `min_color_temp` / `max_color_temp` as bounds. [R4]
- [ ] 7.9 Add test: `NumberSelector` types, ranges, units, and modes match the R5 table for brightness, color temp, durations, and milliseconds. [R5]
- [ ] 7.10 Add test: saving valid options invokes `async_unload_entry` and `async_setup_entry` exactly once each (use mock spies) and produces no "restart HA" prompt. [R6]
- [ ] 7.11 Add test: opening the options flow on a `SOURCE_IMPORT` config entry returns `async_abort(reason="yaml_managed")`. [R7]
- [ ] 7.12 Add test: `async_setup_entry` raises `ConfigEntryError` when `config_entry.version == 1` and current is 2. [R8]
- [ ] 7.13 Add test: `async_setup_entry` succeeds and runs no tombstone log line when entry version is current. [R8]
- [ ] 7.14 Add test: the tombstone helper removes a seeded `switch.adaptive_lighting_sleep_mode_<name>` entity owned by this config entry, emits one INFO log line. [R9, D12]
- [ ] 7.15 Add test: tombstone helper is idempotent — second run finds nothing, no log line. [R9]
- [ ] 7.16 Add test: tombstone helper does not remove a foreign-owned entity matching the name pattern (different `config_entry_id`). [R9, D12]

## 8. Strings and translations

- [ ] 8.1 In `strings.json`, add section labels (`section.targets.name`, `section.daytime_curve.name`, etc.) and short descriptions per section. Add field labels for `sunrise_entity` / `sunset_entity`. [R1, R3]
- [ ] 8.2 In `strings.json`, add the `yaml_managed` abort reason text: "This Adaptive Lighting config entry is managed from `configuration.yaml`. Edit it there to change options." [R7]
- [ ] 8.3 In `strings.json`, add the version-incompatible error: "This entry was created with an older, incompatible version. Delete it and create a new one." [R8]
- [ ] 8.4 Remove `strings.json` keys for the 21 deleted fields and the sleep switch entity. [R1, D7]
- [ ] 8.5 Mirror the additions/removals in `translations/en.json`. Other locales (de, fr, etc.) are out of scope and may diverge until a follow-up change. [R1]

## 9. Docs — README and CHANGELOG

- [ ] 9.1 Replace the upstream README's "Installation" / "Configuration" sections (or add a CDiT-specific preamble at the top) explicitly stating: "This is a CDiT fork. Existing upstream config entries WILL NOT load; recreate them after upgrade." Reference the migration steps from design.md §Migration Plan. [D4]
- [ ] 9.2 Add a "Recommended companions" section to README mentioning Sun2 as a HACS-installable source for precise civil / nautical / astronomical twilight sensors. Show the example of pointing `sunrise_entity` at `sensor.sun2_astro_dawn`. [D2, D14]
- [ ] 9.3 Write `CHANGELOG.md` (or append to existing) entry for `2.0.0-cdit.1`: the 21 removed fields by name, the 2 added fields, the 1 removed entity, the breaking config-entry behavior, and the explicit recreate workflow. [D4]
- [ ] 9.4 Update the fork's GitHub repo description and topics to mark it as opinionated/fork (not a drop-in replacement). [D4]
