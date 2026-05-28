# Example: Write a Simple Plugin

This example creates a minimal plugin named `toy`. It shows component metadata, parameter metadata, port metadata, target/version metadata, and the basic path from plugin catalog entry to drag/drop component instance.

## 1. Create directories

```bash
mkdir -p fuse/plugins/community/toy/tests
touch fuse/plugins/community/toy/__init__.py
```

## 2. Add `plugin.toml`

Create:

```text
fuse/plugins/community/toy/plugin.toml
```

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

Create:

```text
fuse/plugins/community/toy/plugin.py
```

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
class ToyPlugin:
    plugin_id: str = "toy"
    name: str = "Toy Plugin"

    def initialize_database(self, conn) -> None:
        # This toy plugin uses built-in metadata, so no tables are required.
        return None

    def bootstrap_database(self) -> None:
        return None

    def list_targets(self):
        return [
            FrameworkTarget(
                plugin_id=self.plugin_id,
                target_id="toy-1.0",
                display_name="ToySim 1.0",
                framework_name="ToySim",
                framework_version="1.0",
                is_default=True,
            )
        ]

    def load_palette_items(self, target_id: str | None = None):
        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id="toy_component",
                display_name="ToySim.ToyComponent (Component)",
                type_name="ToyComponent",
                element_name="ToySim",
                category="Examples",
                description="A toy component.",
                raw_kind="Component",
                target_id=target_id or "toy-1.0",
                target_label="ToySim 1.0",
                framework_version="1.0",
            )
        ]

    def load_item_details(self, item_id: str, target_id: str | None = None):
        item = self.load_palette_items(target_id=target_id)[0]
        return ItemDetails(
            palette_item=item,
            connectors=[
                ConnectorDefinition(
                    name="in",
                    description="Input port.",
                    interface="toy.signal",
                ),
                ConnectorDefinition(
                    name="out",
                    description="Output port.",
                    interface="toy.signal",
                ),
            ],
            properties=[
                PropertyDefinition(
                    name="clock",
                    description="Clock frequency.",
                    default_value="1GHz",
                    required=True,
                    value_type="string",
                ),
                PropertyDefinition(
                    name="width",
                    description="Data width in bits.",
                    default_value="32",
                    required=True,
                    value_type="int",
                ),
            ],
        )

    def validate_toolchain(self, plugin_settings):
        return True, "Toy plugin does not require an external toolchain."

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        return None


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

## 5. Initialize the database

```bash
.venv/bin/python - <<'PY'
from fuse.core.persistence.db_access import ensure_database_ready

ensure_database_ready(run_plugin_bootstrap=True)
PY
```

## 6. Launch FUSE

```bash
fuse-mod
```

Then:

1. Open **File -> Project Settings**.
2. Enable the Toy plugin.
3. Select `ToySim 1.0` as the target/catalog.
4. Make Toy the active framework/plugin.
5. Click OK or Apply.

The component palette should include:

```text
ToySim.ToyComponent (Component)
```

## 7. Add the toy component

Drag `ToySim.ToyComponent (Component)` from the palette into the canvas.

FUSE will:

- Serialize the `PaletteItem` into a `ComponentDefinition` drag payload.
- Convert the drop point into model coordinates.
- Create a component instance.
- Generate a name such as `ToyComponent_1`.
- Render ports named `in` and `out`.
- Show parameters in the properties panel.

## 8. Edit properties

Select the component and edit:

```text
Name       toy0
clock *    2GHz
width *    64
```

Because `width` has default value `32`, FUSE treats it as integer-like and rejects non-integer edits.

## 9. Connect ports

Add a second toy component and connect:

```text
toy0.out -> toy1.in
```

When prompted, enter latency:

```text
1ns
```

## 10. Save the project

Use:

```text
File -> Save As...
```

The `.fse` file stores component instances and parameter overrides, not the entire Toy plugin catalog.

## 11. Add tests

At minimum, add plugin tests for:

- Plugin discovery.
- `list_targets()`.
- `load_palette_items(target_id=...)`.
- `load_item_details(item_id, target_id=...)`.
- Parameter metadata.
- Port metadata.

Example:

```python
def test_toy_plugin_exposes_component_details():
    from fuse.plugins.community.toy.plugin import ToyPlugin

    plugin = ToyPlugin()
    target = plugin.list_targets()[0]
    items = plugin.load_palette_items(target_id=target.target_id)
    details = plugin.load_item_details(items[0].item_id, target_id=target.target_id)

    assert details.palette_item.type_name == "ToyComponent"
    assert [port.name for port in details.connectors] == ["in", "out"]
    assert any(prop.name == "clock" and prop.required for prop in details.properties)
```
