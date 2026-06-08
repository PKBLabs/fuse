# Composite Components

Composite components are reusable FUSE mini-models. They let you select a finished portion of a model, store that portion as a named component template, and place new instances of that template elsewhere in the same project or in other projects.

Composite components are sometimes called macro components. In the FUSE user interface, the preferred name is **Composite Component**.

## Why use composite components?

As models grow, users often repeat the same local topology many times. For example, an SST memory subsystem may contain a CPU, caches, coherence objects, generators, links, parameters, and carefully arranged positions. Rebuilding that group manually every time is slow and error-prone.

A composite component preserves that work as a reusable mini-model:

```text
selected components + internal links + parameters + positions
  -> Composite Component template
  -> draggable palette item
  -> editable placed instances
```

Composite components are a FUSE editing abstraction. They are not SST components, gem5 SimObjects, or plugin-native simulator objects. Before simulator validation or export, FUSE expands composite instances into the ordinary components and links that make up their internal mini-model.

## Creating a composite from selected components

<!-- FUSE-MEDIA-TODO id=composite-selection type=screenshot path=../assets/screenshots/composite-selection.png -->
> **Media TODO (composite-selection)**: Add a screenshot showing multiple selected components before creating a composite.
> Planned asset: `../assets/screenshots/composite-selection.png`


1. Place, connect, and configure the components that should become the reusable group.
2. Use **Multiselect** in the model-view toolbar, or hold **Ctrl** and click components, to select the components that should be included.
3. FUSE highlights selected components and highlights only the links whose endpoints are both selected.
4. Choose one of the creation actions:
   - **Edit -> Create Composite Component from Selection**
   - Right-click one of the selected components and choose **Create Composite Component from Selection**
5. Enter a name for the new composite component.
6. Optionally enter a description and icon path, or use **Browse** to select an icon.
7. Confirm the dialog.

FUSE stores the selected portion of the model as a local composite definition and replaces the selected items with one placed composite instance. New composites start with their candidate external ports hidden by default. Open the new composite template and explicitly expose only the ports that should appear on the composite boundary. New composites start with their candidate external ports hidden by default. Open the new composite template and explicitly expose only the ports that should appear on the composite boundary.

## Selection rules

Only links with both endpoints inside the selected component set are included in the composite mini-model.

```text
selected component <-> selected component
  included as an internal composite link

selected component <-> unselected component
  not included as an internal composite link
```

If a selected fragment has a boundary connection to an unselected component, FUSE protects the model from accidental corruption. The selected fragment must be made self-contained before it can be converted into a composite, or future boundary-remapping support must be used once available.

## Explicit composite ports

Composite ports are explicit. FUSE records candidate boundary ports for the internal mini-model, but a port appears on the composite component box only when it is marked as exposed.

By default, newly created composites expose no ports. This avoids noisy composite boxes when a mini-model has many unused internal ports, especially when composites contain other composites. Users choose the public interface of the composite by exposing only the ports that should be linkable from the parent model.

Each exposed composite port maps one-to-one to an internal component port:

```text
visible composite port
  -> internal component instance
  -> internal port name
```

Hidden ports remain available inside the composite edit tab, but they do not appear on the composite boundary and cannot be used by links in the parent model.

### Exposing and hiding ports

Open a composite template or composite instance edit tab, then use one of these workflows:

- Enable **Expose Ports** in the floating model-view toolbar and left-click internal ports to toggle whether they are exposed.
- Right-click an internal port and choose **Expose Port on Composite** or **Hide Port from Composite**.

Exposed internal ports are highlighted in the composite edit view. Hiding a port removes it from the composite component boundary. Showing a port adds it to the visible ports for that template or instance.

Right-clicking a port for expose/hide does not start link-creation mode. The expose/hide workflow is separate from normal linking.

When you connect a normal component to an exposed composite port, the link is drawn to the composite box in the model view. During validation/export, FUSE resolves that visual connection to the mapped internal component port.

## Composite entries in the component palette

<!-- FUSE-MEDIA-TODO id=composite-instance type=screenshot path=../assets/screenshots/composite-instance.png -->
> **Media TODO (composite-instance)**: Add a screenshot showing the resulting composite component instance on the main canvas.
> Planned asset: `../assets/screenshots/composite-instance.png`


Created or imported composites appear in the component palette under **Composite Components**. They can be dragged into the model view like normal components.

A new composite instance receives a generated default name based on the template name:

```text
CacheCluster_1
CacheCluster_2
CacheCluster_3
```

The properties panel for a selected composite instance shows both instance-local metadata and template metadata, including the composite template name and template ID.

## Instance-local editing

<!-- FUSE-MEDIA-TODO id=composite-edit-tab type=screenshot path=../assets/screenshots/composite-edit-tab.png -->
> **Media TODO (composite-edit-tab)**: Add a screenshot showing the composite template/instance editor with the internal mini-model visible.
> Planned asset: `../assets/screenshots/composite-edit-tab.png`

