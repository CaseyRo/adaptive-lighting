# Tasks

## 1. Reconcile the number-entity count across the docs

- [x] 1.1 In `README.md`, update the top callout block that says "four live-tunable sliders" to list all five entities, adding `number.<profile>_ramp_half_width`
- [x] 1.2 In `CHANGELOG.md`, add an entry under the current unreleased version documenting the `ramp_half_width` number entity as the fifth live-tunable slider; leave the historical `2.1.0-cdit.1` "four" entry unchanged
- [x] 1.3 Verify the README intro ("five live-tunable sliders") and the reference table ("Number entities (5)") now agree with the corrected callout
- [x] 1.4 Grep the repo for other stale "four ... number"/"four ... slider" doc references and fix any stragglers
- [x] 1.5 Leave source and the `runtime-range-controls` spec untouched (both already reflect five entities)
