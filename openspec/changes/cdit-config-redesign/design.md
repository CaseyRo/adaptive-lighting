## Context

Upstream `basnijholt/adaptive-lighting` is a mature HA custom component (~10k LOC, 800+ stars). Its options flow is built by iterating over `VALIDATION_TUPLES` in `const.py` — 39 entries, each a `(key, default, voluptuous_validator)` tuple. The result is one flat `vol.Schema` rendered as a single tall form with no grouping, no conditional visibility, custom `int_between` validators (no slider UI), and silent no-op behavior when the entry was YAML-configured.

CDiT's install is one household, opinionated about scenes and house modes, and uses Sun2 for precise twilight events. Half of upstream's options are dead weight in that context (sleep mode, take-over-control, manual sun-time math). The other half is hard to find because nothing is grouped.

This change resets the dialog. It also removes the sleep-mode switch entity from the switch platform — sleep mode is dropped wholesale, not just hidden.

## Goals / Non-Goals

**Goals:**
- 18-field dialog that fits on one screen via collapsible sections.
- Sun curve driven by HA entities, so Sun2 (or any other twilight source) plugs in via the existing entity selector.
- Native HA selectors for everything (sliders, dropdowns, entity pickers) instead of voluptuous `int_between` wrappers.
- Reload-on-save without manual `async_unload_entry` / `async_setup_entry` plumbing.
- Honest message when the entry is YAML-managed (currently silently no-ops).
- One-shot break: no migration code, manifest version bump, clear "recreate your entry" message.

**Non-Goals:**
- Multi-step wizard. Editing dominates over setup in this integration's lifetime; sections beat steps.
- Backwards compatibility with upstream config entries.
- Translations beyond `en.json`. Other locales are out of scope; upstream's translations can be culled in a follow-up.
- Replacing the simulator webapp at `webapp/`. It targets the upstream curve model and is decoupled from the HA integration. Out of scope.
- Removing `astral` as a transitive dep. It's still imported elsewhere; pruning it is a follow-up.
- Touching `tests/` for unaffected features (color helpers, light state diffing, etc.). Only config-flow, sleep-mode, and take-over-control tests get rewritten.

## Decisions

### Decision 1: Collapsible sections via HA's `section()` helper, not a multi-step flow

**What we chose:** One `async_step_init` that returns a single schema with grouped sections built via the HA Frontend `section()` helper. All fields visible (or conditionally visible) on one screen.

**Why:** Setup happens once per AL config; editing happens dozens of times over the install's lifetime. Wizards optimize for first-run cost (guidance) at the expense of every subsequent edit (clicks). Sections give us guidance through grouping while keeping editing fast.

**Alternatives considered:**
- **Multi-step flow** (`async_step_basics` → `async_step_curve` → ...). Rejected — every edit becomes a click-through. Also, conditional visibility across steps is messier than within a single section-grouped form.
- **One flat dialog with field-order reshuffling.** Rejected — without visual grouping, ordering alone doesn't communicate which fields belong together.

### Decision 2: Entity-driven sun timing, no `astral` in the curve path

**What we chose:** Two entity selectors (`sunrise_entity`, `sunset_entity`) of `domain: sensor, device_class: timestamp`. Defaults to built-in `sensor.sun_next_rising` / `sensor.sun_next_setting`. The curve math reads `hass.states.get(<entity_id>)` for the timestamps, not `astral`.

**Why:** Lets Sun2 (or any custom sun source) plug in without a code change. Matches HA convention ("everything is an entity"). Decouples us from `astral`'s quirks at high latitudes (irrelevant to Germany, but it's free elegance). Single source of truth — your `sensor.sun_next_rising` is also what every other automation in the house reads.

**Alternatives considered:**
- **Keep `astral` and offer a "sun source" toggle.** Rejected — code path bifurcation, two implementations to test, defeats the simplification goal.
- **Hardcode `sun.sun` and drop the selector.** Rejected — explicitly precludes Sun2, which is the whole reason to refactor sun timing.

### Decision 3: Hardcoded tanh curve with 30-minute half-width

**What we chose:** `brightness_mode` field is deleted. Curve is always tanh. The half-width (`brightness_mode_time_dark` / `_time_light` upstream) is hardcoded as a single constant `RAMP_HALF_WIDTH_SECONDS = 1800` in `const.py`.

