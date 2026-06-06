# Project Files

FUSE project files use the `.fse` extension.

A project file stores the editor model and project settings. It does **not** store full plugin-generated catalogs. Plugin catalog data remains in the local database and is regenerated, imported, or provided by plugins separately.

## What is saved

A `.fse` project saves:

- Project name.
- Schema version.
- Project settings.
- Active plugin ID.
- Enabled plugin settings.
- Selected framework target/catalog per plugin.
- Toolchain settings, excluding secrets.
- Component instances.
- Composite instance identity and instance-local composite edit state.
- Instance names.
- Plugin ID for each component.
- Target/catalog metadata for each component.
- Component type metadata needed to restore the object.
- Instance parameters.
- Instance icon paths.
- Canvas position.
- Links.
- Link endpoints.
- Link latency.
- Editor metadata such as scene rectangle and view center.

## What is not saved

A project file does not store the full plugin catalog, such as every SST component returned by `sst-info`. It also does not embed every local composite definition; reusable composite templates live in the local database and can be shared separately as `.fcc` files. A project may store instance-local composite mini-model state for placed composite instances.

That data belongs to plugin-specific database tables such as:

```text
sst_framework_versions
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
gem5_framework_versions
```

Project files also must not store secrets such as passwords, private keys, or SSH passphrases. Remote SSH execution should rely on the user's system `ssh`, `~/.ssh/config`, and `ssh-agent`.

## Minimal structure

A project file has this high-level shape:

```json
{
  "schemaVersion": "0.1.0",
  "project": {
    "name": "Example Model",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  "projectSettings": {},
  "pluginSettings": {},
  "activeTarget": {},
  "components": [],
  "links": [],
  "editor": {}
}
```

## Project settings

Project settings define the active plugin and plugin-specific target/toolchain settings.

```json
{
  "projectSettings": {
    "projectName": "Example Model",
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
}
```

For SSH-backed projects, `backend` is `ssh` and fields such as `host`, `port`, `username`, and `remoteSetupCommand` may be populated. Authentication secrets should not be saved.

## Active target compatibility field

`activeTarget` is retained for compatibility and quick lookup:

```json
{
  "activeTarget": {
    "pluginId": "sst",
    "targetId": "1"
  }
}
```

The canonical project setting is `projectSettings`, but older `.fse` files may rely on `activeTarget`.

## Example component entry

```json
{
  "id": 1,
  "instanceName": "cache_1",
  "pluginId": "sst",
  "targetId": "1",
  "targetLabel": "SST 15.1.2",
  "frameworkVersion": "15.1.2",
  "componentId": "42",
  "element": "memHierarchy",
  "name": "Cache",
  "isSubcomponent": 0,
  "category": "MEMORY COMPONENT",
  "interface": "",
  "iconPath": "core/resources/media/arch_component_icons/memory_cache.png",
  "parameters": {
    "cache_frequency": "2GHz",
    "cache_size": "32KiB",
    "associativity": "8"
  },
  "position": {
    "x": 100.0,
    "y": 150.0
  }
}
```

Important component fields:

| Field | Meaning |
|---|---|
| `id` | Model-scene node ID. |
| `instanceName` | User-editable unique instance name. |
| `pluginId` | Plugin that owns the component type. |
| `targetId` | Framework target/catalog ID. |
| `targetLabel` | User-facing target/catalog label. |
| `frameworkVersion` | Framework version associated with this component metadata. |
| `componentId` | Plugin-local component/catalog ID. |
| `element` | Framework element/namespace/family. |
| `name` | Component type name. |
| `isSubcomponent` | Whether this was a subcomponent type. |
| `category` | Component category. |
| `interface` | Plugin/framework interface string. |
| `iconPath` | Icon used for this instance. |
| `parameters` | User overrides for plugin-defined parameters. |
| `position` | Model-scene coordinates. |
| `isComposite` | Whether this component entry is a FUSE composite instance. |
| `compositeId` | Composite template ID for composite instances. |
| `compositeInstance` | Optional instance-local composite mini-model state. |

## Example composite component entry

Composite instances are saved as component entries with core-owned composite identity. If a placed instance has instance-local edits, the `compositeInstance` block stores that mini-model state, including exposed/hidden port mappings.

```json
{
  "id": 7,
  "instanceName": "CacheCluster_1",
  "pluginId": "core",
  "targetId": "fuse-composite",
  "componentId": "6cb322e5-cfae-40f9-b6e9-example",
  "element": "Composite Components",
  "name": "CacheCluster",
  "isComposite": 1,
  "compositeId": "6cb322e5-cfae-40f9-b6e9-example",
  "parameters": {},
  "position": {
    "x": 300.0,
    "y": 200.0
  },
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

Composite instances are expanded before simulator validation/export. The simulator-specific export should contain ordinary SST or gem5 objects, not FUSE composite nodes.

## Example link entry

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
    "componentName": "cache0",
    "port": "in"
  }
}
```

Important link fields:

| Field | Meaning |
|---|---|
| `id` | Model link ID. |
| `name` | User-editable unique link name. |
| `latency` | Link latency value. |
| `type` | Link type, currently usually `point_to_point`. |
| `source.nodeId` | Source component node ID. |
| `source.componentName` | Source component instance name at save time. |
| `source.port` | Source port name. |
| `target.nodeId` | Target component node ID. |
| `target.componentName` | Target component instance name at save time. |
| `target.port` | Target port name. |

## Editor metadata

The `editor` object stores view-related metadata:

```json
{
  "editor": {
    "sceneRect": {
      "x": 0.0,
      "y": 0.0,
      "width": 2000.0,
      "height": 1500.0
    },
    "viewCenter": {
      "x": 400.0,
      "y": 300.0
    }
  }
}
```

This is editor state, not simulator model state.

## Compatibility

Project loading validates the schema version. Files with unsupported schema versions fail with a clear error.

When project schema changes, update:

- `SCHEMA_VERSION` in `fuse/core/model/models.py`.
- `validate_project_dict()`.
- Project save/load tests.
- Migration or compatibility code if older projects must remain loadable.

## Relationship to simulator export files

The `.fse` format is FUSE's editable project format. Simulator exports are generated artifacts.

For example:

```text
my_model.fse       # editable FUSE project
my_model.sst.json  # generated SST JSON configuration
```

Do not hand-edit generated simulator exports and expect FUSE to load them as projects. Reopen the `.fse` file, edit the model in FUSE, and export again.

## Project lifecycle prompts

FUSE protects unsaved work during project lifecycle actions. When the current model is dirty and the user starts a New, Open, or Exit action, FUSE asks whether to save first, continue without saving, or cancel the requested action.

The choices behave as follows:

- **Save & New/Open/Exit** saves the current `.fse` project first. If saving fails or the user cancels Save As, the requested action is cancelled and the model remains open.
- **Don't Save** discards the unsaved changes and continues with the requested action.
- **Cancel** leaves the current model open without saving or discarding changes.

Save As appends the `.fse` extension when the user omits it. If Save As fails, FUSE restores the previously active project path and leaves the model marked as unsaved.


## Composite definition files

Reusable composite templates can be exported as `.fcc` files. A `.fcc` file stores one composite definition and can be imported into another local FUSE database. It is not a full project file and does not replace `.fse`.

Use **Edit -> Manage Composite Components...** to import, export, edit, or delete local composite definitions. `.fcc` files preserve exposed/hidden composite port state so imported templates keep the same default public interface.
