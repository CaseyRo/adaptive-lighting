## Why

The CDiT-redesigned Adaptive Lighting integration exposes its surface through HA's standard mechanisms: a device page, three switches per profile, four `number` entities once `add-runtime-range-controls` lands, and an options dialog. That surface is *functional* but not *unified* — the user assembles their own mental picture from rows in the entity list, scattered slider entities, and a config dialog they only see during setup. Day-to-day, the question "what is the kitchen actually doing right now?" requires reading three or four entities and computing.

This change adds a **dedicated Lovelace card** that places all of an AL profile's state on one screen: current brightness and color temperature, position on the 24-hour curve, the three runtime switches, the four range sliders, and (if configured) the active house mode. The card is **additive** — it does not replace the device page or the existing entities; it composes them into a single visual home for a profile.

> **Status**: proposal + design complete. Specs and tasks deferred until prerequisites (`cdit-config-redesign`, `add-runtime-range-controls`) land.

## What Changes

- **New top-level directory `lovelace-card/`** in this repo. Self-contained TypeScript + Lit + Vite frontend project. Builds to a single bundled JS file (`cdit-adaptive-lighting-card.js`) that registers a `<cdit-adaptive-lighting-card>` custom element with HA's `customCards` registry.
- **One card per Adaptive Lighting profile.** Card config takes a single field: the profile's config entry ID (auto-discovered from the user's installed AL configs in the visual editor). The card finds all related entities (switches, numbers, sun-time sensors) by walking the device.
- **Sections rendered**: header with profile name, "Now: <brightness>% · <K> K" hero, 24-hour curve with current position marker, three switches as inline toggles, four range sliders, optional house-mode badge with current mode value.
- **Interactions are HA-native services**: switch toggles call `switch.toggle`, slider drags call `number.set_value` (debounced 300 ms after drag end), long-press opens HA's standard more-info dialog for the underlying entity.
- **Editor**: the card ships a Lovelace visual editor (`<cdit-adaptive-lighting-card-editor>`) so dashboard users don't hand-edit YAML.
- **Distribution: HACS frontend resource**, plus optional auto-registration. When the integration is installed and the user enables a config-flow toggle "Register Lovelace card resource automatically", the integration writes the Lovelace resource entry via `lovelace.resources` so the user does not have to add it manually.
- **Bundled with the integration release** — `manifest.json` of the integration declares the card's HACS metadata so HACS treats them as one package.
- **Theming**: card respects HA's CSS theme variables for surface and text colors but overrides typography (a specific display + body pairing) and adds its own warm/cool accent that follows the current color-temperature output.

## Capabilities

### New Capabilities

- `lovelace-card`: dashboard card for a single Adaptive Lighting profile. Covers card configuration model, auto-discovery of related entities, the rendered visual layout, interaction-to-service mapping, the visual editor, theming behavior, accessibility surface, and the distribution / auto-registration flow.

### Modified Capabilities

None. This is purely additive — no existing capability changes its requirements.

## Impact

- **`lovelace-card/`** (new directory): TypeScript source under `src/`, Vite build config, package.json with Lit + HA-frontend-types dependencies, README with install instructions, a `dist/` output.
- **`hacs.json`** at repo root: extend with a `"plugin"` section so HACS treats the built card as an installable frontend resource alongside the integration.
- **`custom_components/adaptive_lighting/__init__.py`**: optional `async_register_lovelace_resource()` helper that writes the resource URL into HA's lovelace storage when the auto-register option is enabled.
- **`custom_components/adaptive_lighting/config_flow.py`**: one new field in the integration's *global* (not per-entry) options — `register_card_resource` boolean — sitting in the Diagnostics section. Default off.
- **`custom_components/adaptive_lighting/const.py`**: const for the resource URL (`/hacsfiles/adaptive-lighting/cdit-adaptive-lighting-card.js`) plus an off-by-default `CONF_REGISTER_CARD_RESOURCE`.
- **Tests**: card has its own test setup (Vitest + Playwright for visual regression on key states); integration tests for the auto-register helper.
- **No changes to existing entities or services.** The card consumes the public HA state machine.

**Sequencing**: depends on `cdit-config-redesign` (3-switch model, sun-entity sensors) and `add-runtime-range-controls` (the four `number` entities the sliders bind to). Strictly later than both. Independent of and parallel-able with `house-mode-modes`.
