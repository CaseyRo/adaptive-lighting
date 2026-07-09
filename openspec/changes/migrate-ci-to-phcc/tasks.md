# Tasks

## 1. Rewrite the pytest workflow (PHCC, latest + dev)

- [x] 1.1 Verify the install+test recipe in a clean env locally first (fresh venv, latest PHCC, repo on PYTHONPATH → green)
- [x] 1.2 Replace `.github/workflows/pytest.yaml`: trigger on `push` (main) + `pull_request`; `fail-fast: false`; two-entry matrix — `stable` (latest PHCC) and `dev` (`--pre` PHCC, `continue-on-error: true`)
- [x] 1.3 Steps: checkout → setup Python → `uv venv` → `uv pip install ${PRE} pytest-homeassistant-custom-component pytest pytest-asyncio ulid-transform` → `pytest --cov=custom_components.adaptive_lighting --cov-report=xml`
- [x] 1.4 Set `PYTHONPATH` (or install the package) so `custom_components.adaptive_lighting` imports

## 2. Retire the core-checkout scaffolding

- [x] 2.1 Delete `.github/workflows/install_dependencies/` (composite action)
- [x] 2.2 Delete `.github/workflows/update-test-matrix.yaml` and `scripts/update-test-matrix.py`
- [x] 2.3 Delete `scripts/setup-dependencies` and `scripts/setup-symlinks`
- [x] 2.4 Delete `test_dependencies.py`
- [x] 2.5 Delete `Dockerfile` and `.github/workflows/docker-build.yml`
- [x] 2.6 Grep the repo to confirm no remaining references to any deleted file

## 3. Update dev tooling + docs to the PHCC flow

- [x] 3.1 Update `scripts/setup-devcontainer` to the PHCC flow (drop core clone/symlinks; install the test deps)
- [x] 3.2 Rewrite `tests/README.md` for `uv run pytest` (remove core-clone / symlink / Docker instructions)
- [x] 3.3 Update `CLAUDE.md`: drop the "Refresh test matrix" row; point testing at `uv run pytest`
- [x] 3.4 Fix the declared minimum: `hacs.json` `homeassistant` → recent (`2026.1.0`); README line 66 → correct version and drop the false "pinned in `manifest.json`"

## 4. Verify

- [x] 4.1 `uv run pytest` still green locally (164)
- [x] 4.2 Lint the new workflow YAML (actionlint if available; else careful review)
- [x] 4.3 Push; confirm the new pytest matrix goes green and Docker / update-test-matrix no longer run (CI: pytest stable+dev green in ~30s; Docker/update-test-matrix removed)
