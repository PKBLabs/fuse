# Persistence and Database

FUSE uses two persistence mechanisms:

1. A local SQLite database for plugin catalogs and runtime metadata.
2. `.fse` project files for user-created models and per-project settings.

## SQLite database

The runtime database path is controlled by:

```text
fuse/core/persistence/database.py
```

Default path:

```text
fuse/app_data/app.db
```

Tests can override it with:

```text
FUSE_DB_PATH
```

## Core database tables

Core currently owns generic core tables:

```text
core_plugins
core_schema_migrations
```

Core does not own simulator catalog tables.

## Plugin database tables

Plugins own plugin-prefixed tables.

The SST plugin creates:

```text
sst_framework_versions
sst_info_runs
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

The gem5 plugin currently creates:

```text
gem5_framework_versions
```

Future plugins should follow the same pattern:

```text
myplugin_...
rtl_...
networksim_...
```

Do not use hyphens in SQLite table names. Use underscores.

## Framework version/catalog persistence

Plugins that support multiple framework versions should store those versions in plugin-owned tables and expose them through `FrameworkTarget` objects.

Examples:

```text
sst_framework_versions -> FrameworkTarget(plugin_id="sst", ...)
gem5_framework_versions -> FrameworkTarget(plugin_id="gem5", ...)
```

Project Settings stores the selected target ID and framework version in the `.fse` project file. The full catalog remains in the database.

## Database initialization flow

`ensure_database_ready()` does the following:

1. Calls `initialize_core_database()`.
2. Discovers enabled plugins.
3. Registers plugins in `core_plugins`.
4. Calls `plugin.initialize_database(conn)`.
5. Optionally calls `plugin.bootstrap_database()`.

Bootstrap is used for heavier actions such as running `sst-info`.

## Project files

Project files are saved through:

```text
fuse/core/persistence/project_io.py
```

Project files store the model the user created and the project settings needed to interpret it. They do not store the entire plugin catalog.

Saved project data includes:

- `projectSettings`.
- Active plugin and target.
- Enabled plugin settings.
- Toolchain settings excluding secrets.
- Component instances.
- Component parameter overrides.
- Component positions.
- Links and link endpoints.

## Test isolation

Tests should set:

```text
FUSE_DB_PATH=/tmp/test_app.db
```

so they do not read or modify the developer database.

## Local database reset

From the FUSE package root:

```bash
rm -f app_data/app.db
./scripts/setup_dev.sh
```

To force a fresh SST import:

```bash
FUSE_SST_VERSION=15.1.2 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```
