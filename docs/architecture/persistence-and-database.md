# Persistence and Database

FUSE uses two persistence mechanisms:

1. A local SQLite database for plugin catalogs and runtime metadata.
2. `.fse` project files for user-created models.

## SQLite database

The runtime database path is controlled by `fuse/core/persistence/database.py`.

Default path:

```text
app_data/app.db
```

Tests can override it with:

```text
FUSE_DB_PATH
```

## Core database tables

Core currently owns only generic core tables:

```text
core_plugins
core_schema_migrations
```

Core does not own SST catalog tables.

## Plugin database tables

Plugins own plugin-prefixed tables.

The SST plugin creates:

```text
sst_info_runs
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

Future plugins should follow the same pattern:

```text
gem5_...
simu_...
rtl_...
```

Do not use hyphens in SQLite table names. Use underscores.

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

Project files store the model the user created. They do not store the entire plugin catalog.

## Test isolation

Tests should set:

```text
FUSE_DB_PATH=/tmp/test_app.db
```

so they do not read or modify the developer database.
