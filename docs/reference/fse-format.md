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
| `components` | Component instances placed on the canvas, including composite instances. |
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

`projectSettings` stores per-project plugin settings and user-facing catalog preferences.

```json
{
  "projectName": "My Model",
  "activePluginId": "sst",
  "preferredComponentSortingMode": "Alphabetical",
  "preferredComponentGroupingMode": "Element",
  "autoExpandAllComponentTree": false,
  "componentCatalogExpanded": false,
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

Catalog preference fields are editor/user-experience settings:

| Field | Meaning |
|---|---|
| `preferredComponentSortingMode` | Default component catalog sorting mode, such as `Alphabetical` or `Catalog Order`. |
| `preferredComponentGroupingMode` | Default component catalog grouping mode when no compatibility context is active, such as `Element`, `Function`, `Recent`, or `Flat`. |
| `autoExpandAllComponentTree` | Whether the component catalog should expand all groups whenever it is rebuilt. |
| `componentCatalogExpanded` | Last explicit Expand/Collapse All state for the component catalog. |

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
  },
  "isComposite": 0,
  "compositeId": ""
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
| `isComposite` | `1` when this component entry is a FUSE composite instance; otherwise `0`. |
| `compositeId` | Composite template ID for FUSE composite instances. Empty for normal plugin-owned components. |
| `compositeInstance` | Optional instance-local composite mini-model state for edited composite instances. |

### Composite instance state

Composite component instances may include an optional `compositeInstance` block when that placed instance has instance-local mini-model state.

```json
{
  "id": 7,
  "pluginId": "core",
  "targetId": "fuse-composite",
  "componentId": "6cb322e5-cfae-40f9-b6e9-example",
  "isComposite": 1,
  "compositeId": "6cb322e5-cfae-40f9-b6e9-example",
  "instanceName": "CacheCluster_1",
  "compositeInstance": {
    "miniModel": {
      "kind": "fuse.composite-mini-model",
      "components": [],
      "links": [],
      "subcomponentAttachments": []
    },
    "portMappings": []
  }
}
```

| Field | Meaning |
|---|---|
| `pluginId` | Composite instances use the core-owned plugin ID, currently `core`. |
| `targetId` | Composite instances use the core-owned target ID, currently `fuse-composite`. |
| `componentId` / `compositeId` | The local composite definition/template ID. |
| `isComposite` | Marks the component as a FUSE composite instance. |
| `compositeInstance.miniModel` | Instance-local editable mini-model for this placed instance. |
| `compositeInstance.portMappings` | External port mappings for this instance. |

The `compositeInstance` block is omitted when there is no meaningful instance-local mini-model to save. The global reusable composite definition itself is stored in the local database and can be exported separately as a `.fcc` file.

Composite instances are expanded before plugin validation/export. Simulator-specific output should not contain FUSE composite nodes.

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

Stores editor-specific information such as scene rectangle, view center, zoom, interaction mode, and floating toolbar position.

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
  },
  "zoomPercent": 100.0,
  "mode": "select",
  "toolbarPosition": {
    "x": 12,
    "y": 12
  }
}
```

| Field | Meaning |
|---|---|
| `sceneRect` | Model-scene workspace bounds used by the editor. |
| `viewCenter` | Scene coordinate centered in the visible model view. |
| `zoomPercent` | Model view zoom percentage restored when the project is reopened. |
| `mode` | Current model-view interaction mode, usually `select` or `multiselect`. |
| `toolbarPosition` | Floating model-view toolbar position in viewport coordinates. |

The `editor` block is not simulator model data. It should not be interpreted by simulator exporters as topology, timing, or configuration input.

## Compatibility

Project validation requires:

- `schemaVersion` matches `SCHEMA_VERSION`.
- `components` exists and is a list.
- `links` exists and is a list.

Unsupported schemas should fail clearly.

Older `.fse` files that lack `projectSettings` may still be interpreted using `activeTarget` compatibility logic.


## Composite component file format (`.fcc`)

Reusable composite definitions can be shared with other FUSE users as `.fcc` files. The `.fcc` file is JSON and is separate from the editable `.fse` project format.

```json
{
  "kind": "fuse.composite-component",
  "schema_version": "0.1.0",
  "definition": {
    "composite_id": "6cb322e5-cfae-40f9-b6e9-example",
    "name": "Cache Cluster",
    "description": "Reusable cache cluster",
    "icon_path": "icons/cache-cluster.png",
    "mini_model": {},
    "port_mappings": [],
    "schema_version": "0.1.0",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00"
  }
}
```

Importing a `.fcc` file adds the definition to the local `core_composite_components` table. Exporting writes one reusable definition, not a full project.
