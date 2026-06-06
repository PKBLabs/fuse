# Database Table Reference

FUSE uses SQLite for local runtime metadata.

The database stores plugin catalogs and other local metadata. FUSE project files store the user's model and project settings; they do not embed entire plugin catalogs.

## Database location

By default, the development database lives under the FUSE package root:

```text
fuse/app_data/app.db
```

Tests can override this with:

```bash
FUSE_DB_PATH=/tmp/fuse-test.db
```

## Core tables

### `core_plugins`

Tracks discovered plugins.

| Column | Meaning |
|---|---|
| `id` | Plugin ID. |
| `name` | Plugin display name. |
| `version` | Plugin version from manifest metadata. |
| `enabled` | Whether the plugin is enabled. |
| `created_at` | Creation timestamp. |

### `core_composite_components`

Stores local reusable composite component definitions. These are FUSE mini-model templates, not simulator plugin catalog records.

| Column | Meaning |
|---|---|
| `id` | Composite definition/template ID. |
| `name` | User-facing composite template name. |
| `description` | Optional user-facing description. |
| `icon_path` | Optional icon path used for the template and new instances. |
| `mini_model_json` | Serialized FUSE mini-model containing internal components, links, attachments, and layout. |
| `port_map_json` | Serialized candidate port mappings from composite boundary ports to internal component ports, including exposed/hidden state. |
| `schema_version` | Composite definition schema version. |
| `created_at` | Creation timestamp. |
| `updated_at` | Last update timestamp. |

Composite definitions are listed in the component palette under **Composite Components** and can be managed through **Edit -> Manage Composite Components...**. Template edits, including exposed/hidden port state, are saved back to this table.

### `core_schema_migrations`

Tracks schema migrations.

| Column | Meaning |
|---|---|
| `namespace` | Migration namespace. |
| `version` | Migration version. |
| `applied_at` | Timestamp. |

## SST tables

The SST plugin owns `sst_*` tables.

### `sst_framework_versions`

Stores imported SST framework/catalog versions.

| Column | Meaning |
|---|---|
| `id` | Target/catalog ID used by Project Settings. |
| `version` | SST version string. |
| `label` | User-facing label such as `SST 15.1.2`. |
| `source_kind` | Metadata source kind, usually `sst-info`. |
| `source_path` | Source path, if applicable. |
| `sst_info_command` | Command used for import. |
| `is_default` | Default target flag. |
| `created_at` | Creation timestamp. |

### `sst_info_runs`

Records SST metadata import attempts.

| Column | Meaning |
|---|---|
| `id` | Import run ID. |
| `framework_version_id` | Associated SST target ID. |
| `command` | Command used. |
| `return_code` | Process return code. |
| `stdout` | Captured standard output. |
| `stderr` | Captured standard error. |
| `created_at` | Run timestamp. |

### `sst_elements`

Stores SST elements, such as `memHierarchy`.

| Column | Meaning |
|---|---|
| `id` | Element ID. |
| `framework_version_id` | SST target ID. |
| `name` | Element name. |
| `description` | Description text. |

### `sst_components`

Stores SST components and subcomponents.

| Column | Meaning |
|---|---|
| `id` | Component ID used as FUSE `componentId`. |
| `framework_version_id` | SST target ID. |
| `name` | Component type name. |
| `description` | Description text. |
| `is_subcomp` | Whether the row describes a subcomponent. |
| `iface` | Interface string. |
| `parent_id` | Owning `sst_elements.id`. |
| `category` | Category label. |
| `functionality` | SST-provided functionality text. |
| `icon_path` | Resolved icon path. |
| `checkpointable` | Checkpoint support flag. |

### `sst_parameters`

Stores SST parameter metadata.

| Column | Meaning |
|---|---|
| `id` | Parameter ID. |
| `framework_version_id` | SST target ID. |
| `name` | Parameter name. |
| `description` | Description text. |
| `default_val` | Default value. `<required>` is treated as a required empty value by FUSE. |
| `parent_id` | Component/statistic ID. |
| `parent_type` | Parent table name, currently `sst_components` or `sst_statistics`. |
| `required` | Required flag. |

### `sst_ports`

Stores SST port metadata.

| Column | Meaning |
|---|---|
| `id` | Port ID. |
| `framework_version_id` | SST target ID. |
| `name` | Port name. |
| `description` | Description text. |
| `iface` | Interface/type string. |
| `parent_id` | Owning component ID. |

### `sst_statistics`

Stores SST statistic metadata.

| Column | Meaning |
|---|---|
| `id` | Statistic ID. |
| `framework_version_id` | SST target ID. |
| `name` | Statistic name. |
| `description` | Description text. |
| `units` | Statistic units. |
| `iface` | Interface/type string. |
| `parent_id` | Owning component ID. |

### `sst_subcomp_slots`

Stores SST subcomponent slot metadata.

| Column | Meaning |
|---|---|
| `id` | Slot ID. |
| `framework_version_id` | SST target ID. |
| `name` | Slot name. |
| `description` | Description text. |
| `iface` | Interface string. |
| `parent_id` | Owning component ID. |

## gem5 tables

### `gem5_framework_versions`

Stores selectable gem5 target/catalog versions.

| Column | Meaning |
|---|---|
| `id` | Target/catalog ID used by Project Settings. |
| `version` | gem5 version string. |
| `label` | User-facing label such as `gem5 25.1.0.1`. |
| `source_kind` | Source kind, currently usually `built-in`. |
| `source_path` | Optional metadata source path. |
| `gem5_root` | Optional gem5 root path. |
| `gem5_binary_path` | Optional gem5 executable path. |
| `build_isa` | Build ISA such as `X86`. |
| `is_default` | Default target flag. |
| `created_at` | Creation timestamp. |

The current gem5 plugin uses built-in component metadata in Python code. Future versions may add plugin-owned gem5 metadata tables for imported SimObject schemas.

## Plugin table rules

Future plugins should use plugin-specific prefixes, for example:

```text
myplugin_...
rtl_...
networksim_...
```

Plugins should not create generic core tables named:

```text
components
parameters
ports
```

## Inspect tables

```bash
sqlite3 fuse/app_data/app.db ".tables"
```

## Query plugin registry

```bash
sqlite3 fuse/app_data/app.db "SELECT id, name, version, enabled FROM core_plugins;"
```

## Query framework targets

SST:

```bash
sqlite3 fuse/app_data/app.db "SELECT id, version, label, is_default FROM sst_framework_versions;"
```

gem5:

```bash
sqlite3 fuse/app_data/app.db "SELECT id, version, label, build_isa, is_default FROM gem5_framework_versions;"
```

## Query palette-style SST components

```bash
sqlite3 fuse/app_data/app.db '
SELECT c.id, fv.version, e.name AS element, c.name, c.category, c.is_subcomp
FROM sst_components c
JOIN sst_elements e ON c.parent_id = e.id
JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
ORDER BY fv.version, e.name, c.name
LIMIT 25;
'
```
