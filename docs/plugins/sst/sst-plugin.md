# SST Plugin

The SST plugin provides FUSE integration for SST metadata discovery, version-aware catalog selection, project toolchain validation, and SST JSON export.

Plugin path:

```text
fuse/plugins/community/sst/
```

## Responsibilities

The SST plugin currently:

- Runs or reads `sst-info` output.
- Parses SST elements, components, subcomponents, parameters, ports, statistics, and subcomponent slots.
- Stores SST metadata in SST-prefixed tables.
- Stores multiple SST framework/catalog versions side-by-side.
- Maps SST records to generic FUSE palette items.
- Maps SST component details to generic properties and connectors.
- Provides icon mapping through the SST icon resolver.
- Validates local or SSH SST toolchains against project settings.
- Exports FUSE models to SST JSON configuration format.

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

## Framework targets

The SST plugin exposes imported SST versions as FUSE framework targets. These targets are shown in Project Settings.

Example target labels:

```text
SST 15.1.2
SST 16.0.0
```

When a user selects an SST target:

- The component palette shows SST components for that target.
- Component details are loaded from that target's `sst_*` rows.
- Required parameter validation uses that target's metadata.
- SST JSON export should follow the selected target's catalog/version.

## Database schema

The plugin owns these tables:

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

See [SST database schema](sst-database-schema.md).

## Bootstrap/import behavior

During setup, core calls `SSTPlugin.bootstrap_database()` if plugin bootstrap is enabled.

The SST plugin:

1. Checks whether `sst-info` exists on `PATH`.
2. Reads the requested version from `FUSE_SST_VERSION`, defaulting to the configured default.
3. Checks whether a successful import already exists for that version.
4. Skips import unless refresh is forced.
5. Runs `sst-info` if needed.
6. Parses stdout.
7. Synchronizes plugin tables.

Force refresh:

```bash
FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

Import a specific version from an environment where that SST version is active:

```bash
FUSE_SST_VERSION=15.1.2 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
FUSE_SST_VERSION=16.0.0 FUSE_REFRESH_SSTINFO=1 ./scripts/setup_dev.sh
```

## Plugin API mapping

The SST plugin maps:

```text
sst_framework_versions -> FrameworkTarget
sst_components         -> PaletteItem
sst_ports              -> ConnectorDefinition
sst_parameters         -> PropertyDefinition
```

Example SST palette item:

```python
PaletteItem(
    plugin_id="sst",
    item_id="123",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    element_name="memHierarchy",
    category="MEMORY COMPONENT",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
)
```

Example SST item details:

```python
ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="highlink", interface="..."),
        ConnectorDefinition(name="lowlink", interface="..."),
    ],
    properties=[
        PropertyDefinition(name="cache_frequency", default_value="2GHz", required=True),
        PropertyDefinition(name="cache_size", default_value="32KiB", required=True),
    ],
)
```

## Toolchain validation

SST toolchain validation checks the configured execution environment.

For local execution, the relevant paths are:

```text
sstInfo
sst
```

For SSH execution, the same logical tool paths can point to remote executables.

Validation checks that `sst-info` can run and that its version is compatible with the selected project target. Version matching is compatibility-oriented; an SST 15 target can accept compatible SST 15.x installations while rejecting SST 16.x.

## SST JSON export

See [SST JSON Export Guide](sst-json-export-guide.md) for the full export workflow, validation requirements, expected JSON shape, verification steps, and known limitations.

The SST plugin can export the active model to SST JSON configuration format.

The `.fse` file remains the editable FUSE project. The SST JSON file is a generated simulator artifact.

Basic relationship:

```text
FUSE .fse project
  -> loaded into ModelScene
  -> validated against selected SST target
  -> exported as SST JSON
```

Export maps component instances and links into the SST JSON structure expected by SST's JSON configuration flow.

## Live tests

Tests requiring real SST Core/SST Elements should be marked:

```python
@pytest.mark.sst_live
```

The GitHub Actions SST integration workflow runs these tests in prebuilt images:

```text
ghcr.io/pkblabs/fuse-sst-ci:sst-15.1.2
ghcr.io/pkblabs/fuse-sst-ci:sst-16.0.0
```

## Limitations

Current limitations include:

- Core validation is still generic and does not yet fully validate all SST-specific parameter syntax.
- Subcomponent-slot modeling is represented in metadata but not yet fully modeled in the UI.
- SST JSON export should be extended as additional model features are added.
