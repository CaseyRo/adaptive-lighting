## Context

Once `cdit-config-redesign` and `add-runtime-range-controls` are in, each AL profile exposes:
- 3 switches: `switch.adaptive_lighting_<name>`, `_adapt_color`, `_adapt_brightness`.
- 4 `number` entities: `_min_brightness`, `_max_brightness`, `_min_color_temp`, `_max_color_temp`.
- 2 sensor inputs (sun timing): user-configured `sunrise_entity`, `sunset_entity`.
- Internal state via the master switch's `attributes`: `current_brightness`, `current_color_temp`, `sun_position`.

These are scattered across the device page and reachable individually via dashboard cards (`entity` card, `entities` card, etc.), but no single card composes them. Users with multiple AL profiles end up either reading dense entity lists or hand-building entity-card stacks that age poorly.

The integration itself is HA-backend Python. A Lovelace card is HA-frontend code (custom element, TypeScript, runs in the browser). Different runtime, different repo conventions, different build pipeline. The card is *not* a Python module.

Home Assistant's recommended custom-card stack is **Lit** (because HA core is Lit; design tokens and helper types are first-class). Distribution is via **HACS frontend resources**: HACS reads `hacs.json`, fetches the built JS from a release, registers the URL with HA's frontend resource loader. Users install once via HACS and the card is available in the Lovelace card picker.

## Goals / Non-Goals

**Goals:**
- One card per profile that reads "at a glance" — current brightness, current K, current position on the curve, mode (if configured).
- All interactions (toggle, drag) route to HA services. No card-internal state machine.
- Visual editor so dashboard users do not edit YAML to add the card.
- Theming follows HA's surface/text variables; typography and accents are the card's own.
- HACS-installable. Optional one-toggle auto-registration when the integration is configured.
- Accessible: full keyboard reachability, ARIA labels, prefers-reduced-motion respected.
- Bundle size under 100 KB gzipped — this is a single-profile card, not an app.

**Non-Goals:**
- Multi-profile mode (one card showing N profiles in tabs/columns). Stack multiple cards in the dashboard if you need that.
- Editing the AL profile's *configuration* from the card. Configuration stays in the integration's options dialog. The card edits *runtime values* only (the 4 number entities, the 3 switches).
- A standalone web app outside HA. The card runs inside HA's dashboard; the upstream simulator at `webapp/` is a separate concern.
- Server-side rendering, SSR pre-paint, or HA Cast support — out of scope for v1.
- Theme system beyond honoring HA's CSS variables. We do not ship a theme picker.
- Localization beyond English in the first release. Strings will be externalized so other locales can be added later without code changes.

## Decisions

### Decision 1: Card is additive, not a replacement for the device page or entity cards

**What we chose:** The card consumes existing entities. The integration's device page, the individual switches, and the four `number` entities remain available and unaffected. Users who never enable the card see no difference in their setup.

**Why:** Replacement-style cards (hide all the underlying entities, surface only "the card UX") are fragile — a card bug means the user has no fallback. Keeping the underlying entities accessible means the card is a *view*, not a *driver*.

**Alternatives considered:**
- **Replace the device page with the card.** Rejected — outside our reach; HA core renders the device page.
- **Replace the four number entities with card-internal sliders.** Rejected — card state would not survive a frontend reload and would not be automatable.

### Decision 2: Stack is Lit + TypeScript + Vite

**What we chose:** `lit` for the component layer, full TypeScript including HA's `custom-card-helpers` and `home-assistant-js-websocket` types, **Vite** for the build (bundler + dev server + HMR). Single output: a bundled UMD/ESM JS file plus an inline `lovelace-card.js.map`.

**Why:**
- **Lit**: HA core is Lit; using it means the card's `<ha-*>` element usage (e.g., `<ha-switch>`, `<ha-slider>`, `<ha-icon>`) works without translation, and theming via CSS custom properties is native.
- **TypeScript**: HA's frontend types (`HomeAssistant`, `HassEntity`, `LovelaceCard`, `LovelaceCardConfig`) are well-typed; building without TS gives up that safety net for no reason.
- **Vite**: fast dev iteration (HMR against a running HA instance via the frontend dev mode), good tree-shaking, simple `vite build` produces a single bundle without manual Rollup config.