<!-- FUSE-MEDIA-TODO id=video-composite-workflow type=video path=../assets/videos/composite-workflow.mp4 -->
> **Media TODO (video-composite-workflow)**: Add a short video showing select components, create composite, place instance, open editor, and expose a port.
> Planned asset: `../assets/videos/composite-workflow.mp4`


Double-click a composite instance to edit its internal mini-model. FUSE opens a model-view tab for that placed instance.

The first tab is the global project model. Composite edit tabs appear to the right:

```text
[ ProjectName ] [ CompositeA_1 ] [ CompositeA_1:CompositeB_2 ]
```

The project tab cannot be closed. Composite tabs can be closed. Closing a parent composite tab also closes tabs for nested child composite edit contexts.

Edits made inside a composite instance tab apply only to that placed instance. They do not mutate the global composite template stored in the local database. This allows one instance of a composite to be customized without changing other instances of the same template.

Instance-local edits include:

- internal component names
- internal parameters
- internal icon overrides
- internal positions
- internal links and subcomponent attachments supported by the normal model editor
- nested composite instance state
- exposed/hidden port state for that placed instance

## Nested composites

Composite components may contain other composite components. This supports hierarchical model design.

For example:

```text
Global model
  Rack_1
    Tile_1
      CPU/cache/memory mini-model
    Tile_2
      CPU/cache/memory mini-model
```

Double-clicking a nested composite opens another tab with a hierarchy-aware label. FUSE keeps the edit context tied to the specific placed instance, not just the global template.

When flattening for validation or export, FUSE expands nested composites recursively. Expansion rejects composite cycles, such as A containing B while B also contains A.

## Model Outline and Properties panels

There is one global Properties panel and one global Model Outline panel.

Both panels follow the active model-view tab:

- Selecting the project tab shows the global project model outline.
- Selecting a composite tab shows that composite instance's internal mini-model outline.
- Selecting a component, subcomponent, or link in the outline selects and highlights it in the active model view.
- Opening a composite tab starts with no selected object, so the Properties panel shows nothing selected until the user clicks an item.

## Editing global composite templates

A composite definition can be edited as a global/default template. Open the manager with:

```text
Edit -> Manage Composite Components...
```

Select a composite and choose **Edit**, or right-click a composite entry in the component palette and choose **Edit Component...**. FUSE opens a template edit tab named like:

```text
CacheCluster [Template]
```

Template edit tabs change the reusable database definition. Use **Expose Ports** or the port context menu to choose which internal ports should appear on new composite instances by default.

Template tabs have a **Save Template Changes** button. Dirty template tabs are marked with an asterisk. If you close a dirty template tab, FUSE prompts you to save, discard, or cancel the close operation.

When the current project already contains instances of the edited template, saving asks whether to apply the updated template to existing instances in the open project. Applying the template can replace instance-local composite edits. If you do not apply the template, the database definition is still saved, but existing placed instances keep their current instance-local state.

## Managing local composite definitions

Open:

```text
Edit -> Manage Composite Components...
```

The manager dialog lists composite definitions stored in the local database. It supports:

- importing `.fcc` files
- exporting selected composite definitions to `.fcc`
- deleting obsolete or erroneous composite definitions from the local database
- editing global/default composite templates

Deleting a definition removes it from the local component catalog. It does not rewrite already-saved project files or external `.fcc` files. If an open project still contains instances of a deleted template, those instances may rely on their saved instance-local mini-model state or may report a missing composite definition during expansion.

## Importing and exporting composite definitions

Composite definitions can be shared using `.fcc` files.

To import a shared definition:

```text
File -> Import -> Import Composite Component...
```

or use **Import** in the composite manager.

To export a definition, select a composite instance and use:

```text
File -> Export -> Selected Composite Component...
```

or select a definition in the composite manager and choose **Export**.

If an imported file has the same name as an existing local composite but a different ID, FUSE renames the imported definition with an imported suffix so both definitions can coexist.

## Simulator validation and export

Composite components are not passed to simulator plugins as simulator-native objects.

Before SST or gem5 validation/export, FUSE flattens the editable model:

```text
FUSE model with composite instances
  -> expanded model containing ordinary components and links
  -> plugin validation/export
```

The SST exporter receives only SST components, SST subcomponents, and SST links. The gem5 exporter receives only gem5 model objects. This keeps composite editing generic in FUSE core while simulator-specific behavior remains owned by simulator plugins.

## Current limitations

- Composite definitions are stored locally unless exported to `.fcc` and imported elsewhere.
- Deleting a composite definition removes it from the local catalog but does not automatically remove or rewrite placed instances in existing projects.
- Composite boundary links are conservative during creation; only links with both endpoints in the selected fragment become internal links.
- Composite icons currently use file paths. Shared projects may need icon paths adjusted if the same files do not exist on another machine.
- New composites expose no ports until the user explicitly exposes ports in a template or instance edit tab.
- Hidden composite ports cannot be linked from the parent model. If a link cannot be flattened, check that the target composite port is exposed.
- Very deep composite hierarchies may produce long tab labels; full hierarchy labels are intended to preserve edit context.
