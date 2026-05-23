# Database Table Reference

FUSE uses SQLite for local runtime metadata.

## Core tables

### `core_plugins`

Tracks discovered plugins.

```text
id
name
version
enabled
created_at
```

### `core_schema_migrations`

Tracks schema migrations.

```text
namespace
version
applied_at
```

## SST tables

The SST plugin owns `sst_*` tables:

```text
sst_info_runs
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

See [SST database schema](../plugins/sst/sst-database-schema.md).

## Future plugin tables

Future plugins should use plugin-specific prefixes, for example:

```text
gem5_...
simu_...
rtl_...
```

## Inspect tables

```bash
sqlite3 app_data/app.db ".tables"
```

## Query plugin registry

```bash
sqlite3 app_data/app.db "SELECT id, name, version, enabled FROM core_plugins;"
```
