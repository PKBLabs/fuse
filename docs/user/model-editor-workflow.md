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

Use the palette view selector to choose how the catalog is organized:

- **Element** groups entries by simulator/framework element and separates components from subcomponents.
- **Function** groups entries by inferred purpose, such as CPU, Memory, Network, Bus / Interconnect, I/O, Generator, and Statistics / Debug.
- **Flat** lists all entries together.
- **Recent** lists recently used entries.
- **Compatible SubComponents** lists matching subcomponents for the currently selected component when slot metadata is available.

Use the **A-Z** checkbox to control sorting. When enabled, catalog groups and component entries are sorted alphabetically. When disabled, the palette preserves plugin/catalog order. Hover over a palette entry to see metadata such as display name, description, function, interface, and category.

Project Settings also includes preferred catalog behavior:

- **Preferred Component Grouping Mode** selects the default catalog organization when no model component is selected.
- **Preferred Component Sorting Mode** selects whether the catalog defaults to alphabetical order or plugin/catalog order.
- **Auto Expand All Component Tree** controls whether the catalog opens with all groups expanded.

When a component is selected in the model view, the catalog may temporarily switch to **Compatible SubComponents** so the user can quickly find valid children for the selected component's slots. Clearing the selection returns the catalog to the project's preferred grouping and sorting behavior.

Use the search field above the catalog to filter known components as you type. Search checks component names, display names, framework elements, categories, inferred functions, descriptions, interfaces, plugin identifiers, target labels, and framework versions. Use **Expand/Collapse All** above the tree to expand or collapse the current catalog hierarchy; that state is stored with the project.

For SST, metadata is imported from `sst-info` into the local database. If the palette is empty, check that:

- SST Core and SST Elements are installed.
- `sst-info` is reachable locally or through the configured SSH environment.
- The selected SST target has been imported into the FUSE database.
- The project is using the expected active plugin and target.

For gem5, the community plugin can import live SimObject metadata from the configured local gem5 binary. When live metadata has not been imported yet, FUSE falls back to the built-in gem5 catalog for supported objects.

## 5. Add components to the model

Drag a component from the palette and drop it on the canvas.

Each successful drop updates the palette's recent/frequent usage tracking. The Frequently Used quick section shows high-use and pinned entries. Right-click a component instance on the canvas or in the model outline and choose **Add to Frequently Used** to pin that component type for quick access.

When a drop occurs, FUSE:

1. Reads the component metadata from the drag payload.
2. Converts the drop location from view coordinates into model scene coordinates.
3. Creates a component instance at that model coordinate.
4. Generates a unique default instance name.
5. Adds the instance to the scene/model outline.
6. Marks the model as changed/dirty.

The **Edit -> Undo** and **Edit -> Redo** actions track model-editing changes such as component creation, deletion, property edits, link edits, subcomponent attachment edits, and canvas layout changes. Use **Ctrl+Z** to undo the last recorded edit and **Ctrl+Shift+Z** to redo an edit that was undone. FUSE keeps a bounded edit history for the current project session and clears the redo stack when a new edit is made after undoing. Component drags are coalesced into one history entry so a single mouse drag can be undone with one **Undo** action.

The model view also includes a floating canvas toolbar. It can be dragged within the model view and provides quick access to:

- **Select/Move** for normal component selection, link selection, port clicks, component movement, and empty-space panning.
- **Multiselect** for rectangular marquee selection.
- **Undo** and **Redo**.
- A zoom percentage selector plus **Zoom In** and **Zoom Out**.

The toolbar position, zoom level, interaction mode, and current view center are editor state. They are saved in `.fse` files and restored when a project is reopened. They are not simulator model data and do not change exported simulator topology.

Example default names:

```text
Cache_1
Cache_2
TimingSimpleCPU_1
SystemXBar_1
```

The base name comes from the component type. FUSE increments a numeric suffix until the instance name is unique in the model.

### Create and reuse composite components

After a portion of the model is configured, it can be turned into a reusable composite component. Select the components with **Multiselect** or **Ctrl+click** and choose **Edit -> Create Composite Component from Selection**. FUSE saves the selected components, internal links, parameters, and layout as a local mini-model template and replaces the selected fragment with one composite instance.

Composite templates appear in the component palette under **Composite Components** and can be dragged into the model view like normal components. Double-click a composite instance to open a model-view tab for editing that instance's internals. Nested composites open hierarchy-labeled tabs such as `Outer_1:Inner_1`.

Use **Edit -> Manage Composite Components...** to import, export, or delete locally stored composite definitions. Composite definitions can be shared with other users as `.fcc` files.

