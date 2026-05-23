# Plugin Manifest Reference

Plugins are described by `plugin.toml`.

## Location

Community plugins live under:

```text
fuse/plugins/community/<plugin_id>/plugin.toml
```

## Example

```toml
[plugin]
id = "sst"
name = "FUSE SST Plugin"
version = "0.1.0"
vendor = "PKB Research Labs, LLC"
license = "GPL-3.0-or-later"
type = "community"
description = "SST components, validation, and model generation support for FUSE."

[compatibility]
fuse_plugin_api = ">=1.0,<2.0"
fuse_app = ">=0.1,<1.0"

[entry_points]
register = "fuse.plugins.community.sst.plugin:register_plugin"

[capabilities]
component_providers = true
exporters = true
validators = true
importers = false
simulation_runners = false
property_editors = true
```

## `[plugin]`

| Field | Description |
|---|---|
| `id` | Stable plugin ID. |
| `name` | Human-readable name. |
| `version` | Plugin version. |
| `vendor` | Plugin author/vendor. |
| `license` | Plugin license. |
| `type` | `community`, `commercial`, or other policy-defined category. |
| `description` | Short description. |

## `[compatibility]`

Defines supported FUSE versions and plugin API versions.

## `[entry_points]`

`register` must point to a callable using the form:

```text
module.path:function_name
```

The function must return a plugin object.

## `[capabilities]`

Documents plugin capabilities. The runtime may use these fields for UI and validation in the future.
