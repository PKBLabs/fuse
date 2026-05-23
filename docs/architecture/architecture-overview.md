# Architecture Overview

FUSE is organized around a generic application core plus simulator/modeling-framework plugins.

## Major layers

```text
app/
    Main window, splash screen, About dialog, menu wiring.

core/
    Simulator-agnostic editor logic, UI widgets, routing, persistence,
    validation, resources, and plugin runtime.

plugin_api/
    Public plugin-facing dataclasses and protocol definitions.

plugins/
    Community and future third-party plugins.
```

## Dependency direction

The intended direction is:

```text
app
  -> core
      -> plugin_api
      -> plugin_runtime
          -> plugins

plugins
  -> plugin_api
  -> core persistence utilities as needed
```

Core should not directly import SST-specific or gem5-specific implementation modules. Core discovers plugins through manifests and calls plugin methods through generic interfaces.

## Core responsibilities

Core owns:

- Qt graphics items and model canvas behavior.
- Project file save/load.
- Generic validation framework.
- Plugin discovery/runtime.
- Generic model dataclasses.
- Routing algorithms.
- Generic resources such as architecture component icons.
- Core database tables such as `core_plugins` and `core_schema_migrations`.

## Plugin responsibilities

Plugins own framework-specific behavior.

The SST plugin owns:

- `sst-info` execution.
- SST parser logic.
- `sst_*` database tables.
- SST metadata translation into generic palette and item details.
- SST-specific icon mapping.

The gem5 plugin currently exists as a community plugin placeholder and is expected to grow into gem5-specific discovery, metadata import, validation, and export support.

## Startup flow

1. `fuse.app.main` imports and calls `fuse.app.app.main()`.
2. Qt application is created.
3. Splash screen is displayed.
4. `MainWindow` is constructed.
5. `ensure_database_ready()` initializes core database tables.
6. Plugin runtime discovers manifests under `plugins/community/*/plugin.toml`.
7. Enabled plugins initialize plugin-specific schemas.
8. The component palette loads plugin-provided items.
9. The main window is shown.

## Data flow

```text
Plugin-specific metadata
    -> plugin database tables
    -> plugin load_palette_items/load_item_details
    -> core ComponentDefinition
    -> component palette
    -> model canvas
    -> project save/load
```

## Why core avoids plugin-specific catalog tables

Terms like `elements`, `components`, `ports`, `parameters`, `statistics`, and `subcomp_slots` are SST-shaped concepts. They are stored in SST-prefixed tables, not generic core tables.

Core interacts with plugins through generic objects:

- `PaletteItem`
- `ConnectorDefinition`
- `PropertyDefinition`
- `ItemDetails`

This keeps FUSE open to other ecosystems such as gem5, Simulink, RTL tooling, and custom model libraries.
