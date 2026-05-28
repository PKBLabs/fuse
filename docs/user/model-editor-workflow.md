# Model Editor Workflow

This guide describes the basic end-to-end workflow for building a model in FUSE: creating/opening a project, selecting a framework target, adding components, editing properties, connecting ports, validating the model, and saving/exporting.

## 1. Start FUSE

```bash
fuse-mod
```

The splash screen appears, then the main editor opens.

The main window contains:

- A left component palette.
- A central model canvas.
- A right properties panel.
- Menus for project operations, validation, and export.

## 2. Create or open a project

Use:

```text
File -> New Project
```

or:

```text
File -> Open Project
```

A FUSE project stores project-specific settings and the user's model. Project settings are independent from other projects, so one project can target SST 15 while another targets SST 16 or gem5 25.

## 3. Configure Project Settings

Open:

```text
File -> Project Settings
```

The Project Settings dialog contains:

- Project name.
- Active framework/plugin.
- Plugin enablement checkboxes.
- Target version/catalog selectors for enabled plugins.
- Shared execution environment settings.
- Local or remote SSH toolchain configuration.
- Toolchain validation.

### Plugin enablement

Each plugin has an `Enable <plugin> for this project` checkbox. Only enabled plugins participate in the project.

When a plugin is enabled, FUSE shows that plugin's target version/catalog selector. For example:

```text
Enable SST for this project
Target version/catalog: SST 15.1.2
```

or:

```text
Enable gem5 for this project
Target version/catalog: gem5 25.1.0.1
```

### Active plugin

The active plugin controls the component palette and the default validation/export context.

For example, if the active plugin is SST and the selected target is SST 15.1.2, the palette shows only SST catalog items available for that target.

### Toolchain location

The execution environment is shared by all enabled plugins in the current project. For now, FUSE assumes enabled simulator toolchains are either all local or all reachable through one SSH environment.

Supported modes:

```text
Local machine
Remote over SSH
```

For local toolchains, use **Discover Local Tools** to find common binaries such as `sst`, `sst-info`, or `gem5.opt`. If discovery cannot find a tool, enter the full executable path manually.

For remote SSH toolchains, FUSE uses the system `ssh` client with `BatchMode=yes`. Use `~/.ssh/config`, SSH keys, and/or `ssh-agent`; do not store passwords or private keys in project files.

### Toolchain validation

Use:

```text
Validate Enabled Toolchains
```

FUSE checks all enabled plugins against the configured execution environment. Validation verifies that required commands are reachable and that the detected simulator version is compatible with the selected project target.

Version validation is compatibility-oriented rather than exact-CI-tag-oriented. For example, a project targeting SST 15 can accept a compatible SST 15.x installation while rejecting SST 16.x.

## 4. Verify component metadata is loaded

The component palette should list components from the selected active plugin and target.

For SST, metadata is imported from `sst-info` into the local database. If the palette is empty, check that:

- SST Core and SST Elements are installed.
- `sst-info` is reachable locally or through the configured SSH environment.
- The selected SST target has been imported into the FUSE database.
- The project is using the expected active plugin and target.

For gem5, the current community plugin provides built-in catalog metadata for supported gem5 objects.

## 5. Add components to the model

Drag a component from the palette and drop it on the canvas.

When a drop occurs, FUSE:

1. Reads the component metadata from the drag payload.
2. Converts the drop location from view coordinates into model scene coordinates.
3. Creates a component instance at that model coordinate.
4. Generates a unique default instance name.
5. Adds the instance to the scene/model outline.
6. Marks the model as changed/dirty.

Example default names:

```text
Cache_1
Cache_2
TimingSimpleCPU_1
SystemXBar_1
```

The base name comes from the component type. FUSE increments a numeric suffix until the instance name is unique in the model.

## 6. Understand drag/drop placement

FUSE stores component positions in model-scene coordinates, not screen coordinates. This is important because the view can pan, zoom, or resize while the model coordinate system remains stable.

When a component is dropped:

```text
viewport drop position -> mapToScene(...) -> component scene position
```

The saved `.fse` project stores the resulting scene position:

```json
"position": {
  "x": 125.0,
  "y": 225.0
}
```

