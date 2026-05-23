# Example: Write a Simple Plugin

This example creates a minimal plugin named `toy`.

## 1. Create directories

```bash
mkdir -p fuse/plugins/community/toy/tests
touch fuse/plugins/community/toy/__init__.py
```

## 2. Add `plugin.toml`

```toml
[plugin]
id = "toy"
name = "Toy Plugin"
version = "0.1.0"
vendor = "Example"
license = "GPL-3.0-or-later"
type = "community"
description = "Toy plugin for FUSE examples."

[compatibility]
fuse_plugin_api = ">=1.0,<2.0"
fuse_app = ">=0.1,<1.0"

[entry_points]
register = "fuse.plugins.community.toy.plugin:register_plugin"

[capabilities]
component_providers = true
exporters = false
validators = false
importers = false
simulation_runners = false
property_editors = true
```

## 3. Add `plugin.py`

```python
from dataclasses import dataclass

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)


@dataclass
class ToyPlugin:
    plugin_id: str = "toy"
    name: str = "Toy Plugin"

    def initialize_database(self, conn) -> None:
        return None

    def bootstrap_database(self) -> None:
        return None

    def load_palette_items(self):
        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id="toy_component",
                display_name="Toy Component",
                type_name="ToyComponent",
                category="Examples",
                description="A toy component.",
            )
        ]

    def load_item_details(self, item_id: str):
        item = self.load_palette_items()[0]
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
    return ToyPlugin()
```

## 4. Test discovery

```bash
.venv/bin/python - <<'PY'
from fuse.core.plugin_runtime.manager import load_enabled_plugins

for plugin in load_enabled_plugins():
    print(plugin.plugin_id, plugin.name)
PY
```

You should see `toy`.

## 5. Launch FUSE

```bash
fuse-mod
```

The component palette should include `Toy Component`.
