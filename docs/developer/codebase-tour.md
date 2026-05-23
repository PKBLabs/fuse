# Codebase Tour

## `fuse/app/`

Application shell.

- `main.py`: entrypoint.
- `app.py`: `MainWindow`, menus, docking, project actions, startup.
- `about.py`: About dialog.
- `splash.py`: splash screen.

## `fuse/core/model/`

Generic model structures and validation.

- `models.py`: `ComponentDefinition`, `ModelLink`, constants.
- `validation.py`: generic model validation.

## `fuse/core/ui/`

Qt UI and graphics-view classes.

- `component_palette.py`: palette list and drag handling.
- `graphics_items.py`: component, port, link graphics items.
- `model_scene.py`: scene behavior, link creation, selection.
- `model_view.py`: drag/drop target and canvas view.
- `properties_panel.py`: dockable properties and parameter editor.

## `fuse/core/persistence/`

Database and project file logic.

- `database.py`: SQLite connection and core schema.
- `db_access.py`: plugin-aware data access bridge for core UI.
- `project_io.py`: `.fse` project save/load.

## `fuse/core/plugin_runtime/`

Plugin discovery and dispatch.

- `manager.py`: scans plugin manifests, loads entry points, dispatches plugin calls.

## `fuse/core/routing/`

Routing algorithms.

- `routing.py`: orthogonal path routing utilities.

## `fuse/plugin_api/`

Public plugin API dataclasses and protocol definitions.

- `interfaces.py`: `PaletteItem`, `ConnectorDefinition`, `PropertyDefinition`, `ItemDetails`, `FusePlugin` protocol.
- `manifest.py`, `registry.py`, `version.py`: plugin support modules.

## `fuse/plugins/community/sst/`

SST plugin.

- `plugin.py`: plugin entry point.
- `plugin.toml`: plugin manifest.
- `initialize_db.py`: SST-specific schema creation.
- `get_sstinfo.py`: `sst-info` runner/parser/importer.
- `db_utils.py`: SST-specific database query helpers.
- `sst_icon_resolver.py`: SST-to-icon mapping.
- `sst_analysis.py`: pandas analysis utilities.
- `audit_sst_icon_mapping.py`: icon mapping audit tool.

## `fuse/plugins/community/gem5/`

gem5 community plugin placeholder.

- `plugin.py`: placeholder plugin entry point.
- `plugin.toml`: manifest.

## `fuse/tests/`

Core and app tests.

## `fuse/plugins/community/sst/tests/`

SST plugin tests.
