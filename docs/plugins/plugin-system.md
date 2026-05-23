# Plugin System

FUSE uses plugins to provide simulator- or framework-specific catalog data and behavior while keeping the core editor generic.

## Plugin discovery

Plugin discovery is handled by:

```text
fuse/core/plugin_runtime/manager.py
```

The plugin runtime scans:

```text
fuse/plugins/community/*/plugin.toml
```

Each manifest provides an entry point:

```toml
[entry_points]
register = "fuse.plugins.community.sst.plugin:register_plugin"
```

The runtime imports the function and calls it. The function returns a plugin object.

## LoadedPlugin

The plugin manager wraps plugin instances in `LoadedPlugin` objects containing:

- `plugin_id`
- `name`
- `root`
- `manifest`
- `instance`

## Core-to-plugin calls

Core currently calls plugin methods through the manager:

```python
load_enabled_plugins()
load_all_palette_items()
load_item_details(plugin_id, item_id)
```

## Plugin methods

A plugin may implement:

```python
def initialize_database(self, conn) -> None:
    ...

def bootstrap_database(self) -> None:
    ...

def load_palette_items(self) -> list[PaletteItem]:
    ...

def load_item_details(self, item_id: str) -> ItemDetails:
    ...
```

`initialize_database()` should be lightweight and safe to call on startup.

`bootstrap_database()` may be heavier and is used for setup/import actions such as running `sst-info`.

## Plugin API objects

The plugin API exposes generic editor data structures:

- `PaletteItem`
- `ConnectorDefinition`
- `PropertyDefinition`
- `ItemDetails`

Plugins translate simulator-specific metadata into these generic objects.

## Plugin database ownership

Plugins should own plugin-prefixed database tables.

Examples:

```text
sst_*
gem5_*
simu_*
```

Core should not query plugin-specific tables directly.

## Community plugins

Community plugins included with FUSE currently include:

- SST
- gem5

## Broken plugin behavior

The plugin runtime should skip broken plugins rather than crashing the whole app. A broken plugin should produce a diagnostic message and allow other plugins to load.
