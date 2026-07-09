## Context

The repository ships a Home Assistant custom integration and tests it two incompatible ways at once:

- **Local / current source of truth — PHCC.** `pyproject.toml` declares a `test` dependency group (`pytest`, `pytest-asyncio`, `pytest-homeassistant-custom-component`), `testpaths = ["tests"]`, `asyncio_mode = "auto"`. `uv run pytest` passes **164 tests in ~1.4s**. PHCC bundles a pinned Home Assistant and provides the `hass` fixtures and `enable_custom_integrations`, so no HA source checkout is needed.
- **CI — the inherited upstream (basnijholt) core-checkout harness.** `pytest.yaml` runs an 18-entry `core-version` matrix; the `install_dependencies` composite action checks out `home-assistant/core` into `core/`, runs `scripts/setup-dependencies` (installs core's `requirements_test*.txt`) and `scripts/setup-symlinks` (links the component + tests into core), then runs `cd core && pytest tests/components/adaptive_lighting`. The `Docker` workflow builds a `Dockerfile` that does the same clone-core dance and ships a test-runner image to ghcr.

Both CI paths fail on every run:
- `pytest`: the tests `import pytest_homeassistant_custom_component`, but the core-checkout env never installs PHCC → `ModuleNotFoundError` at collection, all 18 entries.
- `Docker`: `scripts/setup-dependencies` / `test_dependencies.py` read `core/requirements_test_all.txt`, which HA `dev` reorganized → `FileNotFoundError`.

The two harnesses cannot coexist: PHCC provides its own HA test scaffolding, so running PHCC-based tests inside a real core checkout is not a supported PHCC mode. The migration to PHCC is already done for the tests; only CI and its scaffolding were left behind.

Cross-references that the retirement must also touch: `tests/README.md`, `CLAUDE.md` (the "Refresh test matrix" row), and `scripts/setup-devcontainer` all document or drive the core-checkout flow.

## Goals / Non-Goals

**Goals:**
- Make `pytest` CI run the exact suite that passes locally (PHCC), and go green.
- Make `Docker` CI stop failing (by retiring the test image it builds, unless there is a reason to keep it).
- Remove the dead core-checkout scaffolding so the repo has one coherent test story.
- Preserve meaningful multi-HA-version coverage at low maintenance cost.

**Non-Goals:**
- No changes to `custom_components/adaptive_lighting/` runtime code.
- No changes to the test files themselves (they already pass under PHCC).
- No new spec/capability behavior (infra-only; `openspec validate` will report "no deltas", which is expected).
- Not fixing the pre-existing `pre-commit`/`TOC` failures — handled separately in PR #2.

## Decisions

### D1. Run the local `tests/` suite with PHCC in CI; drop the core checkout
CI installs the `test` dependency group + the component's manifest requirements (`ulid-transform`) and runs `pytest` (resolving `testpaths = ["tests"]`). No `home-assistant/core` checkout, no symlinks.
- **Why:** it is exactly what passes locally; PHCC is the maintained, standard way to test HA custom components; it removes a whole class of breakage (tracking core's moving `requirements_test*` layout, as the Docker failure shows).
- **Alternatives considered:**
  - *Keep the core checkout and also install PHCC into it* — rejected: PHCC and core's native `tests/` framework provide competing `hass`/`enable_custom_integrations` fixtures; this is not a supported PHCC configuration and would be fragile.
  - *Revert the tests to core-native (remove PHCC)* — rejected: undoes the completed migration, a large rewrite, against the repo's current direction.

### D2. Replace the 18-version `core-version` matrix with a small curated PHCC-version matrix
Each PHCC release pins one HA version, so the matrix becomes a list of pinned PHCC versions. Proposed set: **minimum supported HA** (hacs.json floor, currently `2024.12`) and **latest stable**, optionally **HA `dev`/newest** as a non-blocking entry.
- **Why:** adjacent patch releases in the old 18-entry matrix rarely diverge; min + latest catches the real breakage (a floor-version API removal, a latest-version deprecation) at a fraction of the maintenance and CI minutes.
- **Alternatives considered:**
  - *Single latest-only entry* — rejected: loses floor-version regressions, which are the ones users on older HA actually hit.
  - *Map all ~18 HA releases to PHCC versions* — rejected: high maintenance, defeats the simplification; PHCC pins would need constant bumping.
- **Consequence:** `scripts/update-test-matrix.py` + `update-test-matrix.yaml` (which auto-generated the core-version matrix) are retired in favour of a hand-maintained 2-3 entry matrix a human bumps occasionally.

### D3. Retire the Docker test image (`Dockerfile` + `docker-build.yml`)
- **Why:** the image exists only to run the core-checkout tests in a container; the integration is distributed via HACS, not as a Docker image, so nothing consumes the ghcr artifact. With PHCC, `pytest` runs directly in the CI runner.
- **Alternative considered:** repurpose `Dockerfile` as a PHCC local-test container — rejected as low value (`uv run pytest` locally is already trivial), but see Open Question OQ3.

### D4. Delete the scaffolding that only serves the dead harness
Delete: `.github/workflows/install_dependencies/`, `scripts/setup-dependencies`, `scripts/setup-symlinks`, `scripts/update-test-matrix.py`, `.github/workflows/update-test-matrix.yaml`, `test_dependencies.py`, and (per D3) `Dockerfile` + `docker-build.yml`. Keep `scripts/develop`, `scripts/lint`.
- **Why:** each of these is reachable only from the core-checkout flow; leaving them invites future confusion.
- **Note:** `scripts/setup-devcontainer` also clones core / symlinks; it must be updated to the PHCC flow (`uv sync` + the `test` group) rather than deleted, since the devcontainer still needs a working local test setup.

### D5. Coverage target namespace changes
Old CI measured `--cov=homeassistant.components.adaptive_lighting` (the symlinked-into-core namespace). New CI measures `--cov=custom_components.adaptive_lighting`.

### D6. Docs follow the change
Rewrite `tests/README.md` to the PHCC flow (`uv run pytest`), drop the "Refresh test matrix" row from `CLAUDE.md`, and update the `Dockerfile` header comment (or remove it with the file).

## Risks / Trade-offs

- **Reduced HA-version coverage (18 → 2-3)** → curated min + latest (+ dev) catches the breakage that matters; the matrix is trivially expandable if a regression ever slips through a gap.
- **PHCC lags the newest HA for a short window after each HA release** → make the `dev`/newest entry `continue-on-error: true` (or omit it) so a missing PHCC pin does not redden the suite.
- **Wrong PHCC↔HA pin** → fails loudly at `uv pip install`; the mapping is documented in `tasks.md` and easy to correct.
- **Deleting the ghcr test image could surprise a consumer** → verify nothing pulls `ghcr.io/CaseyRo/adaptive-lighting` (it is a test image; HACS install does not use it) before deleting; rollback is a revert.
- **Manifest requirements beyond `ulid-transform`** → manifest lists only `ulid-transform`; PHCC pulls HA itself. If a future runtime dep is added, the CI install step must include it (or install the package via `pip install -e .`).

## Migration Plan

1. Add the new `pytest.yaml` (PHCC install + curated matrix, `--cov=custom_components.adaptive_lighting`).
2. Delete the D4 scaffolding; update `scripts/setup-devcontainer` to the PHCC flow.
3. Update `tests/README.md`, `CLAUDE.md`, `Dockerfile` header (or remove with D3).
4. Push the branch; confirm the new `pytest` matrix is green and `Docker`/`update-test-matrix` no longer run (removed).
5. Merge. **Rollback:** revert the PR — restores the old harness verbatim.

## Open Questions

1. **OQ1 — Matrix breadth:** min + latest (2 entries), or min + latest + `dev` non-blocking (3)? *(Recommend: min + latest + dev-non-blocking.)*
2. **OQ2 — Delete the Docker test image + `docker-build.yml` outright?** *(Recommend: yes.)*
3. **OQ3 — Keep `Dockerfile` repurposed as an optional PHCC local-test container, or delete it?** *(Recommend: delete.)*
4. **OQ4 — Exact minimum HA version to pin.** hacs.json floor is `2024.12`; confirm that is still the supported floor, and that a matching PHCC release exists to pin against.
