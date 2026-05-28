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

The gem5 plugin currently provides built-in metadata for supported gem5 objects such as `System`, `TimingSimpleCPU`, `SystemXBar`, and `DDR3_1600_8x8`.

## Adding a component to the model

1. Select a component in the palette.
2. Drag it into the model canvas.
3. Drop it where you want the component instance to appear.

When the component is dropped, FUSE converts the drop location into model coordinates, creates a component instance, assigns a unique default instance name, adds the node to the model, and marks the project dirty.

A component instance appears as an architecture icon with ports. The exact ports come from plugin-provided item details. If no ports are available, FUSE may use fallback ports so the component remains usable.

## Selecting a component

Click a component instance on the canvas.

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

The properties panel updates to show:

- Link name.
- Link type.
- Source component and source port.
- Target component and target port.
- Latency.

The selected link is highlighted.

## Highlighting related links

Click a component instance to highlight links attached to that component. This helps identify link ownership in dense models.

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
