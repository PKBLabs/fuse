# Data Model

FUSE separates project-instance data from plugin catalog data. This keeps `.fse` project files small and simulator-independent while still allowing plugins to provide rich simulator-specific metadata.

## Two data layers

```text
Plugin catalog data
  Available component types, parameters, ports, statistics, framework targets

Core composite definition data
  Locally stored reusable FUSE mini-model templates

Project-instance data
  User-created component instances, positions, links, parameter overrides, composite instance edit state
```

## Project-instance data

Project-instance data describes what the user has placed on the canvas.

Core model classes include:

- `ComponentDefinition`
- `ModelLink`
- `ProjectSettings`
- `PluginProjectSettings`
- `ToolchainSettings`
- `CompositeComponentDefinition`
- `CompositePortMapping`

These are defined in:

```text
fuse/core/model/models.py
fuse/core/model/project_settings.py
```

## `ComponentDefinition`

`ComponentDefinition` is the generic description used by the editor for palette items and dropped component instances.

Important fields:

```text
plugin_id
component_id
target_id
target_label
framework_version
element
name
is_subcomp
category
iface
icon_path
display_name_override
```

The key field is `plugin_id`. A `component_id` only has meaning within the plugin that created it. The `target_id` and `framework_version` fields make the definition version-aware. Composite component definitions use core-owned metadata (`plugin_id="core"`, `target_id="fuse-composite"`) so they can appear in the same palette without pretending to be SST or gem5 components.

Example:

```python
ComponentDefinition(
    plugin_id="sst",
    component_id="42",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
    element="memHierarchy",
    name="Cache",
    category="MEMORY COMPONENT",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
)
```

## Drag serialization

Component definitions are serialized into a JSON drag payload using `to_drag_text()` and restored with `from_drag_text()`.

Example payload:

```json
{
  "component_id": "42",
  "plugin_id": "sst",
  "target_id": "1",
  "target_label": "SST 15.1.2",
  "framework_version": "15.1.2",
  "element": "memHierarchy",
  "name": "Cache",
  "is_subcomp": 0,
  "category": "MEMORY COMPONENT",
  "iface": "",
  "icon_path": "core/resources/media/arch_component_icons/memory_cache.png",
  "display_name_override": "memHierarchy.Cache (Component)"
}
```

Backward-compatible pipe-delimited formats are still parsed for older tests/files, but new code should use the JSON payload.

## Composite component definitions

Composite components are core-owned reusable mini-model definitions. A `CompositeComponentDefinition` stores a template ID, display name, description, optional icon path, a serialized mini-model, and candidate port mappings. A `CompositePortMapping` maps a composite boundary port name to the internal component port it represents and records whether that mapping is currently exposed. Only exposed mappings become visible ports on the composite node.

Placed composite instances are normal component nodes with composite identity fields. If an instance has been edited, its instance-local mini-model is stored with that placed node in the project file. Instance-local edits do not mutate the global composite definition in the local database. Instance-local edits may include exposed/hidden port state, so one placed instance can expose a different public interface than the reusable template.

Before simulator validation/export, core flattening expands composite instances recursively into ordinary plugin-owned components and links. This keeps composite editing generic while preserving the rule that SST and gem5 plugins only receive simulator-native model objects.

## `ModelLink`

`ModelLink` represents a point-to-point link between two component instance ports.

Important fields:

```text
link_id
name
latency
source_node_id
source_component_name
source_port
target_node_id
target_component_name
target_port
link_type
```

Example:

```python
ModelLink(
    link_id=1,
    name="link_cpu_cache",
    latency="1ns",
    source_node_id=1,
    source_component_name="cpu0",
    source_port="out",
    target_node_id=2,
    target_component_name="cache0",
    target_port="in",
)
```

## Project settings model

Project settings are stored in `.fse` files and determine which plugin/target/version the model is being built against.

```python
ProjectSettings(
    project_name="Example Project",
    active_plugin_id="sst",
    plugins={
        "sst": PluginProjectSettings(
            plugin_id="sst",
            enabled=True,
            target_id="1",
            target_label="SST 15.1.2",
            framework_version="15.1.2",
            toolchain=ToolchainSettings(...),
        )
    },
)
```

`ToolchainSettings` stores execution environment information:

```text
backend                  local or ssh
tool_paths               paths such as sstInfo, sst, gem5Binary
environment              extra environment variables
options                  plugin/tool-specific options
host, port, username     SSH connection fields
remote_setup_command     optional command such as module load sst/15.1.2
```

Secrets must not be stored in project settings.

## Canvas items

The Qt graphics layer wraps model objects in visual items:

- `ComponentNodeItem`
- `PortItem`
- `ConnectionItem`

`ComponentNodeItem` stores instance-level values such as:

- `node_id`
- `instance_name`
- `parameters`
- `icon_path`
- port items

`ModelScene` manages:

- Component node creation.
- Unique default component names.
- Link creation.
- Link routing.
- Model changed notifications.
- Component-added notifications.

`ModelView` handles drag/drop and converts viewport drop positions to scene/model coordinates with `mapToScene(...)`.

## Plugin catalog data

Plugin catalog data describes available component types. It is not embedded wholesale into project files.

Plugins translate catalog records into generic API objects:

- `FrameworkTarget`
- `PaletteItem`
- `ConnectorDefinition`
- `PropertyDefinition`
- `ItemDetails`

See [Component Metadata Reference](../reference/component-metadata.md).

## Database-backed catalog data

FUSE core owns only core tables such as:

```text
core_plugins
core_schema_migrations
```

Plugins own plugin-prefixed tables.

For SST:

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

For gem5:

```text
gem5_framework_versions
```

Additional gem5 metadata tables may be added as the gem5 plugin evolves.

## Model save/load flow

Save:

```text
ModelScene + ModelView + ProjectSettings
  -> build_project_dict(...)
  -> validate_project_dict(...)
  -> JSON .fse file
```

Load:

```text
JSON .fse file
  -> validate_project_dict(...)
  -> ProjectSettings.from_project_dict(...)
  -> ComponentDefinition objects
  -> ComponentNodeItem objects
  -> ModelLink + ConnectionItem objects
```

## Dirty-state/change tracking

The scene and main window cooperate to track model changes. Component additions, property edits, and project-setting changes notify the app that the project has changed and may need saving.

Examples of edits that should mark the model dirty:

- Dropping a new component.
- Editing a component name.
- Editing a component parameter.
- Editing a link name or latency.
- Creating or modifying a link.
- Changing project settings.
