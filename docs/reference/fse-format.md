# FUSE Project File Format

FUSE project files use the `.fse` extension and are JSON documents.

The `.fse` format is FUSE's editable project format. It is not the same as simulator-specific export formats such as SST JSON.

## Top-level fields

```json
{
  "schemaVersion": "0.1.0",
  "project": {},
  "projectSettings": {},
  "pluginSettings": {},
  "activeTarget": {},
  "components": [],
  "links": [],
  "editor": {}
}
```

| Field | Meaning |
|---|---|
| `schemaVersion` | FUSE project schema version. |
| `project` | Basic project metadata. |
| `projectSettings` | Project-wide plugin, target, and toolchain settings. |
| `pluginSettings` | Compatibility mirror of plugin settings. |
| `activeTarget` | Compatibility/quick-lookup active plugin and target. |
| `components` | Component instances placed on the canvas. |
| `links` | Point-to-point model links. |
| `editor` | Editor view metadata. |

## `project`

```json
{
  "name": "My Model",
  "updatedAt": "2026-01-01T00:00:00+00:00"
}
```

## `projectSettings`

`projectSettings` stores per-project plugin settings.

```json
{
  "projectName": "My Model",
  "activePluginId": "sst",
  "plugins": {
    "sst": {
      "enabled": true,
      "targetId": "1",
      "targetLabel": "SST 15.1.2",
      "frameworkVersion": "15.1.2",
      "toolchain": {
        "backend": "local",
        "toolPaths": {
          "sstInfo": "/opt/sst/bin/sst-info",
          "sst": "/opt/sst/bin/sst"
        },
        "environment": {},
        "options": {},
        "host": "",
        "port": 22,
        "username": "",
        "hostAlias": "",
        "authMethod": "ssh-agent",
        "remoteSetupCommand": ""
      },
      "options": {}
    }
  }
}
```

Toolchain settings must not contain passwords, private keys, or passphrases.

## `activeTarget`

`activeTarget` is retained for compatibility and quick lookup.

```json
{
  "pluginId": "sst",
  "targetId": "1"
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
  "targetId": "1",
  "targetLabel": "SST 15.1.2",
  "frameworkVersion": "15.1.2",
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

| Field | Meaning |
|---|---|
| `id` | Component node ID in the saved model. |
| `element` | Framework element/module/namespace. |
| `name` | Component type name. |
| `pluginId` | Plugin that owns the component type. |
| `targetId` | Framework target/catalog ID. |
| `targetLabel` | User-facing target label. |
| `frameworkVersion` | Framework version associated with the component metadata. |
| `componentId` | Plugin-local component ID. |
| `isSubcomponent` | Whether the component type is a subcomponent. |
| `category` | Category/grouping label. |
| `interface` | Framework-specific interface string. |
| `iconPath` | Icon used for this component instance. |
| `instanceName` | Unique instance name. |
| `parameters` | User-entered parameter overrides. |
| `position` | Model-scene coordinate position. |

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

| Field | Meaning |
|---|---|
| `id` | Link ID in the saved model. |
| `name` | Unique link name. |
| `latency` | Link latency value. |
| `type` | Link type. Currently usually `point_to_point`. |
| `source.nodeId` | Source component node ID. |
| `source.componentName` | Source instance name. |
| `source.port` | Source port name. |
| `target.nodeId` | Target component node ID. |
| `target.componentName` | Target instance name. |
| `target.port` | Target port name. |

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

The `editor` block is not simulator model data.

## Compatibility

Project validation requires:

- `schemaVersion` matches `SCHEMA_VERSION`.
- `components` exists and is a list.
- `links` exists and is a list.

Unsupported schemas should fail clearly.

Older `.fse` files that lack `projectSettings` may still be interpreted using `activeTarget` compatibility logic.
