## Why

The count of `number` entities per profile is inconsistent across the Adaptive Lighting docs. The integration exposes **five** live-tunable `number` entities per profile — the four range bounds (`min_brightness`, `max_brightness`, `min_color_temp`, `max_color_temp`) plus `ramp_half_width` — as stated in the README reference table ("Number entities (5)") and intro ("five live-tunable sliders"), and as required by the `runtime-range-controls` spec ("exposes five runtime curve entities"). But two doc locations still say four: the README's top callout block ("four live-tunable sliders", listing only the four range entities) and the `CHANGELOG.md` `2.1.0-cdit.1` "Added" entry, which introduced the original four and was never followed by an entry recording the fifth (`ramp_half_width`). A reader gets contradictory counts inside the same README.

## What Changes

- **README**: update the top callout block (the "four live-tunable sliders" section) to list all five entities, adding `number.<profile>_ramp_half_width`, so it matches the reference table and intro further down the same file.
- **CHANGELOG**: add an entry under the appropriate unreleased version documenting the `ramp_half_width` number entity as the fifth live-tunable slider. Leave the historical `2.1.0-cdit.1` "four" entry intact — it accurately records the release that introduced the first four; the gap is the missing later entry, not a wrong historical one.
- No source change: the implementation already creates five entities.
- No spec change: `runtime-range-controls` already specifies five (its "four range entities" wording refers to the range subset, distinct from the ramp control).

## Capabilities

### New Capabilities

None. Documentation-only correction.

### Modified Capabilities

None. `runtime-range-controls` already reflects five entities; behavior is unchanged.

## Impact

- `Adaptive_lighting/README.md` (top callout block) and `Adaptive_lighting/CHANGELOG.md` (one added entry). No source or spec files change.
