# Plugin API Reference

The public plugin API is defined primarily in:

```text
fuse/plugin_api/interfaces.py
```

Plugins translate simulator/framework-specific metadata into the generic FUSE objects described here. Core uses these objects to populate the component palette, create dropped component instances, render ports, build the properties panel, validate required parameters, and save/load projects.

## `FrameworkTarget`

A `FrameworkTarget` represents one selectable simulator/framework catalog version.

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

| Field | Description |
|---|---|
| `plugin_id` | Owning plugin ID, such as `sst` or `gem5`. |
| `target_id` | Plugin-local ID for this target/catalog. |
| `display_name` | User-facing label in Project Settings. |
| `framework_name` | Human-readable framework name. |
| `framework_version` | Version string used in compatibility checks and project files. |
| `is_default` | Whether this target should be selected by default. |

Plugins that support multiple framework versions should implement `list_targets()` and populate these fields.

## `PaletteItem`

A `PaletteItem` is a generic object displayed in the component palette.

```python
PaletteItem(
    plugin_id="sst",
    item_id="42",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    element_name="memHierarchy",
    category="MEMORY COMPONENT",
    description="Cache component",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
    raw_kind="Component",
    target_id="1",
    target_label="SST 15.1.2",
    framework_version="15.1.2",
)
```

| Field | Description |
|---|---|
| `plugin_id` | Owning plugin. Must match the manifest/plugin object ID. |
| `item_id` | Stable plugin-local item ID. Core treats this as opaque. |
| `display_name` | Text shown in the component palette. |
| `type_name` | Framework type name. |
| `element_name` | Element, module, namespace, or family name. |
| `category` | Group/category label. |
| `description` | User-facing description. |
| `icon_path` | Optional icon path. |
| `raw_kind` | Plugin kind label such as `Component` or `SubComponent`. |
| `target_id` | Framework target/catalog ID. |
| `target_label` | Framework target/catalog label. |
| `framework_version` | Framework version for this item. |

## `ConnectorDefinition`

A `ConnectorDefinition` is generic port metadata.

```python
ConnectorDefinition(
    name="highlink",
    description="CPU-side link",
    interface="SST::Interfaces::SimpleMem",
)
```

| Field | Description |
|---|---|
| `name` | Port/connector name. Saved in link endpoints. |
| `description` | Optional user-facing description. |
| `interface` | Framework-specific interface/type string. |

FUSE currently treats links as point-to-point. Each port can participate in at most one link.

## `PropertyDefinition`

A `PropertyDefinition` is generic editable parameter metadata.

```python
PropertyDefinition(
    name="clock",
    description="Clock frequency",
    default_value="2GHz",
    required=True,
    value_type="string",
)
```

| Field | Description |
|---|---|
| `name` | Parameter name used in the properties panel and saved project. |
| `description` | Optional help text. |
| `default_value` | Initial value when the user has not overridden the parameter. |
| `required` | Whether core validation requires a non-empty value. |
| `value_type` | Type hint for current/future editors. Defaults to `string`. |

Core currently performs simple required, name, latency, integer, and numeric validation. Plugins should still set `value_type` accurately so richer editors can be added later without changing metadata.

## `ItemDetails`

`ItemDetails` is the full metadata returned for one palette item.

```python
ItemDetails(
    palette_item=item,
    connectors=[...],
    properties=[...],
    statistics=[],
)
```

| Field | Description |
|---|---|
| `palette_item` | The item being described. |
| `connectors` | Ports/connectors to render on the component node. |
| `properties` | Parameters/properties to show in the properties panel. |
| `statistics` | Optional plugin-specific statistics metadata. |

## `FusePlugin` protocol

Plugins may implement the following methods:

```python
def initialize_database(self, conn) -> None: ...
def bootstrap_database(self) -> None: ...
def list_targets(self) -> list[FrameworkTarget]: ...
def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]: ...
def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails: ...
def validate_toolchain(self, plugin_settings) -> tuple[bool, str]: ...
def import_metadata_for_toolchain(self, plugin_settings) -> None: ...
```

### `initialize_database(conn)`

Create or migrate plugin-owned database tables. This should be safe and reasonably fast because it can run during setup/startup.

### `bootstrap_database()`

Run optional heavier import/bootstrap work. SST uses this style of hook to import `sst-info` metadata when requested.

### `list_targets()`

Return selectable framework/catalog targets. This is required for plugins that support multiple simulator/framework versions.

### `load_palette_items(target_id=None)`

Return palette items for a target. If `target_id` is provided, return only items compatible with that target. This is how Project Settings filters the palette by selected simulator version.

### `load_item_details(item_id, target_id=None)`

Return full metadata for one item. This powers port rendering, properties panel generation, parameter defaults, and required-parameter validation.

### `validate_toolchain(plugin_settings)`

Validate that the configured local or SSH toolchain can be reached and is compatible with the project target.

### `import_metadata_for_toolchain(plugin_settings)`

Optional hook for plugins that can import metadata from the configured toolchain.

## Core expectations

Plugins should follow these rules:

- `plugin_id` should match the manifest ID.
- `item_id` must be stable within the plugin.
- `target_id` should be populated when a plugin supports multiple versions/catalogs.
- `load_palette_items(target_id=...)` should filter by target when applicable.
- `load_item_details(item_id, target_id=...)` should return details for the matching target.
- Plugin-specific tables should use a plugin prefix, such as `sst_*` or `gem5_*`.
- Missing optional external tools should not crash the whole app.
- Invalid metadata files should be skipped or rejected with a clear diagnostic.

## Complete example plugin item

```python
from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    FrameworkTarget,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)

class ExamplePlugin:
    plugin_id = "example"
    name = "Example Plugin"

    def list_targets(self):
        return [
            FrameworkTarget(
                plugin_id=self.plugin_id,
                target_id="example-1.0",
                display_name="ExampleSim 1.0",
                framework_name="ExampleSim",
                framework_version="1.0",
                is_default=True,
            )
        ]

    def load_palette_items(self, target_id=None):
        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id="router",
                display_name="Example.Router (Component)",
                type_name="Router",
                element_name="Example",
                category="Network",
                description="Example router component.",
                raw_kind="Component",
                target_id=target_id or "example-1.0",
                target_label="ExampleSim 1.0",
                framework_version="1.0",
            )
        ]

    def load_item_details(self, item_id, target_id=None):
        item = self.load_palette_items(target_id=target_id)[0]
        return ItemDetails(
            palette_item=item,
            connectors=[
                ConnectorDefinition(name="in", interface="example.link"),
                ConnectorDefinition(name="out", interface="example.link"),
            ],
            properties=[
                PropertyDefinition(
                    name="clock",
                    description="Router clock.",
                    default_value="1GHz",
                    required=True,
                ),
                PropertyDefinition(
                    name="num_ports",
                    description="Number of ports.",
                    default_value="4",
                    required=True,
                    value_type="int",
                ),
            ],
        )
```

See also [Component Metadata Reference](component-metadata.md).
