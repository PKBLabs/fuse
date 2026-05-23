# SST Plugin

The SST plugin provides FUSE integration for SST metadata discovery and model-building workflows.

Plugin path:

```text
fuse/plugins/community/sst/
```

## Responsibilities

The SST plugin currently:

- Runs or reads `sst-info` output.
- Parses SST elements, components, subcomponents, parameters, ports, statistics, and subcomponent slots.
- Stores SST metadata in SST-prefixed tables.
- Maps SST records to generic FUSE palette items.
- Maps SST component details to generic properties and connectors.
- Provides icon mapping through the SST icon resolver.

## Entry point

The manifest is:

```text
fuse/plugins/community/sst/plugin.toml
```

Entry point:

```toml
[entry_points]
register = "fuse.plugins.community.sst.plugin:register_plugin"
```

The register function returns an `SSTPlugin` instance.

## Database schema

The plugin owns these tables:

```text
sst_info_runs
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

See [SST database schema](sst-database-schema.md).

## Bootstrap behavior

During setup, core calls `SSTPlugin.bootstrap_database()` if plugin bootstrap is enabled.

The SST plugin:

1. Checks whether `sst-info` exists on `PATH`.
2. Checks whether a successful import has already run.
3. Skips import unless refresh is forced.
4. Runs `sst-info` if needed.
5. Parses stdout.
6. Synchronizes plugin tables.

Force refresh:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Plugin API mapping

The SST plugin maps:

```text
sst_components -> PaletteItem
sst_ports -> ConnectorDefinition
sst_parameters -> PropertyDefinition
```

## Limitations

The current SST plugin imports metadata and exposes it to the editor. Full SST Python model export is planned but should be documented separately once implemented.
