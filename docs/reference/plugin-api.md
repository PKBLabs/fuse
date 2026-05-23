# Plugin API Reference

The plugin API is defined in:

```text
fuse/plugin_api/interfaces.py
```

## `PaletteItem`

Generic object displayed in the component palette.

```python
PaletteItem(
    plugin_id="sst",
    item_id="42",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    category="MEMORY COMPONENT",
    description="Cache component",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
    raw_kind="Component",
)
```

## `ConnectorDefinition`

Generic connector/port definition.

```python
ConnectorDefinition(
    name="highlink",
    description="CPU-side link",
    interface="SST::MemHierarchy::MemLinkBase",
)
```

## `PropertyDefinition`

Generic editable property/parameter definition.

```python
PropertyDefinition(
    name="clock",
    description="Clock frequency",
    default_value="2GHz",
    required=True,
    value_type="string",
)
```

## `ItemDetails`

Full detail object for a palette item.

```python
ItemDetails(
    palette_item=item,
    connectors=[...],
    properties=[...],
    statistics=[],
)
```

## `FusePlugin` protocol

Plugins may implement:

```python
def initialize_database(self, conn) -> None: ...
def bootstrap_database(self) -> None: ...
def load_palette_items(self) -> list[PaletteItem]: ...
def load_item_details(self, item_id: str) -> ItemDetails: ...
```

## Core expectations

- `plugin_id` should match the manifest ID.
- `item_id` must be stable within the plugin.
- `load_item_details()` should return details for a valid item ID.
- Plugin methods should not crash the entire app for missing optional external tools.
