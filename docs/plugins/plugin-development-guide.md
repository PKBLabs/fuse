# Plugin Development Guide

This guide explains how to create a FUSE plugin that contributes component metadata to the editor. It covers plugin layout, manifests, framework targets, component metadata, parameter metadata, port metadata, compatibility metadata, database ownership, and tests.

## Plugin responsibilities

A plugin is responsible for translating a simulator/framework-specific world into the generic FUSE editor API.

A typical component-provider plugin should:

1. Provide a `plugin.toml` manifest.
2. Expose a `register_plugin()` entry point.
3. Return a plugin object with `plugin_id` and `name`.
4. Create plugin-owned database tables if needed.
5. List supported framework targets/catalogs.
6. Return palette items for the selected target.
7. Return item details containing ports, parameters, and optional statistics.
8. Validate local or remote toolchains when the project asks it to.
9. Keep simulator-specific logic inside the plugin.

## Directory layout

Community plugins live under:

```text
fuse/plugins/community/myplugin/
    __init__.py
    plugin.py
    plugin.toml
    README.md
    tests/
```

SST-specific tests belong in the SST plugin directory. gem5-specific tests belong in the gem5 plugin directory. Generic application behavior belongs in `fuse/tests/`.

## Manifest

Create `plugin.toml`:

```toml
[plugin]
id = "myplugin"
name = "FUSE MyPlugin"
version = "0.1.0"
vendor = "Example Vendor"
license = "GPL-3.0-or-later"
type = "community"
description = "Example FUSE plugin."

[compatibility]
fuse_plugin_api = ">=1.0,<2.0"
fuse_app = ">=0.1,<1.0"

[entry_points]
register = "fuse.plugins.community.myplugin.plugin:register_plugin"

[capabilities]
component_providers = true
exporters = false
validators = false
importers = false
simulation_runners = false
property_editors = true
```

### Invalid manifests

The plugin runtime scans:

```text
fuse/plugins/community/*/plugin.toml
```

Invalid TOML manifests are skipped with a diagnostic rather than crashing the whole application. A manifest without `entry_points.register` is also skipped.

## Framework targets

If your plugin supports multiple simulator/framework versions, implement `list_targets()`.

```python
from fuse.plugin_api.interfaces import FrameworkTarget


def list_targets(self):
    return [
        FrameworkTarget(
            plugin_id=self.plugin_id,
            target_id="mysim-1.0",
            display_name="MySim 1.0",
            framework_name="MySim",
            framework_version="1.0",
            is_default=True,
        ),
        FrameworkTarget(
            plugin_id=self.plugin_id,
            target_id="mysim-2.0",
            display_name="MySim 2.0",
            framework_name="MySim",
            framework_version="2.0",
            is_default=False,
        ),
    ]
```

Project Settings stores the selected target. The component palette passes that target back to the plugin when loading palette items and item details.

## Component metadata

The component palette is populated from `PaletteItem` objects.

```python
from fuse.plugin_api.interfaces import PaletteItem

PaletteItem(
    plugin_id="myplugin",
    item_id="router",
    display_name="MySim.Router (Component)",
    type_name="Router",
    element_name="MySim",
    category="Network",
    description="Router component.",
    icon_path="core/resources/media/arch_component_icons/router.png",
    raw_kind="Component",
    target_id="mysim-1.0",
    target_label="MySim 1.0",
    framework_version="1.0",
)
```

Important fields:

- `plugin_id`: owning plugin.
- `item_id`: plugin-local stable identifier.
- `display_name`: text shown in the component list.
- `type_name`: simulator/framework type.
- `element_name`: namespace/module/family.
- `category`: grouping label.
- `target_id`: selected version/catalog.
- `framework_version`: simulator/framework version.

See [Component Metadata Reference](../reference/component-metadata.md) for the full field list.

## Parameter metadata

Component parameters are returned through `PropertyDefinition` objects inside `ItemDetails`.

```python
from fuse.plugin_api.interfaces import PropertyDefinition

PropertyDefinition(
    name="clock",
    description="Clock frequency.",
    default_value="1GHz",
    required=True,
    value_type="string",
)
```

Rules:

- `name` should match the simulator/export field name when possible.
- `default_value` is displayed when the instance has no override.
- `required=True` makes core validation require a non-empty value.
- `value_type` should be accurate even if current UI validation is still simple.

## Port metadata

Ports/connectors are returned as `ConnectorDefinition` objects.

```python
from fuse.plugin_api.interfaces import ConnectorDefinition

ConnectorDefinition(
    name="in",
    description="Input link.",
    interface="mysim.link",
)
```

Rules:

- `name` is saved in link endpoints, so keep it stable.
- `interface` should carry useful simulator-specific type information.
- The current core editor supports point-to-point links; each port can be connected to at most one link.

## Full item details

`load_item_details()` returns `ItemDetails`.

