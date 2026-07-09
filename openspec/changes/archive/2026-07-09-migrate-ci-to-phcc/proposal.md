## Why

The `pytest` and `Docker` CI workflows fail on every run. Root cause: the test suite was migrated to `pytest-homeassistant-custom-component` (PHCC) — declared in `pyproject.toml`'s `test` dependency group, with `testpaths = ["tests"]`, and it passes locally (164 passed in ~1.4s). But CI still runs the inherited upstream (basnijholt) harness: `pytest.yaml` plus the `.github/workflows/install_dependencies` composite action check out `home-assistant/core` into `core/`, symlink the component and its tests into core, install core's own test requirements, and run the tests from `core/tests/components/adaptive_lighting`. That environment never installs PHCC, so collection fails with `ModuleNotFoundError: No module named 'pytest_homeassistant_custom_component'` across all 18 matrix entries. The `Docker` workflow builds the same core-checkout image and dies earlier, on `FileNotFoundError: core/requirements_test_all.txt` (HA `dev` reorganized its test-requirements files).

The two harnesses are mutually incompatible and the repo has one foot in each. Local development already uses PHCC; CI should too.

## What Changes

- Rewrite `.github/workflows/pytest.yaml` to run the local `tests/` suite with PHCC: check out the repo, set up Python + uv, install the component runtime deps plus the `test` dependency group, run `pytest` (which resolves `testpaths = ["tests"]`). No `home-assistant/core` checkout, no symlinks.
- Replace the 18-entry `core-version` matrix with a PHCC-version matrix (each pinned PHCC release targets one HA release). Concrete version set is decided in `design.md`.
- Retire the scaffolding that only serves the dead harness — candidate set (final keep/drop decided in `design.md`): `.github/workflows/install_dependencies/`, `scripts/setup-dependencies`, `scripts/setup-symlinks`, `scripts/update-test-matrix.py`, `.github/workflows/update-test-matrix.yaml`, the `Dockerfile`, and `.github/workflows/docker-build.yml`.
- Update `tests/README.md` (and the `Dockerfile` header, if kept) which document the old core-checkout flow.

## Capabilities

### New Capabilities

None. This is CI and test-infrastructure only; no runtime behavior or spec requirement changes.

### Modified Capabilities

None. The tests themselves are unchanged; they already pass under PHCC. (Expect `openspec validate` to report "no deltas" — correct for an infra-only change.)

## Impact

- CI workflows: `pytest.yaml`, `install_dependencies/action.yml`, `docker-build.yml`, `update-test-matrix.yaml`.
- Build / scripts: `Dockerfile`, `scripts/setup-dependencies`, `scripts/setup-symlinks`, `scripts/update-test-matrix.py`.
- Docs: `tests/README.md`.
- No changes under `custom_components/adaptive_lighting/`. No changes to test files.
- Trade-off: CI exercises fewer HA versions than the old 18-entry matrix. The coverage strategy and its rationale are in `design.md`.
