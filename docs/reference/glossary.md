# Glossary

## Active plugin

The plugin selected in Project Settings as the current modeling context. The active plugin controls the component palette and default validation/export context.

## Catalog

A set of component metadata exposed by a plugin. Catalogs may be versioned by framework target.

## Composite component

A reusable FUSE mini-model template made from selected components, internal links, parameters, and layout. Composite components are editor abstractions and are flattened into simulator-native components before plugin validation/export.

## Composite instance

A placed instance of a composite component template. It may have instance-local internal edits that do not change the global reusable template.

## Component definition

The editor-facing generic description of a component type. FUSE serializes component definitions into drag/drop payloads and uses them to create component instances.

## Component instance

A model object placed on the FUSE canvas. It is created by dragging a palette item into the model view.

## Connector

Generic plugin API term for a connectable endpoint. SST maps ports to connectors. gem5 maps SimObject ports to connectors where available.

## Dirty state

The app state indicating that the current project has unsaved changes.

## Framework target

A selectable simulator/framework version or catalog, such as `SST 15.1.2`, `SST 16.0.0`, or `gem5 25.1.0.1`.

## FUSE package root

The directory containing `app/`, `core/`, `plugins/`, `scripts/`, and `requirements.txt`.

## Link

A connection between two ports. Current links are point-to-point and each connected port may only have one link.

## Palette item

A plugin-provided component type that appears in the component palette.

## Plugin

A FUSE extension that provides simulator/framework-specific functionality.

## Project file

A `.fse` JSON file storing a user-created FUSE model and project settings.

## Project Settings

The project-level dialog for selecting enabled plugins, active framework/plugin, target version/catalog, and local/SSH toolchain settings.

## Property

Generic plugin API term for an editable or inspectable value. SST maps parameters to properties.

## Toolchain

The local or remote simulator/framework installation that FUSE can query, validate, or eventually run/export against.

## SST

The Structural Simulation Toolkit. The SST community plugin imports metadata from `sst-info`.

## `sst-info`

An SST command that reports available SST element libraries, components, subcomponents, parameters, ports, statistics, and related metadata.

## gem5

A computer architecture simulator. The gem5 community plugin exposes selected gem5 component metadata and validates configured gem5 binaries.


## `.fcc` file

A JSON file containing one exported composite component definition for sharing/importing. It is separate from the `.fse` project format.
