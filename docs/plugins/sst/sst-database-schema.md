# SST Database Schema

The SST plugin stores SST-specific catalog and import data in `sst_*` tables.

## Tables

### `sst_info_runs`

Stores raw `sst-info` command results.

Important columns:

```text
id
command
return_code
stdout
stderr
created_at
```

### `sst_elements`

Stores SST element libraries.

```text
id
name
description
```

### `sst_components`

Stores SST components and subcomponents.

```text
id
name
description
is_subcomp
iface
parent_id
category
functionality
icon_path
checkpointable
```

`parent_id` references `sst_elements.id`.

`is_subcomp` is `0` for components and `1` for subcomponents.

### `sst_parameters`

Stores parameters for SST components and statistics.

```text
id
name
description
default_val
parent_id
parent_type
required
```

`parent_type` is one of:

```text
sst_components
sst_statistics
```

### `sst_ports`

Stores component ports.

```text
id
name
description
iface
parent_id
```

`parent_id` references `sst_components.id`.

### `sst_statistics`

Stores component statistics.

```text
id
name
description
units
iface
parent_id
```

### `sst_subcomp_slots`

Stores subcomponent slots.

```text
id
name
description
iface
parent_id
```

## Why SST-prefixed tables?

SST terms are not generic across all simulation frameworks. FUSE core does not own generic `components`, `ports`, or `parameters` tables. Instead, plugins own their own catalog schemas and expose generic palette/details objects to core.

## Resetting SST tables

For development, the easiest reset is to delete the whole local database:

```bash
rm -f app_data/app.db
./scripts/setup_dev.sh
```
