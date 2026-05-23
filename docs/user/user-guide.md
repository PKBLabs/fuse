# User Guide

FUSE provides an IDE-style model-building workspace for architecture and systems simulation workflows.

## Main window

The main window contains:

- A menu bar.
- A left component palette.
- A central drawing/model canvas.
- A dockable properties panel.
- A status bar.

## Component palette

The component palette lists components provided by enabled plugins. For the Community Edition, the included community plugin directories are:

- `plugins/community/sst/`
- `plugins/community/gem5/`

The SST plugin populates palette items by reading SST metadata from `sst-info`, parsing it, storing it in `sst_*` database tables, and translating records into generic FUSE palette items.

## Adding a component to the model

1. Select a component in the palette.
2. Drag it into the model canvas.
3. Drop it where you want the component instance to appear.

A component instance appears as an architecture icon with ports. The exact ports come from plugin-provided item details. If no ports are available, FUSE falls back to basic `in` and `out` ports.

## Selecting a component

Click a component instance on the canvas.

The properties panel updates to show:

- Instance name.
- Component kind.
- Source plugin/type metadata.
- Icon path.
- Parameters.

Required parameters are marked with `*`.

## Editing a component

In the properties panel, edit the value column for editable rows.

Common editable fields include:

- `Name`
- `Icon Path`
- Parameter values

The component instance name must be unique within the model.

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

- Component instances.
- Instance names.
- Component plugin IDs.
- Instance parameters.
- Positions.
- Links.
- Link latency.
- Icon paths.

## About dialog

Use:

```text
Help -> About FUSE
```

The About dialog shows version, edition, licensing, copyright, and plugin policy summary information.
