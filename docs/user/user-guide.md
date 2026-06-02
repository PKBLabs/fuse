# User Guide

FUSE provides an IDE-style model-building workspace for architecture and systems simulation workflows.

## Main window

The main window contains:

- A menu bar.
- A left component palette.
- A central drawing/model canvas.
- A dockable properties panel.
- A status bar.

## Projects and Project Settings

FUSE projects are configured through:

```text
File -> New Project
File -> Open Project
File -> Project Settings
```

Project Settings define:

- Project name.
- Active framework/plugin.
- Enabled plugins.
- Target version/catalog for each enabled plugin.
- Local or remote SSH execution environment.
- Tool paths for enabled simulator/framework toolchains.

Project-specific settings are saved in the `.fse` file. This lets one project target SST 15.1.2 while another targets SST 16.0.0 or gem5 25.1.0.1.

## Component palette

The component palette lists components provided by the active plugin and selected target/catalog.

The Community Edition includes community plugin directories for:

- `plugins/community/sst/`
- `plugins/community/gem5/`

The SST plugin populates palette items by reading SST metadata from `sst-info`, parsing it, storing it in `sst_*` database tables, and translating records into generic FUSE palette items.

The gem5 plugin can import live SimObject metadata from a configured local gem5 executable. When no live metadata has been imported for the selected target, it falls back to built-in metadata for supported objects such as `System`, `TimingSimpleCPU`, `SystemXBar`, and `DDR3_1600_8x8`.

### Palette organization and sorting

The palette can show the active catalog in several views:

- **Element** groups components by simulator/framework element and then separates normal components from subcomponents.
- **Function** groups components by inferred function, such as CPU, Memory, Network, Bus / Interconnect, I/O, Generator, and Statistics / Debug.
- **Flat** shows all available entries in one list.
- **Recent** shows recently used components and subcomponents.
- **Compatible SubComponents** narrows the list to subcomponents that match the selected component's available subcomponent slots when that compatibility context is available.

The **A-Z** checkbox controls catalog sorting. When it is enabled, groups and entries are sorted alphabetically. Component sorting uses the component element, whether the entry is a component or subcomponent, and the component name. When it is disabled, entries keep the order returned by the active plugin/catalog.

Palette entries show tooltips when you hover over them. A component tooltip includes the display name, description, function, interface, and category when that metadata is available. Gem5 entries use imported or inferred functionality such as System, Processor, Interconnect, Memory, Memory Hierarchy, Device, or SimObject to keep live catalogs navigable.

### Frequently used and recent components

The palette tracks component usage locally so frequently used and recently used items can be reached quickly.

- Dragging/dropping a component records it as recently used and increments its usage count.
- The **Frequently Used** quick section shows the highest-count entries first, with alphabetical ordering as a tie-breaker.
- Right-click a component instance on the canvas or in the model outline and choose **Add to Frequently Used** to pin that component into the quick section.
- Frequently used entries can also be hidden/removed from the quick section through the palette's component tile context menu.

Usage state is stored in local user settings. It is a convenience feature and is not written to the `.fse` project file.

## Adding a component to the model

1. Select a component in the palette.
2. Drag it into the model canvas.
3. Drop it where you want the component instance to appear.

When the component is dropped, FUSE converts the drop location into model coordinates, creates a component instance, assigns a unique default instance name, adds the node to the model, and marks the project dirty.

A component instance appears as an architecture icon with ports. The exact ports come from plugin-provided item details. If no ports are available, FUSE may use fallback ports so the component remains usable.

## Selecting a component

Click a component instance on the canvas.

Hovering over a component shows a tooltip with the instance name, component type, plugin/target metadata, and warning text when validation has marked the component. Hovering over a port shows the port name and whether the port is available or already occupied.

Right-click a component instance to open its context menu. The component context menu currently includes:

- **Add to Frequently Used**: pins or promotes that component type in the palette's Frequently Used section.
- **Remove Component**: deletes the component instance from the model.
- **Remove SubComponent**: shown instead of Remove Component for subcomponent instances.

The properties panel updates to show:

- Instance name.
- Component kind.
- Element/category/type metadata.
- Target/catalog metadata.
- Framework version.
- Icon path.
- Parameters.

Required parameters are marked with `*`.

## Editing a component

In the properties panel, edit the value column for editable rows.

