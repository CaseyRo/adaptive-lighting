## Why

A CDiT house already organizes itself around a "house mode" (`input_select.house_mode` or similar) with values like `morning`, `day`, `evening`, `night`, `away`, `guest`. Adaptive Lighting today is mode-blind: enabling AL only during `morning` / `day` / `evening` while disabling adaptation during `away` and forcing fixed brightness in `guest` requires N HA automations per AL × M modes, with no single place to read the truth.

This change makes the house mode binding native to each AL config: pick the house mode source entity once, fill in a per-mode behavior matrix, and the integration drives its three runtime switches (`master`, `adapt_color`, `adapt_brightness`) on every `state_changed` event from the source entity.

> **Status**: stub proposal. Specs, design, and tasks to be written when work on this change starts. Depends on `cdit-config-redesign` landing first; can land in parallel with `add-runtime-range-controls`.

## What Changes

- **New "House mode" section in the options flow** (added to the layout established by `cdit-config-redesign`). Lives between "Sun schedule" and "Light control". Collapsed by default if no source entity is configured, expanded once one is selected.
- **New field `house_mode_entity`** — entity selector. Accepts any entity (`input_select`, `sensor`, `input_text`) — strict typing isn't appropriate because users build mode entities from many sources.
- **Per-mode behavior matrix** — dynamically rendered once a source entity is selected. For each mode value (auto-discovered from `input_select.options` when available; manually enumerable for other entity types), three booleans: `active`, `adapt_color`, `adapt_brightness`.
- **State listener** — integration subscribes to `state_changed` events for the configured `house_mode_entity`. On change, looks up the new state value in the matrix and asserts the three runtime switches accordingly.
- **Strict semantics** (TBD in design): every mode change re-asserts the table; manual user overrides between mode transitions are not preserved across the next transition. Alternative "sticky" semantics deferred until design.
- **Graceful degradation**:
  - Source entity unavailable → no switch changes, log a warning once.
  - State value not in the matrix → log an info entry, leave switches untouched.
  - Matrix is empty (no `house_mode_entity` configured) → integration behaves as if this feature does not exist.
- **No new runtime control entities** — this change operates only on the existing three switches created per AL config.

## Capabilities

### New Capabilities

- `house-mode-binding`: per-AL coupling between an external HA mode entity and the three runtime switches. Covers entity-source configuration, mode discovery, behavior-matrix data model, state-change handling, override semantics (strict by default), and degradation under missing/unavailable source entities.

### Modified Capabilities

- `options-flow`: gains a new "House mode" section with a driver field (`house_mode_entity`) and a conditional matrix renderer. Spec delta will capture this as ADDED Requirements + a MODIFIED Requirement on the section layout list.

## Impact

- **`custom_components/adaptive_lighting/config_flow.py`** — new section, new field, dynamic matrix rendering based on the discovered mode list of the selected entity.
- **`custom_components/adaptive_lighting/__init__.py`** — `async_setup_entry` subscribes to `state_changed` for the configured `house_mode_entity` via `hass.helpers.event.async_track_state_change_event`.
- **`custom_components/adaptive_lighting/switch.py`** — `AdaptiveSwitch` (the master class) gains an `_apply_house_mode(mode_value)` method that flips the three runtime switches per the configured matrix.
- **`custom_components/adaptive_lighting/const.py`** — `CONF_HOUSE_MODE_ENTITY`, `CONF_HOUSE_MODE_MATRIX` constants; default matrix shape (empty dict).
- **`tests/test_house_mode_binding.py`** — new file. Tests: mode change flips switches per matrix; unknown mode value is logged but doesn't crash; entity unavailable triggers warn-once behavior; empty matrix is a no-op; mode-discovery from `input_select.options`; manual mode list for non-select entities.
- **No new runtime dependencies.**

**Sequencing**: depends on `cdit-config-redesign`. May land in parallel with `add-runtime-range-controls` (no overlap). Open architectural question for design: strict vs sticky override semantics.
