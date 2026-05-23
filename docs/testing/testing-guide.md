# Testing Guide

FUSE uses `pytest` and `pytest-qt`.

## Test layout

```text
fuse/tests/                         Core/app tests
fuse/plugins/community/sst/tests/   SST plugin tests
fuse/plugins/community/gem5/tests/  gem5 plugin tests
```

SST-specific tests belong in the SST plugin. gem5-specific tests belong in the gem5 plugin.

## Running tests

Run all tests:

```bash
.venv/bin/python -m pytest -q
```

Run dependency-light tests:

```bash
.venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```

Run SST live tests:

```bash
.venv/bin/python -m pytest -q -m "sst_live"
```

Run gem5 live tests:

```bash
.venv/bin/python -m pytest -q -m "gem5_live"
```

## Markers

```text
sst_live    Requires real SST Core/SST Elements and working sst-info.
gem5_live   Requires a real gem5 binary.
slow        Slower integration tests.
```

## Headless Qt

For local headless testing:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

If `offscreen` fails:

```bash
xvfb-run -a .venv/bin/python -m pytest -q
```

## Isolated database

Tests should set `FUSE_DB_PATH` to a temporary SQLite database. The root `conftest.py` should provide this automatically.

## What to test in core

Core/app tests should cover:

- Application launch/shutdown.
- Main window construction.
- Plugin discovery.
- Database initialization.
- Project save/load.
- Routing.
- Validation.
- Component palette.
- Properties panel.
- Splash screen.
- About dialog.

## What to test in plugins

Plugin tests should cover:

- Plugin schema creation.
- Parser/import logic.
- Plugin API behavior.
- Plugin-specific database utilities.
- Live external tool integration, marked with plugin-specific live markers.

## Writing stable UI tests

Prefer testing public methods and widgets directly over brittle mouse-coordinate simulation.

Use `qtbot.addWidget(widget)` for Qt widgets.

Avoid tests that depend on exact pixel placement unless you are testing layout logic specifically.
