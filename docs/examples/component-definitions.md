# Example Component Definitions

This page gives concrete examples of component metadata for FUSE plugins.

For field-by-field reference, see [Component Metadata Reference](../reference/component-metadata.md).

## Minimal component with two ports

```python
from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)

item = PaletteItem(
    plugin_id="example",
    item_id="adder",
    display_name="Example.Adder (Component)",
    type_name="Adder",
    element_name="Example",
    category="Compute",
    description="Simple arithmetic component.",
    raw_kind="Component",
    target_id="example-1.0",
    target_label="ExampleSim 1.0",
    framework_version="1.0",
)

details = ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="in", description="Input port", interface="example.signal"),
        ConnectorDefinition(name="out", description="Output port", interface="example.signal"),
    ],
    properties=[
        PropertyDefinition(
            name="latency_cycles",
            description="Component latency in cycles.",
            default_value="1",
            required=True,
            value_type="int",
        )
    ],
)
```

## Component with multiple required parameters

```python
PaletteItem(
    plugin_id="example",
    item_id="cache",
    display_name="Example.Cache (Component)",
    type_name="Cache",
    element_name="Example",
    category="Memory",
    description="Example cache component.",
    raw_kind="Component",
    target_id="example-1.0",
    target_label="ExampleSim 1.0",
    framework_version="1.0",
)
```

```python
ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="cpu_side", interface="example.memory_request"),
        ConnectorDefinition(name="mem_side", interface="example.memory_request"),
    ],
    properties=[
        PropertyDefinition(name="clock", default_value="2GHz", required=True),
        PropertyDefinition(name="size", default_value="32KiB", required=True),
        PropertyDefinition(name="associativity", default_value="8", required=True, value_type="int"),
        PropertyDefinition(name="replacement_policy", default_value="lru", required=False),
    ],
)
```

## SST-style cache component

```python
PaletteItem(
    plugin_id="sst",
    item_id="123",
    display_name="memHierarchy.Cache (Component)",
    type_name="Cache",
    element_name="memHierarchy",
    category="MEMORY COMPONENT",
    description="Cache component imported from sst-info.",
    icon_path="core/resources/media/arch_component_icons/memory_cache.png",
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
        ConnectorDefinition(name="highlink", description="CPU-side link", interface="memHierarchy.MemLink"),
        ConnectorDefinition(name="lowlink", description="Memory-side link", interface="memHierarchy.MemLink"),
    ],
    properties=[
        PropertyDefinition(name="cache_frequency", default_value="2GHz", required=True),
        PropertyDefinition(name="cache_size", default_value="32KiB", required=True),
        PropertyDefinition(name="associativity", default_value="8", required=True, value_type="int"),
        PropertyDefinition(name="access_latency_cycles", default_value="4", required=True, value_type="int"),
    ],
)
```

## gem5-style CPU component

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
    target_id="1",
    target_label="gem5 25.1.0.1",
    framework_version="25.1.0.1",
)
```

```python
ItemDetails(
    palette_item=item,
    connectors=[
        ConnectorDefinition(name="icache_port", description="Instruction cache port", interface="request_port"),
        ConnectorDefinition(name="dcache_port", description="Data cache port", interface="request_port"),
    ],
    properties=[
        PropertyDefinition(name="numThreads", description="Number of hardware threads", default_value="1", required=True, value_type="int"),
        PropertyDefinition(name="clock", description="CPU clock frequency", default_value="2GHz", required=True),
    ],
)
```

## Drag/drop result

When the user drops one of these components onto the canvas, FUSE converts the catalog metadata into a component instance.

Example saved instance:

```json
{
  "id": 1,
  "pluginId": "example",
  "targetId": "example-1.0",
  "targetLabel": "ExampleSim 1.0",
  "frameworkVersion": "1.0",
  "componentId": "cache",
  "element": "Example",
  "name": "Cache",
  "instanceName": "Cache_1",
  "parameters": {
    "clock": "2GHz",
    "size": "32KiB",
    "associativity": "8"
  },
  "position": {
    "x": 300.0,
    "y": 200.0
  }
}
```

The instance name, parameter values, icon path, and position can then be edited/saved as part of the FUSE project.
