## Context

After `cdit-config-redesign`, the four most-tuned values — `min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp` — live in the options flow's Daytime curve section. Editing them requires the full Settings → Devices & Services → Adaptive Lighting → Configure → Save click trail, and each save triggers a full integration reload via `OptionsFlowWithReload` (entities torn down, switches re-registered, ~1 s of disruption).

That's the wrong gesture for the right action. "The kitchen feels too warm tonight" should be a slider on the dashboard, not a dialog round-trip. This change promotes those four values to first-class HA `number` entities — sliders that show up on any Lovelace view, that scripts can read, that automations can write, that the user can voice-command via the HA Assist pipeline.

The integration's curve math currently reads `entry.options[CONF_MIN_BRIGHTNESS]` (etc.) on every tick. After this change, it reads `hass.states.get("number.adaptive_lighting_<name>_min_brightness").state`. The options flow still owns these fields (for setup ergonomics), but the runtime source of truth shifts to the entities.

## Goals / Non-Goals

**Goals:**
- Four live-tunable entities per AL profile, slider mode, native HA selectors. Visible on the integration's device page and embeddable in any Lovelace card.
- Persistent across HA restart via `RestoreNumber` (no separate `Store` plumbing).
- Curve math reads from a single runtime source — the entity state. Options flow re-seeds entities on save.
- Slider drag must NOT trigger an integration reload. Tuning is cheap; setup is heavy.
- Setup parity: a fresh AL config still has working defaults from `entry.options`; first-time users do not need to discover the slider entities to get a working install.
- Options-flow open seeds from current entity state, not the stale options snapshot — what the user sees in the dialog is what their lights are running.

**Non-Goals:**
- Promoting non-range setup-time fields (`interval`, `transition`, `initial_transition`, `adapt_delay`, `send_split_delay`, `ramp_half_width`) to runtime entities. Setup-time concerns stay in the options flow.
- A custom Lovelace card. Native HA number cards render the four entities fine; a dedicated card is a separate change (`add-lovelace-card`, already stubbed).
- Reverse coupling — making the options flow read from entities instead of `entry.options` as its persistence backbone. Options flow remains options-flow; the entities are a *runtime* surface layered on top.
- Service handlers for setting range values. The number entity's own `number.set_value` service is enough.

## Decisions

### Decision 1: Single runtime source of truth — the number entity state

**What we chose:** The four `number` entities are the canonical place the curve math reads from at runtime. `entry.options` becomes the seed-on-create and last-save snapshot, but no longer the read path during curve evaluation.

**Why:** Avoids the dual-source-of-truth bug class. With one read path, there is no "which one wins when they disagree?" question. The options flow remains the place to set defaults; the entity is the place to tune live. Different gestures, different surfaces, one read.

**Alternatives considered:**
- **`entry.options` canonical, entity is a passthrough proxy.** Rejected — every slider change has to dual-write to options, which triggers `OptionsFlowWithReload` reload. ~1 s integration disruption per slider tick is unacceptable UX.
- **Custom `hass.data` runtime cache, written by both surfaces, read by curve math.** Rejected — third layer just to bridge the gap between "entry.options is persistent" and "entity is interactive". RestoreNumber already gives us per-entity persistence.

### Decision 2: `RestoreNumber` for persistence, no write-back to `entry.options` on slider change

**What we chose:** The four entities extend `homeassistant.components.number.RestoreNumber`. Each entity persists its state via HA's native restore mechanism. Slider changes do not call `async_update_entry`. `entry.options` is only updated when the user explicitly saves the options flow.

**Why:** Three wins. (1) Avoids the `OptionsFlowWithReload` reload-on-every-slider trap. (2) Uses the HA-idiomatic restore path — same machinery scenes and automations use for any `number` entity. (3) Decouples the persistent-config concept (options flow) from the live-tuning concept (entity); the two surfaces stay logically distinct, even if they happen to mirror each other most of the time.

