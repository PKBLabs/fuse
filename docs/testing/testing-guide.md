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

Core/app tests should cover generic FUSE behavior that is not specific to one simulator plugin:

- Application launch/shutdown.
- Main window construction.
- Plugin discovery.
- Database initialization.
- Project save/load.
- Project settings save/load.
- Component catalog/list behavior.
- Population of the component palette from database/plugin metadata.
- Handling of invalid plugin metadata and manifests.
- Component drag payload serialization/deserialization.
- Drag/drop behavior for creating component instances.
- Conversion of drop positions into model scene coordinates.
- Component addition callbacks/model outline updates.
- Unique default component instance naming.
- Properties panel generation from component metadata.
- Display of correct parameter metadata for selected components.
- Parameter input validation.
- Required parameter validation.
- Writing parameter edits back to the model.
- Dirty-state tracking after edits.
- Routing and link creation.
- Validation.
- Splash screen.
- About dialog.


## Current core UI/metadata test areas

The current core test suite includes coverage for component drag/drop, palette population, model-view drop creation, component instance naming, outline/dirty-state behavior, plugin metadata validation, and properties panel parameter editing.

Representative files:

```text
fuse/tests/test_component_definition_drag.py
fuse/tests/test_component_palette.py
fuse/tests/test_model_view_component_drop.py
fuse/tests/test_component_instance_naming_outline_dirty.py
fuse/tests/test_plugin_metadata_validation.py
fuse/tests/test_properties_panel_parameter_editing.py
```

Keep simulator-specific tests out of these core files. SST-specific behavior belongs under `fuse/plugins/community/sst/tests/`; gem5-specific behavior belongs under `fuse/plugins/community/gem5/tests/`.

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
