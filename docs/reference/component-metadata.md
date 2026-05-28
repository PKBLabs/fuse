# Component Metadata Reference

This document describes the generic metadata that FUSE uses to display components, create component instances, expose editable parameters, create ports, and decide whether a component belongs to a selected framework/version target.

FUSE intentionally separates **catalog metadata** from **project-instance data**.

- Catalog metadata describes component types that a plugin makes available, such as `memHierarchy.Cache` or `gem5.TimingSimpleCPU`.
- Project-instance data describes the objects the user has placed in a `.fse` project, such as `cache_1` at position `(300, 200)` with `clock = 2GHz`.

The generic API types are defined in:

```text
fuse/plugin_api/interfaces.py
```

The editor-facing drag/drop object is defined in:

```text
fuse/core/model/models.py
```

## Metadata flow

A component type normally moves through FUSE like this:

```text
Plugin metadata source
  -> plugin-specific database or built-in plugin records
  -> PaletteItem
  -> ComponentDefinition
  -> drag MIME payload
  -> ComponentNodeItem instance on the canvas
  -> .fse project component entry
```

For SST, the plugin imports metadata from `sst-info` into `sst_*` tables, then exposes selected records as generic palette items. For gem5, the current community plugin exposes built-in metadata for supported SimObjects.

## Framework target metadata

A framework target identifies a simulator/framework version and catalog that can be selected in Project Settings.

Generic type:

```python
FrameworkTarget(
    plugin_id="sst",
    target_id="1",
    display_name="SST 15.1.2",
    framework_name="SST",
    framework_version="15.1.2",
    is_default=True,
)
```

| Field | Required | Meaning |
|---|---:|---|
| `plugin_id` | Yes | Plugin that owns this target, such as `sst` or `gem5`. |
| `target_id` | Yes | Stable ID used by the plugin to load the correct catalog/version. For database-backed plugins this is often a row ID. |
| `display_name` | Yes | User-facing label shown in Project Settings. |
| `framework_name` | Recommended | Human-readable simulator/framework name. |
| `framework_version` | Recommended | Version string used for compatibility checks and project save/load metadata. |
| `is_default` | No | Whether this should be selected by default when no project preference exists. |

## Component catalog metadata: `PaletteItem`

`PaletteItem` is the plugin API object that fills the component palette.

```python
PaletteItem(
    plugin_id="sst",
    item_id="42",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    element_name="memHierarchy",
    category="MEMORY COMPONENT",
    description="SST cache component",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
    raw_kind="Component",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
)
```

| Field | Required | Meaning |
|---|---:|---|
| `plugin_id` | Yes | Plugin that owns the item. It must match the plugin manifest ID and plugin instance ID. |
| `item_id` | Yes | Stable plugin-local item identifier. Core treats this as opaque. |
| `display_name` | Yes | Text shown in the component palette. |
| `type_name` | Yes | Simulator/framework type name, such as `Cache`, `TimingSimpleCPU`, or `SystemXBar`. |
| `element_name` | Recommended | Simulator namespace/family, such as SST element `memHierarchy` or generic `gem5`. |
| `category` | Recommended | Grouping/category used for organization and fallback display. |
| `description` | Recommended | User-facing description shown in details/help surfaces. |
| `icon_path` | Optional | Relative or absolute icon path used for dropped component instances. |
| `raw_kind` | Optional | Plugin-specific kind label, such as `Component` or `SubComponent`. |
| `target_id` | Recommended | Framework target/catalog ID this item belongs to. |
| `target_label` | Recommended | User-facing target label, such as `SST 15.1.2`. |
| `framework_version` | Recommended | Framework version associated with the item. |

### Important rules

- `item_id` only has meaning within the owning `plugin_id`.
- `target_id` should be populated when a plugin supports multiple framework versions.
- `display_name` should be stable enough for users to recognize but does not need to be a unique database key.
- Plugins should keep simulator-specific metadata in plugin-owned tables and translate to `PaletteItem` at the plugin API boundary.