**Alternatives considered:**
- **Dual-write on slider change + suppress reload via a temporary listener detach.** Rejected — peeks into `OptionsFlowWithReload` internals; brittle across HA core upgrades.
- **`Store` helper keyed by entry_id with the four values.** Rejected — extra abstraction layer for the same persistence guarantee RestoreNumber gives us for free.
- **No persistence at all — slider value resets to `entry.options` defaults on every HA restart.** Rejected — punishes users who tune their install. Restart should not lose tuning.

### Decision 3: Options-flow save pushes new values into the entities via reload-and-reseed

**What we chose:** When the user saves the options flow, `entry.options` updates as normal, `OptionsFlowWithReload` reloads the integration, and the number platform's `async_setup_entry` recreates the entities. On creation, each entity reads its initial value from `entry.options[CONF_*]` rather than from the RestoreNumber state. Result: just-saved values appear immediately on the sliders.

**Why:** Reuses the existing reload mechanism instead of inventing a new "push to entity" pathway. The hierarchy is deliberate: a save through the options flow is an explicit user gesture ("these are my new defaults"), so the just-saved value supersedes any pre-existing slider position. The RestoreNumber data is the fallback when there are no fresher options.

**Alternatives considered:**
- **Skip reload on options save and push to entities directly via `entity.async_set_native_value()`.** Rejected — works for the four range fields but the other ~14 options fields still need reload to take effect, so reload happens regardless. Doing two save paths (reload-everything vs. push-this-entity) doubles the surface to test.
- **RestoreNumber state wins over `entry.options` on entity creation.** Rejected — means the options flow Save button silently does nothing for the range fields, which is the opposite of what the user just asked for.

### Decision 4: Options flow OPEN seeds the four range fields from the entity, not from `entry.options`

**What we chose:** When the options flow renders, the four range field defaults are read from `hass.states.get(<entity_id>).state` (cast to int), with a fallback to `entry.options[CONF_*]` if the entity is unavailable. The other ~14 fields continue to seed from `entry.options` as today.

**Why:** "What I see in the dialog matches what's running" is a stronger UX invariant than "what I see in the dialog matches what I last typed here." If the user spent a week tweaking the dashboard slider down to 65% and then opens the dialog, the dialog should show 65, not the 70 they typed at install time.

**Alternatives considered:**
- **Seed from `entry.options` always.** Rejected — divergence between dialog and reality is exactly the kind of "why does saving snap my slider back?" surprise this change is built to eliminate.
- **Seed from entity, but show both values in the dialog (e.g., "current: 65, last saved: 70").** Rejected — visual clutter for a corner case. The user can read the slider entity directly if they want to see history.

### Decision 5: Entity naming pattern uses the profile slug

**What we chose:** Each entity's `unique_id` is `<entry.entry_id>_<field>` (e.g., `<entry_id>_min_brightness`), the device name is the profile name, and HA's default entity-id slug-from-friendly-name yields entities like `number.adaptive_lighting_<profile>_min_brightness` after slugification.

**Why:** Mirrors the convention `cdit-config-redesign` set for the three switches (`switch.adaptive_lighting_<profile>_adapt_brightness` etc.). Predictable for automation authors. No surprises.

**Alternatives considered:**
- **Per-field unique_id without profile in the slug.** Rejected — collides across multiple AL profiles.
- **Short slug (`number.al_<profile>_min_b`).** Rejected — saves keystrokes, costs readability in dashboards.

### Decision 6: Native selector configuration per field

**What we chose:**

| Field | min | max | step | unit | mode | icon |
|---|---|---|---|---|---|---|
| `min_brightness` | 1 | 100 | 1 | `%` | slider | `mdi:brightness-3` |
| `max_brightness` | 1 | 100 | 1 | `%` | slider | `mdi:brightness-7` |
| `min_color_temp` | 1000 | 10000 | 100 | `K` | slider | `mdi:thermometer-low` |
| `max_color_temp` | 1000 | 10000 | 100 | `K` | slider | `mdi:thermometer-high` |

**Why:** Same ranges and units as the options-flow `NumberSelector` config (R5 of `options-flow` spec). Icons pick a "low/high" pair so the slider rows visually pair up on the device page.

