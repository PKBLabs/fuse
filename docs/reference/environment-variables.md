# Environment Variables

## `FUSE_DB_PATH`

Overrides the SQLite database path.

Example:

```bash
FUSE_DB_PATH=/tmp/fuse-test.db .venv/bin/python -m pytest -q
```

Used heavily by tests to avoid touching the developer database.

## `FUSE_REFRESH_SSTINFO`

Forces the SST plugin to rerun `sst-info` even if a successful run already exists.

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
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

## `GEM5_ROOT`

Path to gem5 checkout or installation root.

## `GEM5_BINARY`

Path to a gem5 executable such as:

```text
/opt/gem5/build/X86/gem5.opt
```
