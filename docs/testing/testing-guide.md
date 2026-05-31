# Testing Guide

FUSE uses `pytest` and `pytest-qt`. The fast suite is designed to run without installed SST or gem5 binaries; simulator-backed checks are isolated behind live-test markers.

## Test layout

```text
fuse/tests/                         Core/app tests
fuse/plugins/community/sst/tests/   SST plugin tests
fuse/plugins/community/gem5/tests/  gem5 plugin tests
```

SST-specific tests belong in the SST plugin. gem5-specific tests belong in the gem5 plugin.

## Running tests

Run the fast dependency-light suite from the FUSE package root, the directory that contains `pytest.ini` and `requirements-dev.txt`:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -m "not sst_live and not gem5_live"
```

This is the same marker expression used by the Core Tests GitHub Actions workflow. It includes core tests, Qt tests that can run headlessly, and dependency-light SST/gem5 unit tests. It intentionally excludes tests that require real simulator installations.

Run all tests available in the current environment:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Use this only when the local environment can satisfy every selected marker. A normal developer machine usually should not run the unfiltered suite unless SST and gem5 live-test requirements are also configured.

Run SST live tests only:

```bash
.venv/bin/python -m pytest -q -m "sst_live"
```

Run gem5 live tests only:

```bash
.venv/bin/python -m pytest -q -m "gem5_live"
```

Useful local debugging commands:

```bash
.venv/bin/python -m pytest -q -x
.venv/bin/python -m pytest --maxfail=3 -vv
.venv/bin/python -m pytest -q -k "project_settings or toolchain or compatibility"
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
- Target/catalog selection and item details.
- Toolchain command construction, version matching, and validation failure paths.
- Compatibility and migration behavior for plugin-owned project targets.
- Export behavior and plugin-specific serialization.
- Live external tool integration, marked with plugin-specific live markers.

## Current expanded regression coverage

The dependency-light suite includes broad regression tests for the current project state. In addition to the older UI, database, project I/O, parser, and live-test coverage, it now includes:

- Project/plugin/toolchain settings serialization and legacy compatibility.
- Public plugin API dataclass helpers for link compatibility, target compatibility, and migration planning.
- Local and SSH command-provider behavior, including timeout, permission, missing-executable, and environment-merging cases.
- Toolchain version parsing and version-prefix policy matching.
- Plugin discovery and plugin manager behavior for manifest loading, item details, target forwarding, and plugin filtering.
- Core validation behavior for unique names, required parameters, link endpoint latencies, plugin-delegated validation, and subcomponent attachments.
- gem5 unit coverage for built-in component metadata, toolchain command selection, and validation outcomes.
- SST unit coverage for target compatibility reporting, scene migration planning/application, variable ports, subcomponents, and JSON export behavior.

These tests are intended to be comprehensive for the current dependency-light code paths, but they do not replace live SST/gem5 integration tests. Any behavior that depends on an actual simulator binary should remain under the corresponding live marker.

## Writing stable UI tests

Prefer testing public methods and widgets directly over brittle mouse-coordinate simulation.

Use `qtbot.addWidget(widget)` for Qt widgets.

Avoid tests that depend on exact pixel placement unless you are testing layout logic specifically.
