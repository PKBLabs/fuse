# Plugin Development Guide

This guide shows how to create a basic FUSE plugin.

## Directory layout

A community plugin lives under:

```text
fuse/plugins/community/myplugin/
    __init__.py
    plugin.py
    plugin.toml
    README.md
    tests/
```

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

## Plugin class

Create `plugin.py`:

```python
from dataclasses import dataclass

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT ''
            )
        """)

    def bootstrap_database(self) -> None:
        # Optional heavier setup.
        return None

    def load_palette_items(self) -> list[PaletteItem]:
        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id="example",
                display_name="Example Component",
                type_name="ExampleComponent",
                category="Example",
                description="A plugin-provided example component.",
            )
        ]

    def load_item_details(self, item_id: str) -> ItemDetails:
        item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=item_id,
            display_name="Example Component",
            type_name="ExampleComponent",
            category="Example",
        )

        return ItemDetails(
            palette_item=item,
            connectors=[
                ConnectorDefinition(name="in"),
                ConnectorDefinition(name="out"),
            ],
            properties=[
                PropertyDefinition(
                    name="clock",
                    description="Clock frequency.",
                    default_value="1GHz",
                    required=True,
                )
            ],
        )


def register_plugin():
    return MyPlugin()
```

## Plugin database tables

Use a plugin-specific table prefix:

```text
myplugin_components
myplugin_parameters
myplugin_import_runs
```

Do not create generic tables named `components` or `parameters` in core.

## Testing a plugin

Place tests under:

```text
fuse/plugins/community/myplugin/tests/
```

Add the plugin test directory to `pytest.ini`.

## Plugin development checklist

- `plugin.toml` has the correct `register` path.
- `plugin.py` exposes `register_plugin()`.
- Plugin object has `plugin_id` and `name`.
- Plugin database tables use a plugin prefix.
- Plugin returns valid `PaletteItem` objects.
- Plugin returns valid `ItemDetails` objects.
- Tests cover plugin discovery and item loading.