**Why:** Three modes (default / linear / tanh) were a research-era artifact; tanh is the eye-friendly choice for any household use case. The half-width sweet spot (30 min) is well-studied for circadian-friendly transitions and looks reasonable from solstice (sunrise 04:30) to equinox (sunrise 06:00). Removing the knob removes a UX maze.

**Alternatives considered:**
- **Keep `brightness_mode` as a hidden constant, expose half-width.** Rejected — same maintenance cost as keeping both, with no real win.
- **Expose half-width as one Advanced slider.** Rejected (initially considered). One less knob is genuinely better than one customizable knob — advanced fields rot when unused.

### Decision 4: Strict break, no migration code

**What we chose:** Bump `manifest.json` major version (1.x → 2.0.0-cdit.1). On upgrade, HA fails to load old config entries with a "this version is incompatible" toast. User recreates the entry manually.

**Why:** Single-household fork. The cost of one manual re-setup is ~5 minutes. Migration code that strips removed keys and silently translates old values would be ~50 LOC, would carry across the next two breaks, and is the kind of code that hides edge-case bugs.

**Alternatives considered:**
- **Silent strip on `async_setup_entry`.** Rejected — looks magical, hides which fields the user thought were configured.
- **`async_migrate_entry` with explicit version bump.** Rejected — correct for a public fork, overkill for one user. Re-evaluate if anyone outside CDiT installs this.

### Decision 5: Native HA selectors instead of voluptuous `int_between`

**What we chose:** `NumberSelector` with `min`, `max`, `step`, `unit_of_measurement`, `mode=NumberSelectorMode.SLIDER` (or `BOX` for fine-grained); `EntitySelector` with domain/device_class filters; `BooleanSelector`; `DurationSelector` for time intervals. All in `homeassistant.helpers.selector`.

**Why:** Selectors render as proper UI (sliders, dropdowns, color pickers, entity pickers). `int_between(1, 100)` validates correctly but renders as a plain text field — same UX whether the range is brightness, color temp, or seconds. Selectors are the direction HA core is moving; staying on voluptuous custom validators means re-implementing this every minor HA release.

**Alternatives considered:**
- **Keep voluptuous wrappers, restyle via custom frontend card.** Rejected — explicitly pulls us into frontend territory, which is out of scope for this change.

### Decision 6: `OptionsFlowWithReload` instead of manual reload

**What we chose:** Subclass `homeassistant.config_entries.OptionsFlowWithReload` (added to HA core in 2024.10). Override `async_step_init` only. No `async_unload_entry` / `async_setup_entry` reload plumbing.

**Why:** The documented, supported path. Manual reload has subtle bugs around entity registry stale state and listener leakage. `OptionsFlowWithReload` handles them by tearing down and rebuilding the entry atomically.

**Alternatives considered:**
- **Stay on `OptionsFlow` and call `hass.config_entries.async_reload(...)` manually after save.** Rejected — duplicates HA framework code, easy to forget on edge paths.

### Decision 7: Delete the sleep mode switch entity, don't hide it

**What we chose:** Remove the sleep-mode switch class from `switch.py` entirely. Each AL config now creates 3 switches (master, adapt_brightness, adapt_color), not 4. Sleep-mode state machine is also stripped from the master switch class.

**Why:** Keeping unused entities pollutes the device page, accumulates state, and creates ambiguity ("will this wake up if I flip it?"). Hiding from UI but keeping the code path means the state machine still runs, just invisibly — worst of both worlds.

**Alternatives considered:**
- **Keep the entity, hide from UI.** Rejected — see above.
- **Keep the class, gate behind a feature flag.** Rejected — dead code with a flag is still dead code.

### Decision 8: Delete take-over-control, don't gate it

**What we chose:** Remove `take_over_control`, `take_over_control_mode`, `detect_non_ha_changes`, `autoreset_control`, `only_once`, `adapt_only_on_bare_turn_on`. Strip the take-over-control state machine from `switch.py`.

**Why:** Manual-override semantics live at the scene/automation layer in CDiT's house. The take-over-control code threads through every adapter call in `switch.py` — making it conditional via a feature flag doesn't reduce complexity, just relocates it. Delete is the only honest option.

**Alternatives considered:**
- **Gate behind `enable_legacy_overrides` flag.** Rejected — preserves the code, defeats the simplification goal, accumulates "advanced settings" that nobody ever turns on.
- **Keep `intercept` and `multi_light_intercept`** — these *are* kept. They're transport behavior (hooking `light.turn_on` to merge adaptive values), not manual-override semantics. Different concern.