**Alternatives considered:**
- **`box-or-slider` mode for color temp** (which has a 9000-unit range and 100-unit step). Rejected for now — pure slider mode is fine on desktop; mobile UX is the only place box-mode helps, and 90 steps is still draggable. Re-evaluate if user complains.
- **Same `mdi:brightness-percent` icon for both brightness entities.** Rejected — visually identical entities on the device page is a discoverability foot-gun.

### Decision 7: Range validation lives in the selector, not in a custom validator

**What we chose:** Min/max bounds are enforced by `NumberEntity.native_min_value` / `native_max_value` (frontend rejects out-of-range inputs). The curve math does not re-validate — it trusts the state machine to hold a sane number.

**Why:** Aligns with `cdit-config-redesign` Decision 5 (native selectors over voluptuous wrappers). One layer of validation, frontend-enforced.

**Alternatives considered:**
- **Belt-and-braces validation in curve math.** Rejected — duplicates the frontend rule. If the state machine ever held a bogus value, the curve math would silently coerce; better to fail loud (let `int(...)` raise) so we hear about real bugs.

### Decision 8: Read path in curve math — `hass.states.get`, no caching

**What we chose:** `AdaptiveSwitch._get_settings()` (or wherever the curve evaluates) reads `hass.states.get(self._range_entity_id("min_brightness")).state` on every tick, casts to int, passes into `SunLightSettings`. No local attribute cache, no listener-on-change.

**Why:** The state machine read is a dict lookup. Curve evaluation happens every ~90 s (the `interval` setting). The 4 state-machine reads cost ~5 µs total. Caching saves nothing measurable and adds invalidation complexity ("which event resets the cache?").

**Alternatives considered:**
- **Cache + state-change listener.** Rejected — premature optimization. If profiling ever shows curve eval is hot, revisit.
- **Pass `hass` into `SunLightSettings.brightness_pct()` and read inside.** Rejected — pollutes the pure-math wrapper with HA state access. The switch class is the right boundary.

### Decision 9: Entity unavailability falls back to `entry.options`

**What we chose:** If `hass.states.get(<entity_id>)` returns `None` or the state is `unavailable` / `unknown`, the curve math falls back to `entry.options[CONF_*]`. Logged at DEBUG.

**Why:** Belt-and-braces. The race window is small (entity created in same setup pass as the switch) but real. Falling back to the same value the entity would seed from anyway keeps the curve continuous through any transient hiccup.

**Alternatives considered:**
- **Skip the curve update if entities are unavailable.** Rejected — invisible to the user, looks like a freeze.
- **Hard-fail loudly.** Rejected — startup ordering is HA's responsibility, not the user's problem to debug.

### Decision 10: Capability slug `runtime-range-controls`

**What we chose:** This change defines one new capability — `runtime-range-controls` — covering entity creation, write-through semantics, the curve-math read path, restore behavior, and option-flow seeding. It also modifies the existing `options-flow` capability (the Daytime curve section gains write-through behavior on save).

**Why:** Scoped tight, matches the pattern set by `options-flow` in `cdit-config-redesign`. Keeps spec scenarios testable in isolation.

### Decision 11: All AL entities use HA's `has_entity_name` composition

**What we chose:** Every entity created by this integration sets `_attr_has_entity_name = True` and registers under a device record whose `name` is the profile's display name (i.e., `entry.title`, which mirrors `entry.data[CONF_NAME]`). The per-entity `_attr_name` carries only the entity's role:

| Entity class | `_attr_name` | Resulting friendly name | Chars |
|---|---|---|---|
| `AdaptiveSwitch` (master) | `None` | "Dining MVP" | 10 |
| `AdaptBrightnessSwitch` | `"Brightness"` | "Dining MVP Brightness" | 21 |
| `AdaptColorSwitch` | `"Color"` | "Dining MVP Color" | 16 |
| `AdaptiveRangeNumber(min_brightness)` | `"Min brightness"` | "Dining MVP Min brightness" | 25 |
| `AdaptiveRangeNumber(max_brightness)` | `"Max brightness"` | "Dining MVP Max brightness" | 25 |
| `AdaptiveRangeNumber(min_color_temp)` | `"Min color temp"` | "Dining MVP Min color temp" | 25 |
| `AdaptiveRangeNumber(max_color_temp)` | `"Max color temp"` | "Dining MVP Max color temp" | 25 |

