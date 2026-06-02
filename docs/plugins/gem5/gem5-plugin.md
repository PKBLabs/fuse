# gem5 Plugin

The gem5 plugin provides FUSE integration for gem5-oriented model-building workflows.

Plugin path:

```text
fuse/plugins/community/gem5/
```

## Current status

The current gem5 plugin is no longer only a placeholder. It provides:

- Plugin discovery through `plugin.toml`.
- Built-in gem5 framework targets.
- Built-in palette metadata for selected gem5 objects.
- Parameter/property metadata for those objects.
- Port metadata for those objects.
- Local/SSH toolchain validation structure.
- Live CI integration against gem5 container images.

The gem5 plugin does not yet include a full automatic metadata importer equivalent to SST's `sst-info` flow.

## Manifest

```text
fuse/plugins/community/gem5/plugin.toml
```

Entry point:

```toml
[entry_points]
register = "fuse.plugins.community.gem5.plugin:register_plugin"
```

## Framework targets

The gem5 plugin currently creates built-in targets for:

```text
gem5 25.1.0.1
gem5 24.1.0.3
```

These appear in Project Settings as target version/catalog choices.

## Built-in component metadata

The plugin includes built-in fallback definitions for selected gem5 objects, such as:

```text
gem5.System
gem5.TimingSimpleCPU
gem5.SystemXBar
gem5.DDR3_1600_8x8
```

Example palette item:

```python
PaletteItem(
    plugin_id="gem5",
    item_id="timing_simple_cpu",
    display_name="gem5.TimingSimpleCPU (Component)",
    type_name="TimingSimpleCPU",
    element_name="gem5",
    category="CPU",
    description="TimingSimpleCPU SimObject for timing-mode gem5 models.",
    raw_kind="Component",
    target_label="gem5 25.1.0.1",
    framework_version="25.1.0.1",
)
```

Example details:

```python
ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="icache_port", interface="request_port"),
        ConnectorDefinition(name="dcache_port", interface="request_port"),
    ],
    properties=[
        PropertyDefinition(name="numThreads", default_value="1", required=True),
        PropertyDefinition(name="clock", default_value="2GHz", required=True),
    ],
)
```

## Toolchain validation

Project Settings can point to a local or SSH gem5 executable.

The main path is:

```text
gem5Binary
```

In CI containers this is typically:

```text
/opt/gem5/build/X86/gem5.opt
```

Some gem5 versions do not support `--version`, so health checks should use `--help` or a lightweight command that the selected gem5 version supports.

## Database schema

The gem5 plugin currently owns:

```text
gem5_framework_versions
```

Future versions may add plugin-owned metadata tables for imported SimObject schemas.

## Live tests

Tests requiring a real gem5 binary should be marked:

```python
@pytest.mark.gem5_live
```

The GitHub Actions gem5 integration workflow runs these tests in prebuilt images:

```text
ghcr.io/pkblabs/fuse-gem5-ci:gem5-v25.1.0.1
ghcr.io/pkblabs/fuse-gem5-ci:gem5-v24.1.0.3
```

## Model validation and export readiness

FUSE distinguishes between a valid editable FUSE model and a gem5 model that is ready to export. A mixed SST/gem5 `.fse` file can be saved and reopened, but gem5 export validation currently requires a gem5-only graph.

For gem5 export readiness, the plugin checks that:

- the model contains exactly one `gem5.System` component;
- all gem5 components use one selected gem5 target/version;
- the model contains at least one CPU component;
- CPU `icache_port` and `dcache_port` ports are connected;
- the model contains a `gem5.SystemXBar` interconnect;
- the crossbar `cpu_side_ports` and `mem_side_ports` ports are connected;
- the model contains at least one supported memory/DRAM component;
- memory component ports are connected;
- FUSE subcomponent attachments are not present in gem5 export graphs.

These checks are structural checks. They are meant to catch incomplete FUSE/gem5 models before export, not to prove that every simulator-level runtime constraint has been satisfied.

## gem5 Python export

The gem5 plugin can export a gem5-only FUSE graph to an editable Python configuration file from:

```text
File -> Export -> gem5 Python...
```

The exporter targets the gem5 component subset that FUSE can structurally validate. It writes a normal Python config using `m5.objects`, including a top-level `System`, clock/voltage domains, memory ranges, SimObject construction, and port assignments from FUSE links. Imported live metadata improves catalog and validation behavior, but generated configs are still intended to be reviewed and edited before production simulations.

The generated file is intentionally editable. Users should review workload, process, ISA, and simulator-specific settings before using it for production simulation runs.


## Intended future responsibilities

Future gem5 plugin work may include:

- Remote/SSH gem5 metadata import with safe probe staging.
- Deeper gem5 parameter/property type validation.
- gem5 model construction assistance.
- Broader gem5 configuration generation/export.
- Richer gem5-specific validation.