See [Composite Components](composite-components.md) for the complete workflow.

## 6. Navigate the model canvas

Use the model canvas as a zoomable and pannable workspace.

- Use the floating toolbar's zoom controls, the zoom percentage field, the mouse wheel, or keyboard zoom shortcuts to zoom in and out.
- Drag empty canvas background in **Select/Move** mode to pan the view.
- Drag a component or subcomponent to move only that item rather than panning the whole model.
- Use **Multiselect** mode to draw a rectangular marquee around multiple items. When several components are selected, FUSE highlights links whose endpoints are both selected.
- The light grid is only a visual alignment aid; it does not change model coordinates or exported simulator output.

Hit testing is view-aware. Component, port, and link selection should continue to work when the view is zoomed in or out. Ports are prioritized near link endpoints so connecting and selecting ports remains practical even when links overlap a port location.

## 7. Understand drag/drop placement

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

When the project is reopened, FUSE restores the component to that model coordinate. The `.fse` serializer also stores format/version metadata, model counts, plugin identities, component properties, ports/link references, subcomponent attachment references, and editor layout data so users can continue editing after reopening the project.

## 8. Select and inspect components

Click a component instance on the canvas. Hover over the component to see its tooltip, including instance/type metadata and validation warnings when present. Hover over ports to see the port name and availability.

Right-click a component on the canvas to open its context menu:

- **Add to Frequently Used** pins or promotes the component type in the palette.
- **Remove Component** deletes the component instance.
- **Remove SubComponent** appears instead for subcomponent instances.

The same component actions are available from the model outline context menu. When the selected items can form a composite, **Create Composite Component from Selection** is also available from the Edit menu and selected-item context menu.

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

## 9. Edit component properties

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

## 10. Parameter validation while editing

The properties panel validates basic inputs before accepting edits.

Current validation includes:

- Names cannot be empty.
- Component and link names must be unique.
- Required parameters cannot be empty.
- Latency values must end with a time unit such as `ps`, `ns`, `us`, `ms`, or `s`.
- If a parameter default looks like an integer, replacement values must parse as integers.
- If a parameter default looks like a floating-point number, replacement values must parse as numbers.

If an entered value is invalid, FUSE warns the user and restores the previous value.

## 11. Connect ports

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

## 12. Select and edit links

Click a link line to inspect it. Hover over a link to see its tooltip, including the link name, source endpoint, target endpoint, source latency, and target latency. Right-click a link and choose **Remove Link** to delete it.

The properties panel shows:

- Link name.
- Link type.
- Source endpoint.
- Target endpoint.
- Source latency.
- Target latency.

Example:

```text
Object
  Name    link_1
  Type    point_to_point
  Source  cpu0.icache_port
  Target  bus0.cpu_side_ports

Parameters
  source_latency 1ns
  target_latency 1ns
```

Editable link fields include:

- Link name.
- Source latency.
- Target latency.

Links can also be deleted from the model outline context menu, from the properties panel delete button, or by pressing **Delete**/**Backspace** while the link is selected.

## 13. Delete model objects

FUSE supports deletion from both the canvas and the model outline. Select a component, subcomponent, link, or subcomponent attachment and press **Delete** or **Backspace**, or use the relevant right-click/context-menu remove action. The properties panel also exposes a delete button for selected links and subcomponent attachments.

When a component is deleted, FUSE also removes attached normal links, subcomponent attachment edges involving that component, and recursively attached child subcomponents. When a link is deleted, it is removed from both endpoint ports so those ports can be reused.

## 14. Validate the model

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

## 15. Save the project

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

## 16. Export simulator-specific output

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

## 17. Save/load and `.fse` serialization

The `.fse` file is the editable FUSE project format. It is distinct from simulator export formats such as SST JSON or gem5 Python. A saved `.fse` project preserves:

- project settings and enabled plugin targets
- SST, gem5, and mixed-plugin component instances
- component properties and variable-port counts
- point-to-point links, endpoint latencies, compatibility status, and plugin metadata
- subcomponent attachments and compatibility metadata
- canvas positions, scene bounds, and view metadata
- serializer/schema metadata used for future compatibility checks

FUSE validates the file structure before loading a project and before writing a project file. Saves are written atomically through a temporary file and replace the destination only after JSON serialization succeeds, which reduces the chance of leaving a partially written `.fse` file after a failed save.

Mixed SST/gem5 models are valid FUSE models and can be saved, reopened, and edited. Export validation remains simulator-specific: SST-only models can be validated for SST export, gem5-only models can be validated for gem5 export, and mixed export is reported as unsupported until a defined hybrid backend exists.
