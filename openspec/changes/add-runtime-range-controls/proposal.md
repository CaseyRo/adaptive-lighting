## Why

The four brightness/color-temperature ranges (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) are exactly the values a CDiT household wants to live-tune from a Lovelace card — the difference between "kitchen feels too warm" and "kitchen feels right" is one slider away. Today they are setup-time options buried in the integration's options dialog; every tweak forces a click trail through Settings → Devices → Adaptive Lighting → Configure → Save, and triggers a full integration reload via `OptionsFlowWithReload`.

This change promotes the four ranges to first-class runtime entities (HA's `number` platform), with the config flow remaining the place to seed the initial defaults and any subsequent UI edit writing through transparently.

> **Status**: stub proposal. Specs, design, and tasks to be written when work on this change starts. Depends on `cdit-config-redesign` landing first.

## What Changes

- **Add a `number` platform** to the integration. Each AL config entry creates four `number` entities:
  - `number.adaptive_lighting_<name>_min_brightness` (range 1–100, step 1, %, slider mode)
  - `number.adaptive_lighting_<name>_max_brightness` (same)
  - `number.adaptive_lighting_<name>_min_color_temp` (range 1000–10000, step 100, K, slider mode)
  - `number.adaptive_lighting_<name>_max_color_temp` (same)
- **Source-of-truth model: write-through** (Decision C from the prior session). The number entity is canonical at runtime; config flow values seed the entity on first creation and act as a mirror afterwards.
  - On config-entry creation, the four number entities are initialized from `entry.options`.
  - When the user moves a slider on the number entity, the new value is persisted back to `entry.options` via `async_update_entry`.
  - When the user saves the options flow, the four corresponding number entities have their state updated to match.
- **Curve math reads from number entities**, not from `entry.options` directly. Single read path at evaluation time.
- **Options flow keeps the four fields visible** in the Daytime curve section so users can still tune them from the config screen (especially first-time setup). Both surfaces stay in sync.

- **Entity-naming hygiene** (folded in because the new entities would inherit the same problem otherwise): switch the existing three switch entities and the four new number entities to HA's `has_entity_name = True` convention. Device name becomes the profile name (e.g., "Dining MVP"); entity names become short ("Brightness", "Color", "Min color temp"). Today's friendly names like "Adaptive Lighting Adapt Brightness dining_mvp_lights" truncate to "Adaptive Lighting Adapt Br…" in HA's More-info card; after this change they read as "Dining MVP Brightness" (21 chars, well inside the truncation window). `unique_id`s stay stable, so existing entity_ids and automations keep working.

## Capabilities

### New Capabilities

- `runtime-range-controls`: live-tunable brightness and color-temperature range entities, with bidirectional sync to the config entry options. Covers entity creation, write-through semantics, curve-math read path, and conflict resolution between the two surfaces. Also defines the `has_entity_name` naming convention applied to all AL entities (switches + number entities).

### Modified Capabilities

- `options-flow`: the Daytime curve section's four range fields gain write-through behavior to the new number entities. Spec delta will capture this as a MODIFIED requirement.

## Impact

- **`custom_components/adaptive_lighting/number.py`** — new file, `number` platform implementation.
- **`custom_components/adaptive_lighting/const.py`** — `Platform.NUMBER` appended to platform list; entity unique-id pattern constants.
- **`custom_components/adaptive_lighting/__init__.py`** — curve math switches its reads for the four ranges from `entry.options[...]` to `hass.states.get(<number_entity_id>)`. `async_setup_entry` registers number platform.
- **`custom_components/adaptive_lighting/config_flow.py`** — save path also writes through to the four number entities (if they exist). Initial setup creates them.
- **`tests/test_number_platform.py`** — new file. Tests: entity creation on first setup, slider change persists to options, options save writes to entity, curve reads pick up latest value, removal cleans up entities.
- **`tests/test_config_flow.py`** — extends existing tests to cover the write-through path.
- **No new runtime dependencies.**

**Sequencing**: this change MUST land after `cdit-config-redesign` — relies on its pruned schema, native selectors, and `OptionsFlowWithReload` pattern.
