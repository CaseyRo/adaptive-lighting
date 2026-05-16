# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A CDiT fork of [basnijholt/adaptive-lighting](https://github.com/basnijholt/adaptive-lighting) — a Home Assistant custom component that adjusts light brightness and color temperature in sync with the sun curve. The fork is opinionated about CDiT's single-household setup and explicitly diverges from upstream on the integration's configuration surface.

**Fork is not a drop-in replacement.** Existing upstream config entries will fail to load (deliberate, see `openspec/changes/cdit-config-redesign/design.md` decision 4).

## Remote topology

```
origin    git@github.com:CaseyRo/adaptive-lighting.git   (the fork, read-write)
upstream  https://github.com/basnijholt/adaptive-lighting.git   (read-only)
```

Sync upstream changes:

```bash
git fetch upstream
git merge upstream/main         # or rebase, depending on local policy
# resolve conflicts under custom_components/adaptive_lighting/
```

## Commands

Python tooling is `uv` (not `pip` or `poetry`). All commands assume an activated venv from `./scripts/setup-devcontainer`.

| Task | Command |
|---|---|
| Run the test suite | `uv run pytest` |
| Run a single test | `uv run pytest tests/test_config_flow.py::test_options_flow_init` |
| Lint everything (pre-commit) | `./scripts/lint` |
| Run HA locally with the custom component loaded | `./scripts/develop` (boots HA on `localhost:8123` from `./config/`) |
| Update generated docs/content in README | `./scripts/update-generated-content` |
| Refresh test matrix | `./scripts/update-test-matrix.py` |

Ruff config lives in `.ruff.toml`. Pre-commit hooks in `.pre-commit-config.yaml`. Both enforce on push via `./scripts/lint`.

## Architecture

This is a standard Home Assistant **custom component** packaged under `custom_components/adaptive_lighting/`. HA loads it by directory name when present in a HA config's `custom_components/`. The HACS integration provides distribution.

Big-picture layout:

```
custom_components/adaptive_lighting/
├── __init__.py             entry point: async_setup_entry, async_unload_entry,
│                           and the curve math (sun-position + brightness/CT calc)
├── config_flow.py          UI flow for setup and reconfiguration. Iterates
│                           VALIDATION_TUPLES from const.py to build the schema.
├── switch.py               the 4 switch entities per AL config (master, sleep,
│                           adapt_color, adapt_brightness). After
│                           cdit-config-redesign lands: 3 switches (no sleep).
├── const.py                CONF_/DEFAULT_ constants + VALIDATION_TUPLES — the
│                           single source for what fields exist in the schema.
├── color_and_brightness.py pure math: tanh, sun-elevation curve, color-temp
│                           interpolation.
├── adaptation_utils.py     per-light service-call shaping (intercept,
│                           skip_redundant_commands, split commands, etc.)
├── hass_utils.py           HA-specific helpers (entity registry lookups,
│                           timestamps, service-call dispatch).
├── manifest.json           integration metadata; `version` here gates
│                           the strict break in cdit-config-redesign.
└── strings.json            UI labels for the config flow, errors, abort reasons.
```

The CDiT fork is also planning two follow-on changes that layer cleanly on top:
- `add-runtime-range-controls` — adds a `number` platform with live entities for the 4 brightness/CT ranges.
- `house-mode-modes` — adds an `input_select`-driven behavior matrix that drives the 3 runtime switches on house-mode change.

Neither is implemented yet; both have proposal stubs in `openspec/changes/`.

## Planning workflow — OpenSpec under `opsx`

All non-trivial changes go through OpenSpec before code lands. The experimental `opsx` schema (artifact-driven: proposal → design → specs → tasks) is configured. Drive it via `.claude/commands/opsx/*` slash commands or the `openspec-*` skills.

```
openspec/
├── config.yaml             (project context lives here once filled in)
├── specs/                  long-lived capability specs (empty until a change archives)
└── changes/
    ├── cdit-config-redesign/         active, 4/4 artifacts, strict-validate green
    │   ├── proposal.md     why + what changes + capabilities + impact
    │   ├── design.md       15 decisions with rejected alternatives, risks, migration
    │   ├── specs/options-flow/spec.md   9 requirements, 22 Given/When/Then scenarios
    │   └── tasks.md        9 task groups, 36 checkboxes with [R, D] annotations
    ├── add-runtime-range-controls/   stub, proposal only
    └── house-mode-modes/             stub, proposal only
```

Validate any active change with:

```bash
openspec validate <change-name> --strict
```

When implementing tasks for an active change, prefer `/opsx:apply <change-name>` over manual edits — it walks `tasks.md` checkbox by checkbox. `/opsx:verify` checks the resulting code against the spec's scenarios before archive.

## Conventions worth preserving

- **Change names**: kebab-case (e.g., `cdit-config-redesign`, `add-runtime-range-controls`).
- **Capability slugs**: kebab-case, scoped tight (`options-flow`, `runtime-range-controls`, `house-mode-binding`) — not broad umbrellas.
- **Annotations in `tasks.md`**: each task ends with `[R…, D…]` referencing requirements in the change's spec delta and decisions in `design.md`. Keep traceability.
- **No silent migrations**: CDiT-fork breaking changes bump `manifest.json` major and reject incompatible config entries with a clear error (see `cdit-config-redesign` design decision 4).
- **`openspec/config.yaml` `context:` field**: still unset. Fill in once CDiT tech-stack conventions stabilize — it propagates into every artifact prompt.