**Why:** Today's friendly names ("Adaptive Lighting Adapt Brightness dining_mvp_lights") truncate to "Adaptive Lighting Adapt Br…" in HA's More-info card and overflow most Lovelace cards. The `has_entity_name = True` convention is the HA-idiomatic way to compose `<device> <role>` strings that read naturally and respect screen width. It also unifies presentation across the existing three switches and the four new number entities — a one-time fix instead of inheriting the problem.

**Why drop the "Adapt" verb from the two toggles:** Tightest fit on HA's narrowest cards (~28 char truncation point). The entity type (a toggle switch UI) already says "this is on/off"; the device context already says "this is adaptive lighting." Calling it just "Brightness" risks being read as a brightness value, but the toggle UI affordance and the integration icon disambiguate it in every HA surface where it renders. Worst case for clarity: an unfamiliar dashboard read; trade accepted for guaranteed fit and visual rhythm with the number-entity sliders.

**Entity-id stability:** `unique_id`s are unchanged by this decision, so the entity registry preserves existing entity_ids for any deployed install (automations and scripts referencing `switch.adaptive_lighting_adapt_brightness_dining_mvp_lights` keep working). Only the human-facing friendly name changes for existing installs. Fresh installs after this change ships get the cleaner entity_id slugs from the start.

**Alternatives considered:**
- **Strip "Adaptive Lighting" prefix without adopting `has_entity_name`.** Rejected — patches one symptom (the prefix) without fixing the structural problem (per-entity hand-composed names). Next entity we add inherits the same pattern.
- **Rename `unique_id`s to the cleaner pattern and let HA regenerate entity_ids.** Rejected — breaks every user automation. Not worth the upside; `has_entity_name` gives us the readable friendly name without touching unique_ids.
- **Use the entry id (`abc123…`) as the device name.** Rejected — opaque to users. Profile name is the right anchor.

## Risks / Trade-offs

- **[RestoreNumber state is wiped if the user deletes and recreates the integration]** → New install starts from `entry.options` defaults. Acceptable — that's the documented behavior for any HA entity. Mitigation: README note that "Settings → Devices → Adaptive Lighting → Configure" is the place to set defaults, "the sliders" are the place to tune live.
- **[Options-flow Save snaps live slider to the typed value]** → Intentional (Decision 3). Mitigation: the section framer text in `strings.json` says "saving here resets the live sliders to these values."
- **[Stale options dialog if user opens it during a long-running automation that's adjusting the sliders]** → The seed-on-open (Decision 4) reads the entity state at flow-open time; further automation changes after open are not reflected. Mitigation: this is the standard HA dialog-render contract; same behavior as every other config flow.
- **[Curve math reads state machine on every tick, ~90 s interval]** → Tiny perf cost; not a concern at human-scale tick rates. Mitigation: none needed; document in design.md (Decision 8).
- **[Profile rename via UI breaks the entity unique_id slug]** → `unique_id` uses `entry.entry_id`, not the profile name, so the unique_id is stable across renames. Entity ID slug (entity_id) regenerates from the friendly name; HA preserves it via entity registry. Mitigation: covered by HA's own rename handling; no special code needed.
- **[Race: user moves slider while options-flow save is in flight]** → Last-write-wins per the natural state-machine ordering: whichever async task lands last sets the value. Acceptable; the window is < 1 s. Mitigation: none.

## Migration Plan

Single PR on the fork's `main` branch. The `cdit-config-redesign` change is already archived (this depends on its options-flow contract, not its delivery).

1. Add the `number` platform.
2. Ship the runtime-range-controls capability via the spec delta.
3. Tag a release (`v2.1.0-cdit.1` — minor bump; no breaking change to existing entries).
4. Existing config entries pick up four new entities on next HA restart. The entities seed from the entry's saved options the first time they appear. No user action required.

**Rollback:** revert the PR. The four new entities disappear from the entity registry; the curve math reverts to reading `entry.options` directly. No data loss.

## Open Questions

None — all 11 decisions resolved.