**Alternatives considered:**
- **Preact + Vite.** Rejected — Preact components do not natively render HA's `<ha-*>` elements; you would translate every interaction.
- **Vanilla custom elements (no framework).** Rejected — too much boilerplate; Lit's templating saves real time.
- **Rollup only, no Vite.** Rejected — slower dev loop; the build is no smaller.

### Decision 3: Same repo, separate build pipeline (`lovelace-card/`)

**What we chose:** New top-level directory `lovelace-card/` with its own `package.json`, `node_modules`, `vite.config.ts`, and `tsconfig.json`. The Python integration ignores this directory (already covered by `.gitignore` patterns for `node_modules`); CI gains a `lovelace-card-build` job.

**Why:** Atomic releases — when we bump the integration's version, the card builds in the same release tag. HACS reads both sections of `hacs.json` from the same repo. Splitting into a sibling repo (`cdit-works/lovelace-adaptive-lighting`) would force cross-repo version synchronization for every release.

**Alternatives considered:**
- **Sibling repo.** Rejected — release coordination overhead.
- **Built artifacts committed to git under `custom_components/adaptive_lighting/frontend/`.** Rejected — pollutes the Python package with frontend assets; HACS treats integrations and plugins as separate categories.

### Decision 4: One card = one profile (no multi-profile mode)

