# Developer notes for the tests directory

The tests use [`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component)
(PHCC), which bundles a pinned Home Assistant plus its test fixtures. **No Home
Assistant `core` checkout is required** (the old clone-core + symlink + Docker
flow has been retired).

## Running the tests

From the repo root:

```bash
uv run pytest
```

`uv` builds the environment from `pyproject.toml` (the `test` dependency group
pulls in PHCC, `pytest`, and `pytest-asyncio`), and `testpaths = ["tests"]`
scopes collection to this directory. Pass pytest arguments straight through:

```bash
uv run pytest tests/test_number_platform.py -k ramp -vv
```

## What CI runs

`.github/workflows/pytest.yaml` runs the same suite on two matrix entries:

- **stable** — the latest released PHCC (current stable HA).
- **dev** — the latest PHCC pre-release (`--pre`, upcoming HA beta), marked
  `continue-on-error` so a missing or flaky pre-release never fails the build.

To reproduce a CI entry in a throwaway environment:

```bash
PYTHONPATH="$PWD" uv run --no-project \
  --with pytest-homeassistant-custom-component --with pytest \
  --with pytest-asyncio --with ulid-transform \
  pytest -q
```
