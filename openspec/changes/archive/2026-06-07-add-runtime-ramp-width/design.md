# add-runtime-ramp-width — design

## Context

`cdit-config-redesign` decision 3 hardcoded the tanh ramp half-width (`RAMP_HALF_WIDTH_SECONDS = 1800`) and explicitly rejected exposing it — "one less knob is genuinely better than one customizable knob." The 2026-06-07 seasonality exploration revised the picture: seasonal pacing (longer summer dusks) is a real want, the agreed home for seasonal *logic* is Node-RED via runtime entities ([[project-al-seasonality-decision]] memory), and ramp width is the only curve parameter without a runtime entity. The `runtime-range-controls` capability (implemented, archived 2026-05-17) established the full pattern: `number` platform, `RestoreNumber`, registry lookup by stable unique_id, per-tick reads with fallback, no reload on slider change.

Since then, `anchor_sun_events()` (added in the 2026-06-07 day-anchoring fix) also consumes the half-width — its post-sunset ramp-tail window must match the curve's width or wide evening ramps get truncated when the `next_*` sensors flip to tomorrow.

## Goals / Non-Goals

**Goals:**
- One ramp half-width number entity per profile, live-effective on the next curve tick.
- Fully drivable from Node-RED (seasonal flows) and Lovelace, like the four range entities.
- The day-anchoring tail window always equals the curve's active width.

**Non-Goals:**
- Per-event asymmetric widths (separate sunrise/sunset). No customer: summer-morning ramps run while the household sleeps.
- Decoupling CT from brightness curve shape (spec R4 coupling stands; separate tripwire).
- Any seasonal logic in the integration (day-length lerps etc.) — that lives in Node-RED.
- A config-flow field for the width.
- Winter-morning clock anchoring (separate tripwire).

## Decisions

### Decision 1: One width, both ramps

A single value parameterizes both the sunrise and sunset tanh windows, exactly as the constant does today (`SunLightSettings.ramp_half_width_seconds` is already one field). Splitting would double the entity surface for a window nobody is awake to see, and Node-RED can't meaningfully drive a morning width either. **Rejected:** `sunrise_ramp_width` / `sunset_ramp_width` pair — revisit only if a real morning use case appears; adding a second entity later is backward-compatible.

### Decision 2: Runtime entity only, constant fallback — no options-flow field

The entity is the *only* surface for this knob. Decision 3's rationale ("advanced fields rot in config dialogs") still holds for the dialog; what changed is the existence of a better surface. Consequences that diverge from the four range entities:

- Restore precedence is simply: restored value → `DEFAULT_RAMP_HALF_WIDTH_MIN` (30). There is no `entry.options` tier because no option exists.
- The options-flow seeding/propagation requirements (seed-from-entity on open, recreate-with-saved-value on save) do **not** apply.
- Unavailable-entity fallback in the curve path is the constant, logged at `DEBUG`, mirroring `_get_runtime_range` shape.

**Rejected:** adding a parallel `CONF_RAMP_HALF_WIDTH` option field — would reopen the dialog-bloat question decision 3 settled, and adds a second source of truth for zero benefit (NR doesn't read options).

### Decision 3: Entity unit is minutes; curve consumes seconds

`native_min=5`, `native_max=120`, `step=1`, `unit="min"`, `SLIDER`. Humans and Node-RED flows think in minutes; the curve math takes seconds. Conversion (`× 60`, int) happens at the single read site in `switch.py`. Bounds rationale: below ~5 min the adapt interval makes the ramp visibly steppy; above 120 min the two ramps would consume 4 h of curve and start crowding short winter days (Dec day length ≈ 7.8 h leaves a 3.8 h plateau at max width — still sane, which is why 120 is the cap and not less). **Rejected:** exposing seconds (matches code but hostile defaults UX: slider 300–7200 step 60); exposing *total* transition duration (2×) — breaks the ± semantics every existing artifact uses.

### Decision 4: Reuse the registry-lookup pattern, dedicated read helper

A `_get_runtime_ramp_width_seconds()` (or equivalent) on the switch follows `_get_runtime_range`'s structure — entity-registry lookup by `f"{entry_id}_ramp_half_width"`, state cast, fallback — but returns seconds and falls back to the constant rather than a config snapshot. `sun_light_settings` (rebuilt per tick) feeds it into `SunLightSettings.ramp_half_width_seconds`; the dataclass and curve math need **zero** changes (already parameterized). **Rejected:** generalizing `_get_runtime_range` with optional fallback/conversion params — two call patterns through one function obscures both.

### Decision 5: `_today_sun_events` uses the live width for anchoring

`anchor_sun_events(..., half_width=<live seconds>)` replaces the constant. If the curve ramps for 60 min after sunset but the anchor window is still 30, the down-ramp snaps to minimum halfway through — the exact bug class fixed on 2026-06-07. One value must flow to both consumers within a tick. Implementation note: read the width once per evaluation and pass the same number to both the curve settings and the anchor call; do not perform two independent entity reads that could race a slider write mid-tick.

### Decision 6: Naming and identity

Follows the `has_entity_name` composition requirement: `_attr_name = "Ramp half-width"`, `suggested_object_id = "ramp_half_width"`, unique_id `<entry_id>_ramp_half_width`, same device as the switches. Friendly name for profile "Dining MVP": `Dining MVP Ramp half-width`. Entity description/tooltip notes the total transition is 2× this value. **Rejected:** "Transition" naming — ambiguous against HA's per-service-call `transition` attribute, which this integration also uses.

## Risks / Trade-offs

- [Wide width on short winter days squeezes the max plateau] → capped at 120 min; at 52°N winter day length (~7.8 h) the plateau is still ≥ 3.8 h. The curve math degrades gracefully (plateau branch simply never matches) even if bounds change later.
- [Two consumers of one value drifting (curve vs anchor)] → Decision 5: single read per tick, passed to both; regression test asserts a widened ramp completes past the sensor flip.
- [NR writes a float (e.g. 42.5)] → step=1 hints the UI; read path casts via `int(float(state))` like the range reads; sub-minute precision is meaningless here.
- [Restored stale width surprises after long downtime] → acceptable; identical semantics to the four range entities, and the default is one service call away.

## Migration Plan

Additive. Existing config entries load unchanged; the new entity appears with default 30 (= prior constant) so behavior is identical until someone moves it. Minor version bump (`2.5.0-cdit.1` — new entity surface), normal HACS pre-release flow. Rollback = downgrade; the orphaned registry entry for the number is harmless and HA prunes it on next entry reload.

## Open Questions

_None — all decisions settled during the 2026-06-07 exploration._