**What we chose:** The card config takes exactly one `entry_id` (the AL profile's config entry ID). To show N profiles, the user stacks N cards using HA's standard grid or vertical-stack layouts.

**Why:** Lovelace's composition primitives already solve multi-card layout. Building tabs/columns/grid into the card itself reimplements `stack-in-card`, `vertical-stack`, and `grid-layout`. Cards are best when they are a single coherent unit.

**Alternatives considered:**
- **`profiles: [<id1>, <id2>, ...]` with a tab strip.** Rejected — leaks responsibility into the card.

### Decision 5: Auto-discovery of related entities from the device

**What we chose:** Card config has one user-facing field: `entry` (the AL profile's config entry ID, picked from a dropdown in the visual editor). The card resolves all relevant entities at render time by:
1. Looking up the device tied to that config entry.
2. Reading all entities owned by that device.
3. Classifying them by `unique_id` suffix (`_min_brightness`, `_adapt_color`, etc.).

**Why:** Users do not hand-wire seven entity IDs per card. If we rename an entity in a future integration version, the card finds the new name automatically.

**Alternatives considered:**
- **Explicit `entities: { switch_master: ..., number_min_brightness: ..., ... }` config.** Rejected — verbose, fragile, and pushes integration internals onto the dashboard user.

### Decision 6: Honor HA theme variables, override typography and accents

**What we chose:**
- **Inherit from HA theme**: `--card-background-color`, `--primary-text-color`, `--secondary-text-color`, `--divider-color` — the card's outer surface and base text colors come from the user's chosen HA theme so the card sits naturally on any dashboard.
- **Override locally**: typography stack (display: an editorial sans-serif like *Mona Sans* or *Söhne*; body: a paired sans; numerals: tabular monospace `Söhne Mono` or `Berkeley Mono`), spacing scale, and a single accent color that follows the current color temperature output (warm for low K, neutral for ~4000 K, cool for high K).
- **Fonts loaded from a self-hosted woff2 in the bundle** so cards do not hit a third-party font CDN.

**Why:** HA themes are diverse — pure-white, pure-black, dramatic accent-color themes, etc. Inheriting structural colors means the card fits in. Overriding typography is what makes the card *the* card instead of "another HA card."

**Alternatives considered:**
- **Full custom palette ignoring HA theme.** Rejected — the card would look out of place on a user's themed dashboard.
- **Pure inheritance (no typography override).** Rejected — defeats the purpose of building a distinctive card.

### Decision 7: Curve rendered as static SVG with a single animated marker

**What we chose:** The 24-hour brightness curve is precomputed once per minute by the card from the user's `min/max_brightness` numbers and the sun-event timestamps (via the integration's exposed attributes), drawn as a single SVG `<path>`. The "you are here" marker is a small filled `<circle>` whose `cx` updates every 30 seconds via a property change.

**Why:** SVG path is cheaper than a `<canvas>` redraw, and a tiny CSS transition on the marker's `cx` is smoother than re-rendering. Curves at this scale (~150 pts) are trivial.

**Alternatives considered:**
- **Canvas-based curve.** Rejected — overkill; SVG handles this without breaking a sweat.
- **No curve, just numbers.** Rejected — the curve is the card's signature visual.

### Decision 8: Slider drags debounced 300 ms before calling `number.set_value`

**What we chose:** Each of the four range sliders tracks an internal "draft" value during drag. The HA service call (`number.set_value`) fires 300 ms after the user releases the slider (or after 300 ms of pointer-still during a continuous drag).

**Why:** Without debouncing, dragging a slider from 1% to 80% emits ~50 service calls. With debouncing, it emits 1–2. Lower bus traffic, less state churn, and the card still feels responsive because the visual position updates instantly from the draft value.

**Alternatives considered:**
- **Fire on every change event.** Rejected — wastes service calls and trips up automations watching the entity.
- **Fire only on `change` (full release).** Rejected — feels laggy when the user adjusts mid-drag.

### Decision 9: HACS frontend resource distribution, with optional integration auto-registration

**What we chose:**
- **Primary distribution**: `hacs.json` declares the card as a frontend plugin alongside the integration. HACS users install via "Frontend → Adaptive Lighting (CDiT) Card."
- **Optional auto-register**: in the integration's *global* options (Diagnostics section), a single toggle `register_card_resource` (default OFF). When the user enables it, on next setup the integration calls `lovelace.resources.async_create_item(...)` with the card's expected URL, so the user does not need to manually add a resource entry in Lovelace.
- **Resource URL**: `/hacsfiles/adaptive-lighting/cdit-adaptive-lighting-card.js` — matches HACS's standard file serving path.

**Why:** HACS users get a one-click install. Power users who do not use HACS or who keep frontend resources Strictly Managed™ can leave auto-register off and add the resource themselves. The toggle is off by default because silently registering frontend resources during a backend install crosses a layer the user might not expect.

**Alternatives considered:**
- **Always auto-register.** Rejected — too magical; the integration touching `lovelace.resources` without permission feels invasive.
- **Never auto-register, document only.** Rejected — the manual-add path is a known HACS UX wart; if we can save the click, we should.

### Decision 10: Visual direction is "editorial-instrument"

**What we chose:** A specific aesthetic point of view, not a stack of generic UI primitives:

```
Layout idea (one card, ~360 wide):

┌──────────────────────────────────────────────────────┐
│  KITCHEN                                             │   ← profile name, small caps display font
│  ──────                                              │   ← thin rule, theme-divider color
│                                                      │
│       72 %    ·    3 240 K                           │   ← hero numerals, tabular mono, ~28pt
│       brightness   color temperature                 │   ← micro caption, body sans, ~11pt
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │                                                │  │
│  │                ╭───────────────╮               │  │
│  │              ╱       ●         ╲              │  │   ← static SVG curve; only the
│  │            ╱        you-are                    ╲    ●now dot moves
│  │         ──╯           here                       ╰── │
│  │  04:51                                      19:34 │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  Adaptive ●     Color ●     Brightness ●            │   ← switches as toggles
│                                                      │
│  ── 5 % ──────────────────────────── 90 % ──         │   ← double-ended sliders
│  ── 2 200 K ──────────────────────── 4 800 K ──      │
│                                                      │
│  House mode: Day  →  full adaptive                   │   ← optional, shown only if house-mode-modes configured
└──────────────────────────────────────────────────────┘
```

**Why:** Calm typography + a single curve + restrained color is more "instrument panel" than "dashboard widget" — the card communicates *what the lights are doing*, not *what knobs you can turn*. The card itself shifts subtly in tone with the current color temperature (background tint warms after sunset, cools mid-day), which makes the dashboard feel alive without animation noise.

**Alternatives considered:**
- **Skeuomorphic dimmer/dial UI.** Rejected — feels gimmicky after the first day.
- **Pure data card (numbers in a grid, no curve).** Rejected — loses the "at a glance" property; the curve is the differentiator.
- **Card-shifts-color too aggressively (full background = current K).** Rejected — fights the user's chosen dashboard theme; subtle accent tint only.

## Risks / Trade-offs

- **[Lit + Vite + npm in a Python repo]** → Adds a JS toolchain to the repo. Anyone working on the integration without touching the card can ignore it (no Python dependency on `lovelace-card/`), but CI gains a parallel build job. Mitigation: dedicated `lovelace-card-build` workflow, isolated from the integration's test workflow.
- **[HA frontend API breaking changes]** → HA frontend has historically broken minor APIs (especially around `LovelaceCard` lifecycle). Mitigation: pin `home-assistant-js-websocket` and `custom-card-helpers` to known-good versions; the card declares its minimum HA version (matches the integration's, pinned to 2025.1+).
- **[`<ha-slider>` and `<ha-switch>` internals]** → We use HA's built-in elements, which means we are coupled to whatever HA ships. Mitigation: if HA renames or restyles one of these, the card breaks visually but not behaviorally — failure mode is cosmetic and recoverable.
- **[Bundle size]** → Lit + helpers is ~30 KB gzipped baseline. Plus our code. Plus fonts. Mitigation: keep one display font and one body font; subset to the glyphs we use; lazy-load nothing because there is only one screen.
- **[Resource auto-registration races with HACS install]** → If the user enables auto-register before the card file exists at the URL, HA logs a 404 every time it tries to load Lovelace resources. Mitigation: integration writes the resource only when the card file is present on disk (check via the static path); document the order (install card via HACS first, then enable auto-register).
- **[Accessibility for the curve]** → A pretty SVG curve is not screen-reader-accessible without explicit `aria-label` text describing current values. Mitigation: a visually hidden `<div aria-live="polite">` mirrors the hero numerals; the curve gets `role="img"` with an accessible name like "Brightness curve, currently 72% at 3240 K."
- **[Long-press disambiguation on mobile]** → Long-press to open more-info conflicts with HA's standard tap behavior. Mitigation: follow HA's `action-handler` convention exactly; let the dashboard's tap/hold/double-tap actions config override card defaults.

## Migration Plan

- **Install order**: this change is a net-new resource. No migration of existing data.
- **First-time install (HACS path)**:
  1. User installs the CDiT integration via HACS as normal.
  2. User installs the "Adaptive Lighting (CDiT) Card" frontend resource via HACS.
  3. User adds a card to a dashboard; the visual editor lets them pick an AL profile.
- **First-time install (no HACS, manual)**:
  1. Copy `dist/cdit-adaptive-lighting-card.js` from the release tarball into `<HA config>/www/`.
  2. Add a resource entry: `url: /local/cdit-adaptive-lighting-card.js, type: module`.
  3. Restart frontend, add card to dashboard.
- **Optional auto-register flow**:
  1. After HACS install, user opens the integration's global options.
  2. Enables `register_card_resource` toggle in Diagnostics.
  3. On next reload, the integration writes the resource entry. User no longer manages it manually.

**Rollback:** Remove the card from any dashboards using it; uninstall via HACS (or delete from `www/`). The integration and all entities remain functional — the card is purely additive.

## Open Questions

- **Font choice**: Mona Sans + tabular Mona Sans Mono, or Söhne + Söhne Mono, or a freer choice (Inter Display + JetBrains Mono)? Söhne is licensed; Mona Sans is open. Lean Mona Sans for license cleanness in an open-source plugin.
- **Curve refresh cadence**: 30 seconds (smooth-feeling) vs 60 seconds (cheaper). At 30 s the marker glides; at 60 s it ticks. Lean 30 s.
- **Card width breakpoints**: at ~360 px the layout above works. At narrower (mobile column dashboards, ~280 px), the curve gets short. Drop the time labels under the curve? Or scale down the hero numerals? Lean: drop time labels at ≤300 px width.
- **Bundle distribution**: ship one combined bundle (~80 KB) or split into `card.js` + `editor.js` so the editor only loads in dashboard-edit mode (~50 KB + 30 KB)? Lean split — the editor lazy-loads behind dashboard-edit-mode anyway.
- **Should the card show forecast** (where the curve will be in N hours) on hover? Could be a nice "I am thinking about my house" gesture. Lean: defer to v1.1.
- **House-mode badge interaction**: tap to cycle the source `input_select`? Or read-only? Lean read-only for v1 — cycling modes is a house-wide concern, not a per-profile one.
