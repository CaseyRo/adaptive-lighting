## Why

The upstream Adaptive Lighting options dialog is a 40-field flat schema that mixes setup-time decisions, runtime-tunable values, and features CDiT does not use — sleep mode, automatic manual-override detection, three interchangeable brightness curve modes, and eight fields of manual sun-time bookkeeping. With no grouping, no conditional visibility, and expert-only field names, the dialog is hard to read and risky to edit; meaningful changes are buried in noise.

This change resets the integration config to what CDiT actually needs: an 18-field, sectioned dialog with conditional visibility, native HA selectors, and entity-driven sun timing that plugs into Sun2 cleanly.

## What Changes

**BREAKING** — existing upstream config entries will not load. `manifest.json` major version is bumped; users (CDiT only — one household) recreate the entry once.

- **Sectioned layout via `section()` helper** — 5 collapsible groups (Targets, Daytime curve, Sun schedule, Light control, Advanced) plus a collapsed Diagnostics subsection. One screen, grouped logically, no multi-step wizard.
- **`OptionsFlowWithReload`** — saving reloads the integration without a full HA restart and without the stale-state bugs of manual reload.
- **Conditional visibility** — fields appear only when their driver is set:
  - `send_split_delay` only when `separate_turn_on_commands` is true.
  - `include_config_in_attributes` lives under a collapsed Diagnostics subsection.
- **Entity-driven sun timing** — two new fields replace eight:
  - `sunrise_entity`: any `sensor` with `device_class: timestamp`. Default `sensor.sun_next_rising`.
  - `sunset_entity`: same. Default `sensor.sun_next_setting`.
  - Users with Sun2 installed can point to civil / nautical / astronomical twilight sensors without code changes.
- **Synthetic tanh brightness curve** — derived from `sunrise_entity` and `sunset_entity` with a hardcoded 30-minute half-width ramp at each end. Curve shape is no longer user-configurable.
- **Native HA selectors throughout** — `EntitySelector` (lights and sun events), `NumberSelector` with explicit ranges (brightness, color temp, durations), `BooleanSelector` (flags). Replaces the upstream `int_between(...)` voluptuous custom validators with introspectable UI primitives.
- **Explicit YAML-managed entry message** — currently the dialog appears editable but silently no-ops for YAML-configured entries. Replace with an `async_abort` and a clear "this entry is managed by YAML; edit `configuration.yaml`" message.
- **Remove 21 fields and 1 entity:**
  - **Sleep cluster (6 fields + 1 entity)**: `sleep_brightness`, `sleep_rgb_or_color_temp`, `sleep_color_temp`, `sleep_rgb_color`, `sleep_transition`, `adapt_until_sleep`. Plus `switch.adaptive_lighting_sleep_mode_<name>` from the switch platform — runtime drops from 4 toggles to 3.
  - **Manual sun timing (8 fields)**: `sunrise_time`, `min_sunrise_time`, `max_sunrise_time`, `sunrise_offset`, and the four sunset counterparts. Replaced by `sunrise_entity` / `sunset_entity`.
  - **Curve shape (3 fields)**: `brightness_mode`, `brightness_mode_time_dark`, `brightness_mode_time_light`. Hardcoded to tanh with 30-min half-width.
  - **Take-over-control cluster (4 fields)**: `take_over_control`, `take_over_control_mode`, `detect_non_ha_changes`, `autoreset_control`. Manual overrides handled at the scene/automation layer; `only_once` and `adapt_only_on_bare_turn_on` removed as anti-AL flags.
- **Kept from upstream override cluster (2 fields)**: `intercept` and `multi_light_intercept` — these are transport behavior (hooking `light.turn_on`), not manual-override semantics.

## Capabilities

### New Capabilities

- `options-flow`: integration setup and reconfiguration UI. Covers section layout, conditional field visibility, entity-driven sun timing, native HA selector usage, reload-on-save semantics, YAML-managed entry messaging, and the surface of fields that exist in the config dialog.

### Modified Capabilities

None. `openspec/specs/` is empty — this is the first capability defined in the fork.

## Impact

- **`custom_components/adaptive_lighting/const.py`** — `VALIDATION_TUPLES` shrinks from 39 to 18 entries; `CONF_*` / `DEFAULT_*` constants for removed fields are deleted; `EXTRA_VALIDATION` shrinks accordingly. New constants for the hardcoded tanh half-width and the two entity-config keys.
- **`custom_components/adaptive_lighting/config_flow.py`** — schema build switches from a flat `vol.Schema({...})` loop over `VALIDATION_TUPLES` to a hand-shaped layout using `section()` and HA selector classes. `OptionsFlowWithReload` replaces `OptionsFlow`. YAML-managed branch replaces the silent no-op with `async_abort(reason="yaml_managed")`.
- **`custom_components/adaptive_lighting/switch.py`** — sleep mode switch entity class and its state machine are removed from the master switch class. Take-over-control state machine and its `autoreset` timer are removed. Two fewer entities per AL config.
- **`custom_components/adaptive_lighting/__init__.py`** — `astral` calls for sun timing are replaced with `hass.states.get(<sunrise_entity>)` reads; tanh curve math moves here as a stable, hardcoded function. Astral remains a transitive dep but is no longer called in the curve path.
- **`custom_components/adaptive_lighting/manifest.json`** — `version` bumped to `2.0.0-cdit.1` (or equivalent CDiT-tagged major) to force config-entry rejection on upgrade.
- **`custom_components/adaptive_lighting/strings.json` + `translations/en.json`** — re-shaped to match new section labels; keys for deleted fields removed; new keys for sun-entity labels, the YAML-managed abort reason, and section titles. Other locales left as upstream — out of scope for this change.
- **`tests/test_config_flow.py`** — substantially rewritten against the new schema. Sleep-mode tests and take-over-control tests are deleted, not migrated. New tests cover: entity selector validation, conditional visibility, tanh curve output at fixed timestamps, YAML-managed abort path, and `OptionsFlowWithReload` behavior.
- **No new runtime dependencies.** `astral` stays in `pyproject.toml` for now (used elsewhere); can be pruned in a follow-up.
- **Future changes unlocked**: `add-runtime-range-controls` (number entities for the 4 brightness/color-temp ranges) and `house-mode-modes` (per-AL behavior matrix driven by an external mode entity) both layer on top of this redesign cleanly.
