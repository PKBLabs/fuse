# Data Model

FUSE currently separates project-instance data from plugin catalog data.

## Project-instance data

Project-instance data describes what the user has placed on the canvas.

Core model classes include:

- `ComponentDefinition`
- `ModelLink`

These are defined in:

```text
fuse/core/model/models.py
```

## ComponentDefinition

`ComponentDefinition` is the generic description used by the editor for palette items and dropped component instances.

Important fields:

```text
plugin_id
component_id
element
name
is_subcomp
category
iface
icon_path
display_name_override
```

The key field is `plugin_id`. A `component_id` only has meaning within the plugin that created it.

Example:

```python
ComponentDefinition(
    plugin_id="sst",
    component_id="42",
    element="memHierarchy",
    name="Cache",
    category="MEMORY COMPONENT",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
)
```

## Drag serialization

Component definitions are serialized into drag text using `to_drag_text()` and restored with `from_drag_text()`.

The current plugin-aware format is:

```text
component_id | plugin_id | element | name | is_subcomp | category | iface | icon_path | display_name_override
```

## ModelLink

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

## Plugin catalog data

Plugin catalog data describes available component types. It is not embedded wholesale into project files.

For SST, catalog data lives in `sst_*` tables.

Plugins translate catalog records into generic API objects:

- `PaletteItem`
- `ConnectorDefinition`
- `PropertyDefinition`
- `ItemDetails`