### Decision 9: Conditional visibility costs one submit cycle

**What we chose:** Fields with drivers (`send_split_delay` driven by `separate_turn_on_commands`; sun-time min/max pairs driven by whether the sun-entity is set) are conditionally included in the schema. When the driver changes, the user submits the form and HA re-renders with the new fields.

**Why:** HA's config flow can't re-render a single step dynamically when a field changes within that step. The supported path is to submit and let the next render reflect the new state. This costs one extra submit when a driver changes — accepted because driver changes are rare (you set `separate_turn_on_commands` once and forget).

**Alternatives considered:**
- **Always show all fields.** Rejected — the whole point is to hide noise.
- **Split into multiple steps when a driver changes.** Rejected — back to the wizard problem.

### Decision 10: Capability slug is `options-flow`, scoped tight

**What we chose:** This change defines one capability, `options-flow`, covering the integration's setup/reconfigure UI. Future changes get their own capabilities (`runtime-controls` for the number entities, `house-mode-binding` for the per-mode matrix).

**Why:** Keeps each spec testable and each requirement focused. A single `integration-configuration` umbrella would collect every config-related requirement across multiple changes — hard to read, hard to maintain.

### Decision 11: Sun curve math — max brightness lives strictly between the two entities

**What we chose:** Given `t_sunrise` and `t_sunset` from the entities, the brightness curve is:

```
       t < t_sunrise - 1800s :  brightness = min
       t in [t_sunrise - 1800s, t_sunrise + 1800s] : tanh ramp from min → max
       t in [t_sunrise + 1800s, t_sunset - 1800s]  : brightness = max
       t in [t_sunset - 1800s, t_sunset + 1800s]   : tanh ramp from max → min
       t > t_sunset + 1800s :   brightness = min
```

Same shape applied to color temperature, scaled between `min_color_temp` and `max_color_temp`.

**Why:** Symmetric, deterministic, easy to test. The user's pick of entity is the semantic anchor — pick `sun2_dawn` and full brightness arrives 30 min after civil dawn.

**Alternatives considered:**
- **Treat the entities as ramp midpoints.** Rejected — less intuitive; "when does the day start" should map to "when does max brightness start," not "when am I halfway to max."
- **Sun-elevation-style curve interpolated between events.** Rejected — adds astral-style math complexity without proportional benefit. The user picked entity-driven explicitly to avoid that.

### Decision 12: Auto-remove leftover sleep-mode switch entities on first load

**What we chose:** In `async_setup_entry`, scan the entity registry for any `switch.adaptive_lighting_sleep_mode_*` entries tied to this integration's config entry, remove them via `entity_registry.async_remove(entity_id)`, and log each removal at INFO level.

**Why:** Without this, upgrading users see orphan switches in Settings → Entities forever. The cleanup is bounded (only entities this integration created, identifiable by `unique_id` prefix), idempotent (runs every setup, no-op after the first), and small (~10 LOC). The log line gives auditability.

**Alternatives considered:**
- **Log + leave for manual cleanup.** Rejected — pollutes the device page; CDiT install has half a dozen AL configs, that's half a dozen orphans.
- **One-time cleanup script.** Rejected — extra step the user has to run.

### Decision 13: Pin `homeassistant` minimum version to 2025.1.0

**What we chose:** `manifest.json` declares `"homeassistant": "2025.1.0"` as the minimum supported HA version.

**Why:** Lets us use the latest stable selector API (`NumberSelector` with `BOX_OR_SLIDER` mode, `EntitySelector` with multi-domain filtering), `section()` helper with no rendering quirks, and `OptionsFlowWithReload` with all 2024.x bug fixes applied. Excludes pre-2025.1 installs intentionally — running HA more than ~6 months behind is its own problem.

**Alternatives considered:**
- **Pin 2024.10.** Rejected (initially recommended) — gives back the headroom for no clear benefit; user explicitly chose to go bolder.
- **No pin (`"homeassistant"` absent).** Rejected — silently runs on incompatible versions, fails confusingly when `section()` doesn't render right.

### Decision 14: Sun-entity selectors are strictly typed

**What we chose:** Both `sunrise_entity` and `sunset_entity` use `EntitySelector(EntitySelectorConfig(domain="sensor", device_class="timestamp"))`. Only sensors with `device_class: timestamp` show up in the picker.

