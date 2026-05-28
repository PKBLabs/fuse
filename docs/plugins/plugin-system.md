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

Invalid TOML manifests or broken entry points are skipped with diagnostics so one broken plugin does not prevent the whole application from starting.

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
list_all_targets()
load_all_palette_items(plugin_id=None, target_id=None)
load_item_details(plugin_id, item_id, target_id=None)
```

## Plugin methods

A plugin may implement:

```python
def initialize_database(self, conn) -> None: ...
def bootstrap_database(self) -> None: ...
def list_targets(self) -> list[FrameworkTarget]: ...
def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]: ...
def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails: ...
def validate_toolchain(self, plugin_settings) -> tuple[bool, str]: ...
def import_metadata_for_toolchain(self, plugin_settings) -> None: ...
```

`initialize_database()` should be lightweight and safe to call on startup/setup.

`bootstrap_database()` may be heavier and is used for setup/import actions such as running `sst-info`.

`list_targets()` lets the plugin expose versioned framework catalogs.

`load_palette_items(target_id=...)` lets the project filter the palette by selected target.

`load_item_details(item_id, target_id=...)` provides parameters and ports for the selected component and target.

`validate_toolchain(...)` lets a plugin validate local or SSH toolchains from Project Settings.

## Plugin API objects

The plugin API exposes generic editor data structures:

- `FrameworkTarget`
- `PaletteItem`
- `ConnectorDefinition`
- `PropertyDefinition`
- `ItemDetails`

Plugins translate simulator-specific metadata into these generic objects.

See [Plugin API Reference](../reference/plugin-api.md) and [Component Metadata Reference](../reference/component-metadata.md).

## Project Settings integration

Project Settings stores per-project plugin configuration:

- Enabled/disabled plugin state.
- Active plugin ID.
- Selected target/catalog ID.
- Framework version label.
- Toolchain settings.

This allows different projects to use different simulator versions.

Example:

```text
Project A: SST 15.1.2
Project B: SST 16.0.0
Project C: gem5 25.1.0.1
```

## Plugin database ownership

Plugins should own plugin-prefixed database tables.

Examples:

```text
sst_*
gem5_*
simu_*
```

Core should not query plugin-specific tables directly except through plugin APIs or dedicated plugin modules.

## Metadata source patterns

Plugins may provide metadata from:

- Built-in Python dictionaries.
- Plugin-owned SQLite tables.
- Imported simulator/tool output.
- Files in a future plugin metadata format.
- Remote toolchain discovery over SSH.

Regardless of source, the plugin should expose metadata through the generic plugin API objects.

## Community plugins

Community plugins included with FUSE currently include:

- SST
- gem5

## Broken plugin behavior

The plugin runtime should skip broken plugins rather than crashing the whole app. A broken plugin should produce a diagnostic message and allow other plugins to load.

## Testing expectations

Core tests should cover plugin discovery and generic behavior. Plugin-specific tests should live inside the plugin directory and cover simulator-specific parsing, import, export, validation, and live toolchain integration.