Common editable fields include:

- `Name`
- `Icon Path`
- Parameter values

The component instance name must be unique within the model. Parameter edits are written back to the component instance and saved in the `.fse` project file.

## Creating links

FUSE currently supports point-to-point links.

To create a link:

1. Click an unconnected source port.
2. Click an unconnected target port.
3. Enter a latency when prompted.

Each point-to-point port can participate in at most one link. If a port is already connected, FUSE rejects attempts to connect it again.

## Selecting links

Click a link line to select it.

Hovering over a link shows a tooltip with the link name, source endpoint, target endpoint, source latency, and target latency. Right-click a link and choose **Remove Link** to delete it.

The properties panel updates to show:

- Link name.
- Link type.
- Source component and source port.
- Target component and target port.
- Latency.

The selected link is highlighted.

## Highlighting related links

Click a component instance to highlight links attached to that component. This helps identify link ownership in dense models.

## Deleting components, subcomponents, and links

FUSE provides several equivalent deletion paths:

- Select a component, subcomponent, link, or subcomponent attachment on the canvas and press **Delete** or **Backspace**.
- Right-click a component on the canvas and choose **Remove Component** or **Remove SubComponent**.
- Right-click a link on the canvas and choose **Remove Link**.
- Select a link or attachment and use the delete button shown in the properties panel.
- Right-click an item in the model outline and choose the remove action.
- Select a component or link in the model outline and press **Delete** or **Backspace**.

Deleting a component also deletes normal links attached to that component, subcomponent attachment edges involving that component, and recursively attached child subcomponents. Deleting a link removes it from both endpoint ports and makes those ports available again. All deletion operations mark the project dirty.

## Undo, redo, and unsaved changes

Use **Edit -> Undo** or **Ctrl+Z** to undo the most recent model edit. Use **Edit -> Redo** or **Ctrl+Shift+Z** to restore an edit that was undone. Undo/redo covers the current editing session and is intended for normal model-editing actions such as component creation, deletion, property changes, link changes, subcomponent attachment changes, and layout moves. Interactive drag movement is recorded as one undoable layout change instead of a separate history entry for every intermediate mouse position.

Creating a new edit after undoing clears the redo stack, matching common editor behavior. The edit history is bounded so very long editing sessions do not grow without limit.

When the model has unsaved changes, FUSE shows an asterisk in the window title and an **Unsaved** indicator in the status bar. Saving the project clears the indicator. New/Open/Exit prompts still protect unsaved changes.

## Validating a model

FUSE validates generic model rules before save/export workflows.

Current validation checks include:

- Empty component names.
- Duplicate component names.
- Empty link names.
- Duplicate link names.
- Missing required component parameters.
- Missing link latency.

Project Settings also validates configured toolchains for enabled plugins.

## Saving a project

Use:

```text
File -> Save
```

or:

```text
File -> Save As...
```

FUSE project files use the `.fse` extension.

Before saving, FUSE validates the model. If required values are missing or names are duplicated, save is blocked and the affected components/rows are marked.

## Opening a project

Use:

```text
File -> Open...
```

The project loader restores:

- Project settings.
- Active plugin/target selection.
- Component instances.
- Instance names.
- Component plugin IDs.
- Framework target metadata.
- Instance parameters.
- Positions.
- Links.
- Link latency.
- Icon paths.

## Exporting simulator-specific output

A `.fse` file is FUSE's native project format. Simulator-specific exports are generated separately.

For SST, FUSE can export the current model to SST JSON configuration format. The generated SST JSON file is intended for SST, while the `.fse` file remains the editable FUSE project.

## About dialog

Use:

```text
Help -> About FUSE
```

The About dialog shows version, edition, licensing, copyright, and plugin policy summary information.

## More documentation

- [Model Editor Workflow](model-editor-workflow.md)
- [Properties and Validation](properties-and-validation.md)
- [Project Files](project-files.md)
- [Component Metadata Reference](../reference/component-metadata.md)

## Unsaved changes and project lifecycle actions

The model title and status bar indicate when the current project has unsaved changes. FUSE clears this dirty state after a successful save or after opening/creating a clean project.

When a dirty model is open, New, Open, and Exit actions present a save prompt. Failed saves do not discard work, and cancelling the prompt leaves the current model unchanged.
