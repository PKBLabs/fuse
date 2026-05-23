# FUSE Project File Format

FUSE project files use `.fse` and JSON.

## Top-level fields

```json
{
  "schemaVersion": "0.1.0",
  "project": {},
  "components": [],
  "links": [],
  "editor": {}
}
```

## `project`

```json
{
  "name": "My Model",
  "updatedAt": "2026-01-01T00:00:00+00:00"
}
```

## `components`

Each component entry describes one canvas instance.

```json
{
  "id": 1,
  "element": "memHierarchy",
  "name": "Cache",
  "pluginId": "sst",
  "componentId": "42",
  "isSubcomponent": 0,
  "category": "MEMORY COMPONENT",
  "interface": "",
  "iconPath": "core/resources/media/arch_component_icons/memory_cache.png",
  "instanceName": "l1cache0",
  "parameters": {
    "cache_size": "32KiB",
    "associativity": "8"
  },
  "position": {
    "x": 100.0,
    "y": 150.0
  }
}
```

## `links`

Each link entry describes one point-to-point connection.

```json
{
  "id": 1,
  "name": "link_cpu_cache",
  "latency": "1ns",
  "type": "point_to_point",
  "source": {
    "nodeId": 1,
    "componentName": "cpu0",
    "port": "out"
  },
  "target": {
    "nodeId": 2,
    "componentName": "l1cache0",
    "port": "in"
  }
}
```

## `editor`

Stores editor-specific information such as scene rectangle and view center.

```json
{
  "sceneRect": {
    "x": 0,
    "y": 0,
    "width": 2000,
    "height": 1500
  },
  "viewCenter": {
    "x": 500,
    "y": 500
  }
}
```

## Compatibility

Project validation requires:

- `schemaVersion` matches `SCHEMA_VERSION`.
- `components` exists and is a list.
- `links` exists and is a list.

Unsupported schemas should fail clearly.