When the project is reopened, FUSE restores the component to that model coordinate.

## 7. Select and inspect components

Click a component instance on the canvas. The properties panel updates to show:

- Instance name.
- Kind: component or subcomponent.
- Element/category/type metadata.
- Interface metadata.
- Target/catalog label.
- Framework version.
- Icon path.
- Component parameters.

Required parameters are displayed with `*`.

Example:

```text
Parameters
  clock *       2GHz
  cache_size *  32KiB
  associativity 8
```

## 8. Edit component properties

To edit a component value:

1. Select the component.
2. Locate the row in the properties panel.
3. Edit the value column.
4. Press Enter or move focus away from the cell.

Editable component fields include:

- Instance name.
- Icon path.
- Plugin-provided parameter values.

FUSE writes parameter edits back to the selected component instance. Those values are then saved in the `.fse` file under the component's `parameters` object.

Example saved parameters:

```json
"parameters": {
  "clock": "2GHz",
  "cache_size": "32KiB",
  "associativity": "8"
}
```

Changing a property marks the model dirty so the user can save the updated project.

## 9. Parameter validation while editing

The properties panel validates basic inputs before accepting edits.

Current validation includes:

- Names cannot be empty.
- Component and link names must be unique.
- Required parameters cannot be empty.
- Latency values must end with a time unit such as `ps`, `ns`, `us`, `ms`, or `s`.
- If a parameter default looks like an integer, replacement values must parse as integers.
- If a parameter default looks like a floating-point number, replacement values must parse as numbers.

If an entered value is invalid, FUSE warns the user and restores the previous value.

## 10. Connect ports

FUSE currently supports point-to-point links.

To create a link:

1. Click an unconnected source port.
2. Click an unconnected target port.
3. Enter link latency when prompted.

Example latency:

```text
1ns
```

A link is then added to the scene and the model's link list.

Current point-to-point rule:

```text
one port -> at most one link
```

If either selected port is already connected, FUSE rejects the new connection and shows a message.

## 11. Select and edit links

Click a link line to inspect it. The properties panel shows:

- Link name.
- Link type.
- Source endpoint.
- Target endpoint.
- Latency.

Example:

```text
Object
  Name    link_1
  Type    point_to_point
  Source  cpu0.icache_port
  Target  bus0.cpu_side_ports

Parameters
  latency 1ns
```

Editable link fields include:

- Link name.
- Link latency.

## 12. Validate the model

FUSE validates common model correctness rules before save/export operations.

Current core validation checks:

- Component instance names are non-empty and unique.
- Link names are non-empty and unique.
- Required component parameters are populated.
- Link latency is populated.

When validation finds problems:

- FUSE shows a summary dialog.
- Affected rows may be highlighted in the properties panel.
- Components with validation issues may display warning markers.

Fix the listed issues, then validate/save again.

## 13. Save the project

Use:

```text
File -> Save
```

or:

```text
File -> Save As...
```

FUSE project files use the `.fse` extension.

A project file stores the model and project settings, including:

- Project name.
- Active plugin.
- Enabled plugin settings.
- Selected framework target/catalog per plugin.
- Toolchain settings, excluding secrets.
- Component instances.
- Parameter overrides.
- Component positions.
- Links and endpoints.
- Editor view metadata.

Project files do **not** store entire plugin catalogs. Catalogs are regenerated from plugin metadata, imported toolchain data, or built-in plugin records.

## 14. Export simulator-specific output

When a plugin supports export, use the appropriate export action from the application menu.

For SST, FUSE can export the active model to SST JSON configuration format. The `.fse` file remains FUSE's own project format, while the SST export is a simulator-specific generated artifact.

The basic relationship is:

```text
FUSE .fse project
  -> loaded into editor
  -> validated against selected SST target
  -> exported as SST JSON
```

## Good modeling habits

- Start by selecting the correct project target/version.
- Validate the toolchain before building a large model.
- Use meaningful instance names such as `cpu0`, `l1cache0`, `router0`, or `memctrl0`.
- Fill required parameters as components are added.
- Connect ports after core components are configured.
- Save often.
- Keep `.fse` project files separate from generated simulator export files.
- Revalidate after switching framework targets.
