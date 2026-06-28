# SST Test Suite

The SST tests are intentionally split into tiers. The core suite should test
only FUSE core behavior. Plugin behavior runs only after core passes. SST then
has an additional split between deterministic plugin tests, deterministic
external/custom-component fixture tests, and live tests against real SST
installations.

## Recommended local commands

From the repository root:

```bash
make test-core
make test-plugins
make test-sst-external-fixtures
```

The one-shot deterministic command is still available when you do not need to
inspect the tiers separately:

```bash
make test-fast
```

Equivalent direct pytest commands:

```bash
# Tier 1: core only
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m pytest -q fuse/tests

# Tier 2: deterministic plugin tests, excluding SST external fixtures and live checks
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m pytest -q fuse/plugins/community/sst/tests \
  -m "not sst_live and not sst_remote and not sst_ext and not sst_external and not slow"

PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m pytest -q fuse/plugins/community/gem5/tests \
  -m "not gem5_live and not slow"

# Tier 3: deterministic SST external/custom component fixture tests
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m pytest -q fuse/plugins/community/sst/tests \
  -m "sst_external and not sst_live and not sst_remote and not sst_ext and not slow"
```

The same named suites are also available through the Python runner:

```bash
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m fuse.tools.run_tests --list
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m fuse.tools.run_tests core
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m fuse.tools.run_tests plugins
PYTHONPATH="$PWD" ./fuse/.venv/bin/python -m fuse.tools.run_tests sst-external-fixtures
```

## Suite layers

| Layer | Command | Requires | Purpose |
| --- | --- | --- | --- |
| Core | `make test-core` | Python dependencies only | Core FUSE behavior; no plugin test directories |
| Plugin deterministic | `make test-plugins` | Python dependencies and Qt test deps | SST and gem5 plugin-owned behavior, excluding live/external acceptance |
| SST deterministic | `make test-sst-fast` | Python dependencies and Qt test deps | SST plugin tests excluding live, remote, external fixture, and slow tests |
| gem5 deterministic | `make test-gem5-fast` | Python dependencies and Qt test deps | gem5 plugin tests excluding live and slow tests |
| SST external fixtures | `make test-sst-external-fixtures` | Python dependencies only | Deterministic external/custom SST behavior using fixture metadata |
| Full local SST directory | `make test-sst-full` | PySide6; live tests skip if unavailable | Everything under the SST test directory |
| Live SST | `make test-sst-live` | Working `sst` and `sst-info` | Real SST install tests, normally SST 15.1.2 or 16.0.0 |
| SST external live | `make test-sst-external-live` | `sst-ext-tests` CI image/config | External acceptance environment checks |
| Remote SST | `make test-sst-remote` | SSH/remote SST test configuration | Remote toolchain checks |
| Core coverage | `make test-coverage-core` | `pytest-cov` | Core/app coverage |
| Plugin coverage | `make test-coverage-plugins` | `pytest-cov` | SST/gem5 plugin coverage |

## CI tiers

The deterministic GitHub Actions workflow follows the same order:

1. **Tier 1 / Core tests only** runs `tests`.
2. **Tier 2 / Plugin deterministic tests** runs SST and gem5 plugin tests only
   if Tier 1 passes.
3. **Tier 3 / SST external fixture tests** runs deterministic external/custom
   SST fixture tests only if the plugin tier passes.

Live simulator checks are intentionally separate workflows:

- `sst-integration.yml` runs `sst_live` against real SST 15.1.2 and 16.0.0
  container images. Version-specific slices are available with
  `make test-sst-live-15`, `make test-sst-live-16`,
  `python -m fuse.tools.run_tests sst-live-15`, and
  `python -m fuse.tools.run_tests sst-live-16`.
- `sst-external-validation.yml` runs `sst_ext` in the external validation
  environment.
- `gem5-integration.yml` runs `gem5_live` against real gem5 container images.

## Pytest markers

The important plugin-related markers are:

- `sst`: deterministic SST plugin tests.
- `sst_external`: deterministic external/custom SST behavior using fixtures.
- `sst_live`: requires real SST Core/SST Elements and working `sst-info`/`sst`.
- `sst_ext`: optional external validation environment checks.
- `sst_remote`: requires configured SSH/remote SST test environment.
- `gem5_live`: requires a real gem5 installation or gem5-capable container.
- `qt`: requires Qt/PySide6.
- `slow`: longer integration tests.
- `golden`: semantic/golden export regression tests.
- `sst_15` / `sst_16`: live tests requiring a specific SST major version.

Every test that depends on a local simulator installation, external validation
image, remote SSH endpoint, or long-running workflow must use one of these
markers so the deterministic CI tier stays dependency-light.

## Helper modules

- `catalog_test_helpers.py` builds deterministic SST component catalogs and
  synthetic `sst-info` output.
- `scene_test_helpers.py` builds in-memory scenes for export/runtime tests.
- `fake_toolchains.py` builds local/SSH toolchain settings without running real
  commands.

Fixture `sst-info` files live under `fixtures/sst-info/`.

## Coverage focus

The most important SST modules for coverage are:

- `fuse.plugins.community.sst.get_sstinfo`
- `fuse.plugins.community.sst.component_catalog`
- `fuse.plugins.community.sst.export_json`
- `fuse.plugins.community.sst.policy.runtime`
- `fuse.plugins.community.sst.plugin`

## Plugin-local generated SST catalog snapshots

Toolchain-discovered SST component catalog snapshots are generated under
`fuse/plugins/community/sst/component_catalogs/toolchains/`. They are SST
plugin runtime metadata, not core application data, and should not be committed
except for the `.gitignore` guardrail in that directory.