```python
from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)


def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails:
    item = PaletteItem(
        plugin_id=self.plugin_id,
        item_id=item_id,
        display_name="MySim.Router (Component)",
        type_name="Router",
        element_name="MySim",
        category="Network",
        target_id=target_id or "mysim-1.0",
        target_label="MySim 1.0",
        framework_version="1.0",
    )

    return ItemDetails(
        palette_item=item,
        connectors=[
            ConnectorDefinition(name="in", interface="mysim.link"),
            ConnectorDefinition(name="out", interface="mysim.link"),
        ],
        properties=[
            PropertyDefinition(name="clock", default_value="1GHz", required=True),
            PropertyDefinition(name="num_ports", default_value="4", required=True, value_type="int"),
        ],
    )
```

## Complete minimal plugin

```python
from dataclasses import dataclass

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    FrameworkTarget,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)


@dataclass
class MyPlugin:
    plugin_id: str = "myplugin"
    name: str = "FUSE MyPlugin"

    def initialize_database(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS myplugin_components (
                id TEXT PRIMARY KEY,
                type_name TEXT NOT NULL,
                description TEXT DEFAULT ''
            )
        """)

    def bootstrap_database(self) -> None:
        return None

    def list_targets(self) -> list[FrameworkTarget]:
        return [
            FrameworkTarget(
                plugin_id=self.plugin_id,
                target_id="mysim-1.0",
                display_name="MySim 1.0",
                framework_name="MySim",
                framework_version="1.0",
                is_default=True,
            )
        ]

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id="router",
                display_name="MySim.Router (Component)",
                type_name="Router",
                element_name="MySim",
                category="Network",
                description="A plugin-provided router component.",
                raw_kind="Component",
                target_id=target_id or "mysim-1.0",
                target_label="MySim 1.0",
                framework_version="1.0",
            )
        ]

    def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails:
        item = self.load_palette_items(target_id=target_id)[0]

        return ItemDetails(
            palette_item=item,
            connectors=[
                ConnectorDefinition(name="in", interface="mysim.link"),
                ConnectorDefinition(name="out", interface="mysim.link"),
            ],
            properties=[
                PropertyDefinition(
                    name="clock",
                    description="Clock frequency.",
                    default_value="1GHz",
                    required=True,
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

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        return True, "No external toolchain is required for this example plugin."

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        return None


def register_plugin():
    return MyPlugin()
```

## How the user adds your component

After your plugin returns palette items:

1. The user opens Project Settings.
2. The user enables your plugin and selects a target/catalog.
3. FUSE asks your plugin for `load_palette_items(target_id=...)`.
4. The palette shows `display_name`.
5. The user drags the item to the model canvas.
6. FUSE creates a component instance using the item's metadata.
7. FUSE asks your plugin for `load_item_details(...)` to render ports and show parameters.

## Compatibility and versioning

Use two compatibility layers:

1. Manifest compatibility tells FUSE whether the plugin itself is compatible with the FUSE app/plugin API.
2. Framework target compatibility tells the project which simulator/framework version the component catalog belongs to.

Do not mix these concepts. A plugin can be compatible with FUSE while exposing multiple incompatible simulator versions as separate targets.

## Database ownership

Use plugin-specific table names:

```text
myplugin_components
myplugin_parameters
myplugin_import_runs
```

Do not create generic tables named `components`, `parameters`, or `ports` in core.

Database-backed plugins should include the target/framework version in their schema so multiple catalogs can coexist.

## Toolchain validation

Plugins that depend on external tools should validate them through project settings. The core project model supports local and SSH-backed execution environments.

A plugin validation method should return:

```python
(True, "Validated MySim 1.0 toolchain.")
```

or:

```python
(False, "mysim-info was not found at the configured path.")
```

Do not raise exceptions for normal user configuration problems.

## Testing a plugin

Place plugin-specific tests under:

```text
fuse/plugins/community/myplugin/tests/
```

Test at least:

- Manifest discovery.
- Database table initialization.
- Target listing.
- Palette item loading.
- Item detail loading.
- Parameter metadata.
- Port metadata.
- Toolchain validation errors.
- Import/export behavior, if provided.

External-tool integration tests should use a marker, such as `mysim_live`, so dependency-light CI can skip them.

## Plugin development checklist

- `plugin.toml` has the correct `entry_points.register` path.
- `register_plugin()` returns a plugin instance.
- Plugin object has `plugin_id` and `name`.
- `plugin_id` matches the manifest ID.
- Plugin database tables use a plugin prefix.
- Framework targets are returned for versioned catalogs.
- Palette items include target/version metadata.
- Item details include parameter and port metadata.
- Required parameters are marked with `required=True`.
- Port names are stable.
- Toolchain validation returns user-friendly messages.
- Tests cover plugin discovery and metadata loading.