**Why:** Covers all real use cases (built-in `sensor.sun_next_rising`, Sun2's `sensor.sun2_*`, any custom timestamp sensor) while preventing foot-guns — `input_datetime` entities don't auto-update for next sunrise, and picking one would silently produce wrong curves. Strict typing makes the wrong choice impossible.

**Alternatives considered:**
- **Loose typing (any datetime entity).** Rejected — invites the `input_datetime` foot-gun.
- **Strict + escape hatch constant.** Rejected — no real use case for loose mode; adding the knob now is YAGNI.

### Decision 15: `RAMP_HALF_WIDTH_SECONDS` lives in `const.py`

**What we chose:** Define `RAMP_HALF_WIDTH_SECONDS = 1800` in `const.py` near the other tuning defaults, with an inline comment explaining the 30-minute choice (eye-friendly circadian transition, robust across solstice-to-equinox sunrise drift).

**Why:** `const.py` is the canonical "knobs you might tweak" location in HA custom components. Discoverable to anyone reading the integration. The comment captures the rationale so future-CDiT doesn't relitigate.

**Alternatives considered:**
- **`__init__.py` near curve math.** Rejected — cohesive but harder to find when you want to tune.
- **Buried in `config_flow.py`.** Rejected — treats the constant as flow-private, but the curve math is the actual consumer.

## Risks / Trade-offs

- **[Sun2 isn't installed in HA]** → Defaults work fine — built-in `sensor.sun_next_*` is always present. Mitigation: README mentions Sun2 as a recommended-but-not-required HACS install.
- **[`sensor.sun_next_rising` flips to tomorrow's date the moment sunrise passes]** → The curve math must handle this: after `t_sunrise` has passed, read `sun.sun.last_changed`/historical state, or anchor today's curve from `t_sunset` and the implicit "today is between yesterday's sunset and tomorrow's sunrise." Mitigation: write a small helper `today_sun_events()` that returns `(today_sunrise_dt, today_sunset_dt)` based on current time vs entity values; specs/tasks will cover this explicitly.
- **[Removed sleep-mode switch entity lingers in HA's entity registry after upgrade]** → Old `switch.adaptive_lighting_sleep_mode_<name>` entries remain in `core.entity_registry` until manually deleted. Mitigation: document in CHANGELOG; provide a one-line `hass.config_entries.async_remove(...)` snippet for cleanup, or accept manual deletion via UI.
- **[Strict break inconveniences any non-CDiT installer]** → Anyone forking the CDiT fork to use upstream config entries will hit the break. Mitigation: explicit "this fork is opinionated; existing AL entries will not load" notice in README and on the fork's GitHub description.
- **[HA `section()` API is relatively young (added 2024.5)]** → Risk of styling/render quirks on older HA versions. Mitigation: bump `manifest.json` `homeassistant` minimum version to ≥ 2024.10 (when `OptionsFlowWithReload` also landed, so we're pinning both together).
- **[The synthetic tanh curve drifts from astronomical reality near solstices]** → Won't perfectly match astral-computed elevation. Mitigation: this is by design — the user picked Sun2 entities for accuracy at the *endpoints*; smooth dimming between them is what matters, not physical accuracy.
- **[`include_config_in_attributes` buried in Diagnostics could trip debug-time users]** → Mitigation: section is collapsed by default but not hidden; surfaces on expand. Mention in README's "Debugging" subsection.

## Migration Plan

This change is delivered as a single PR on the fork's `main` branch. No phased rollout; CDiT-dev is the only consumer.

1. Land the PR.
2. Tag the release (`v2.0.0-cdit.1`).
3. On the running HA install:
   - Snapshot current AL config (Settings → Integrations → Adaptive Lighting → ⋮ → Download Diagnostics, or just screenshot the options dialog).
   - Update via HACS or manual copy of `custom_components/adaptive_lighting/`.
   - Restart HA.
   - Old config entry shows as "failed to load."
   - Delete the failed entry.
   - Recreate via Settings → Add Integration → Adaptive Lighting, copying the snapshot's values into the new section layout.
4. Manually delete leftover `switch.adaptive_lighting_sleep_mode_<name>` entries via Settings → Devices → Entities (filter by integration, sort by "missing").

**Rollback:** `git revert` the PR merge commit. Old upstream config entries do *not* auto-recover — you'd reinstall upstream AL from HACS and re-create the entry there.

## Open Questions

None — all resolved and folded into Decisions 12–15.
