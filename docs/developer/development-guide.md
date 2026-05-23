# Development Guide

This guide describes how to work on FUSE locally.

## Repository layout

A typical checkout contains:

```text
README.md
docs/
examples/
fuse/
    app/
    app_data/
    core/
    plugin_api/
    plugins/
    scripts/
    tests/
```

The Python package is the inner `fuse/` directory.

## Setup

From the FUSE package root:

```bash
chmod +x scripts/setup_dev.sh
./scripts/setup_dev.sh
```

## Running the app during development

```bash
fuse-mod
```

or:

```bash
PYTHONPATH="$(pwd)/.." .venv/bin/python -m fuse.app.main
```

## Installing test dependencies

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Running tests

```bash
.venv/bin/python -m pytest -q
```

Fast tests only:

```bash
.venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```

## Code organization rules

Keep these boundaries:

```text
app/         Qt application shell and main window.
core/        simulator-agnostic editor functionality.
plugin_api/  public plugin-facing interfaces.
plugins/     simulator/framework-specific integrations.
```

Core should not import from `plugins.community.sst` or `plugins.community.gem5` directly.

Plugins may import generic core services such as database connection helpers and plugin API dataclasses.

## Adding a feature

When adding a new feature, ask:

1. Is it simulator-agnostic?
   - Put it in `core/`.
2. Is it UI-related?
   - Put it in `core/ui/` or `app/` depending on scope.
3. Is it plugin-specific?
   - Put it in the relevant plugin.
4. Does it affect project files?
   - Update `project_io.py` and tests.
5. Does it affect validation?
   - Update `core/model/validation.py` and tests.

## Useful environment variables

```text
FUSE_DB_PATH
FUSE_REFRESH_SSTINFO
FUSE_SPLASH_MS
FUSE_TEST_AUTOCLOSE_MS
QT_QPA_PLATFORM
```

See [Environment variables](../reference/environment-variables.md).