## Editor drag/drop metadata: `ComponentDefinition`

`ComponentDefinition` is the generic editor object used for drag/drop and component-node creation.

```python
ComponentDefinition(
    plugin_id="sst",
    component_id="42",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
    element="memHierarchy",
    name="Cache",
    is_subcomp=0,
    category="MEMORY COMPONENT",
    iface="",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
    display_name_override="memHierarchy.Cache (Component)",
)
```

| Field | Required | Meaning |
|---|---:|---|
| `plugin_id` | Yes | Plugin that owns this component type. |
| `component_id` | Recommended | Plugin-local catalog ID. Serialized as `componentId` in `.fse` files. |
| `target_id` | Recommended | Selected framework target/catalog ID. |
| `target_label` | Recommended | User-facing framework target label. |
| `framework_version` | Recommended | Framework version used for validation/export context. |
| `element` | Recommended | Framework element/namespace/family. |
| `name` | Yes | Component type name. Used as the base for generated instance names. |
| `is_subcomp` | Optional | Integer/bool flag indicating whether the type is a subcomponent. |
| `category` | Optional | Component grouping/category. |
| `iface` | Optional | Interface type for subcomponents or framework-specific matching. |
| `icon_path` | Optional | Icon path copied into the component instance. |
| `display_name_override` | Optional | Palette/display string override. |

### Drag MIME payload

The component palette serializes `ComponentDefinition` with `to_drag_text()`. The model canvas decodes it with `from_drag_text()` when the user drops the component.

The current payload is JSON and contains:

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

FUSE still supports older pipe-delimited drag payloads for backward compatibility, but new code should use the JSON form.

## Full component details: `ItemDetails`

When a component is selected or dropped, FUSE asks the plugin for full details:

```python
ItemDetails(
    palette_item=item,
    connectors=[...],
    properties=[...],
    statistics=[],
)
```

`ItemDetails` is where a plugin provides port metadata, parameter metadata, and optional statistics metadata for a specific palette item.

## Parameter metadata: `PropertyDefinition`

FUSE exposes simulator parameters as generic properties.

```python
PropertyDefinition(
    name="clock",
    description="Clock frequency.",
    default_value="1GHz",
    required=True,
    value_type="string",
)
```

| Field | Required | Meaning |
|---|---:|---|
| `name` | Yes | Parameter/property name as shown in the properties panel and saved under `parameters`. |
| `description` | Recommended | Help text/tool tip for the user. |
| `default_value` | Optional | Initial value shown when the user has not overridden the parameter. |
| `required` | Optional | Whether validation requires a non-empty value. |
| `value_type` | Optional | Intended type hint. Current core UI primarily infers numeric validation from defaults and has special validation for latency. |

### Parameter naming

Parameter names should match the simulator/exporter field names whenever possible. For example, an SST parameter imported as `clock` should remain `clock` in FUSE so SST export can write it back without translation.

### Required parameters

A parameter is required when `required=True`. The SST plugin also treats SST defaults of `<required>` as required values and displays them as empty required fields in the properties panel.

### Type validation

The current core properties panel performs these checks:

- Names must be non-empty and unique across component and link names.
- Required parameters must be non-empty.
- Link latency values must end in a recognized time unit: `fs`, `ps`, `ns`, `us`, `ms`, or `s`.
- If a default value looks like an integer, edited values must also parse as integers.
- If a default value looks like a float, edited values must also parse as numbers.

Future plugin-specific editors may provide richer type-aware widgets, enums, ranges, units, and validation rules.

## Port metadata: `ConnectorDefinition`

FUSE represents ports/connectors with `ConnectorDefinition`.

```python
ConnectorDefinition(
    name="highlink",
    description="CPU-side cache link.",
    interface="SST::Interfaces::SimpleMem",
)
```

| Field | Required | Meaning |
|---|---:|---|
| `name` | Yes | Port name shown on the component node and saved in link endpoints. |
| `description` | Recommended | User-facing help text. |
| `interface` | Recommended | Framework-specific interface/type string used by plugins and future validation. |

