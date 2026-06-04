# Environment Variables

## `FUSE_DB_PATH`

Overrides the SQLite database path.

Example:

```bash
FUSE_DB_PATH=/tmp/fuse-test.db .venv/bin/python -m pytest -q
```

Used heavily by tests to avoid touching the developer database.

## `FUSE_SST_VERSION`

Selects the SST version label used during SST metadata import/bootstrap.

Example:

```bash
FUSE_SST_VERSION=15.1.2 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
FUSE_SST_VERSION=16.0.0 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

This does not install SST. It labels/imports metadata from the currently configured/reachable SST environment.

## `FUSE_REFRESH_SSTINFO`

Forces the SST plugin to rerun `sst-info` even if a successful run already exists.

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```


## `FUSE_ENABLE_SST_EXT_TESTS`

Enables backend-only SST plugin external validation stages that require real SST tooling.

```bash
FUSE_ENABLE_SST_EXT_TESTS=1 QT_QPA_PLATFORM=offscreen \
  .venv/bin/python -m pytest -q -m "sst_ext"
```

When unset, SST plugin external-validation tests still exercise fixture export and JSON checks, but real SST init/runtime stages are skipped.

## `SST_EXT_TESTS_ROOT`

Optional path to a local `sst-ext-tests` checkout for developer diagnostics/interoperability. FUSE does not vendor or require this repository for normal tests.

```bash
SST_EXT_TESTS_ROOT=/path/to/sst-ext-tests \
  FUSE_ENABLE_SST_EXT_TESTS=1 \
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -m "sst_ext"
```

## `FUSE_SPLASH_MS`

Controls minimum splash screen duration in milliseconds.

Useful in tests:

```bash
FUSE_SPLASH_MS=0 .venv/bin/python -m fuse.app.main
```

## `FUSE_TEST_AUTOCLOSE_MS`

Tells the app to quit automatically after startup. Used by launch/shutdown tests.

```bash
FUSE_TEST_AUTOCLOSE_MS=250 .venv/bin/python -m fuse.app.main
```

## `QT_QPA_PLATFORM`

Controls Qt platform backend.

For headless CI:

```bash
QT_QPA_PLATFORM=offscreen
```

Alternative:

```bash
QT_QPA_PLATFORM=xcb xvfb-run -a .venv/bin/python -m pytest -q
```

## `FUSE_GEM5_VERSION`

Version label used by gem5 live tests and CI matrices.

Example:

```bash
FUSE_GEM5_VERSION=25.1.0.1 .venv/bin/python -m pytest -q -m "gem5_live"
```

## `GEM5_ROOT`

Path to gem5 checkout or installation root.

## `GEM5_BINARY`

Path to a gem5 executable such as:

```text
/opt/gem5/build/X86/gem5.opt
```
