# Project Files

FUSE project files use the `.fse` extension.

A project file stores the editor model, not plugin-generated catalogs. Plugin catalog data remains in the local database and is regenerated or imported separately.

## What is saved

A `.fse` project saves:

- Project name.
- Schema version.
- Component instances.
- Instance names.
- Plugin ID for each component.
- Component type metadata needed to restore the object.
- Instance parameters.
- Instance icon paths.
- Canvas position.
- Links.
- Link endpoints.
- Link latency.
- Editor metadata such as scene rectangle and view center.

## What is not saved

A project file does not store the full plugin catalog, such as every SST component returned by `sst-info`.

That data belongs to plugin-specific database tables such as:

```text
sst_elements
sst_components
sst_parameters
sst_ports
sst_statistics
sst_subcomp_slots
```

## Minimal structure

A project file has this high-level shape:

```json
{
  "schemaVersion": "0.1.0",
  "project": {
    "name": "Example Model",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  "components": [],
  "links": [],
  "editor": {}
}
```

## Example component entry

```json
{
  "id": 1,
  "instanceName": "cpu0",
  "pluginId": "sst",
  "componentId": "42",
  "element": "memHierarchy",
  "name": "Cache",
  "isSubcomponent": 0,
  "category": "MEMORY COMPONENT",
  "interface": "",
  "iconPath": "core/resources/media/arch_component_icons/memory_cache.png",
  "parameters": {
    "clock": "2GHz"
  },
  "position": {
    "x": 100.0,
    "y": 150.0
  }
}
```

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

## Compatibility

Project loading validates the schema version. Files with unsupported schema versions should fail with a clear error.

When project schema changes, update:

- `SCHEMA_VERSION` in `fuse/core/model/models.py`.
- `validate_project_dict()`.
- Project save/load tests.
- Migration or compatibility code if older projects must remain loadable.