### Port behavior in the model editor

- Ports are rendered as small connection points on component nodes.
- A link is created by clicking one unconnected port, then another unconnected port.
- The current core model treats links as point-to-point; each port can participate in at most one link.
- Link endpoints are saved by node ID, component instance name, and port name.

If a plugin returns no ports for a component, the graphics item may use fallback ports so that the component remains usable in the editor. Plugin authors should still provide explicit port metadata whenever possible.

## Compatibility metadata

Compatibility metadata appears at two levels: plugin compatibility and framework target compatibility.

### Plugin manifest compatibility

Plugin manifest compatibility belongs in `plugin.toml`:

```toml
[compatibility]
fuse_plugin_api = ">=1.0,<2.0"
fuse_app = ">=0.1,<1.0"
```

Core plugin discovery reads manifests from:

```text
fuse/plugins/community/*/plugin.toml
```

Malformed TOML manifests are skipped with a diagnostic instead of crashing the application.

### Framework/catalog compatibility

Framework/catalog compatibility is represented by `FrameworkTarget`, `PaletteItem.target_id`, and project settings.

A project can enable a plugin and select a target/catalog version:

```json
{
  "projectSettings": {
    "projectName": "Example Project",
    "activePluginId": "sst",
    "plugins": {
      "sst": {
        "enabled": true,
        "targetId": "1",
        "targetLabel": "SST 15.1.2",
        "frameworkVersion": "15.1.2"
      }
    }
  }
}
```

When a project target is selected:

- The component palette is filtered to the active plugin/target.
- Component details are loaded for that plugin/target.
- Validation uses metadata from that selected target.
- Exporters should use the selected framework version and target-specific nuances.

### Toolchain compatibility

Project Settings can point to either a local toolchain or a remote SSH environment. Toolchain validation checks whether the configured simulator can be reached and whether it is compatible with the selected target.

For user convenience, validation may use relaxed version matching. For example, an SST 15 target can accept a compatible SST 15.x toolchain, while rejecting SST 16.x.

## Example: generic component definition

```python
from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)

item = PaletteItem(
    plugin_id="example",
    item_id="router",
    display_name="Example.Router (Component)",
    type_name="Router",
    element_name="Example",
    category="Network",
    description="Example network router.",
    icon_path="core/resources/media/arch_component_icons/router.png",
    raw_kind="Component",
    target_id="example-1",
    target_label="ExampleSim 1.0",
    framework_version="1.0",
)

details = ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(
            name="north",
            description="North-facing link.",
            interface="example.link",
        ),
        ConnectorDefinition(
            name="south",
            description="South-facing link.",
            interface="example.link",
        ),
    ],
    properties=[
        PropertyDefinition(
            name="clock",
            description="Router clock frequency.",
            default_value="1GHz",
            required=True,
            value_type="string",
        ),
        PropertyDefinition(
            name="num_ports",
            description="Number of router ports.",
            default_value="4",
            required=True,
            value_type="int",
        ),
    ],
)
```

## Example: SST-style component metadata

```python
PaletteItem(
    plugin_id="sst",
    item_id="123",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    element_name="memHierarchy",
    category="MEMORY COMPONENT",
    description="Cache component imported from sst-info.",
    raw_kind="Component",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
)
```

```python
ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="highlink", interface="memHierarchy.MemLink"),
        ConnectorDefinition(name="lowlink", interface="memHierarchy.MemLink"),
    ],
    properties=[
        PropertyDefinition(name="cache_frequency", default_value="2GHz", required=True),
        PropertyDefinition(name="cache_size", default_value="32KiB", required=True),
        PropertyDefinition(name="associativity", default_value="8", required=True),
    ],
)
```

## Example: gem5-style component metadata

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
    target_id="2",
    target_label="gem5 25.1.0.1",
    framework_version="25.1.0.1",
)
```

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
