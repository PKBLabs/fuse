# FUSE Community Edition

FUSE, the Flexible User-extensible Simulation Editor, is a plugin-oriented graphical application for building, validating, and exporting simulation models through a visual desktop editor.

<!-- FUSE-MEDIA-TODO id=home-hero type=screenshot path=assets/screenshots/main-window-empty.png -->
> **Media TODO (home-hero)**: Add a clean first-launch screenshot showing the empty FUSE workspace, component palette, model canvas, properties panel, and validation/status areas.
> Planned asset: `assets/screenshots/main-window-empty.png`

## What FUSE provides

FUSE is intended to make simulator model construction more approachable while preserving framework-specific metadata, validation, and export behavior.

Core capabilities include:

- A Qt/PySide6 graphical model canvas.
- Drag-and-drop framework components from plugin-provided palettes.
- Ports, typed links, and subcomponent attachment workflows.
- Editable properties and framework-derived parameters.
- Composite components for reusable mini-models.
- Project save/load using `.fse` files.
- Validation before save/export.
- Community plugins for SST and gem5.
- Export paths for SST JSON and gem5 Python artifacts.

## Start here

New users should begin with:

- [Installation](user/installation.md)
- [Quickstart](user/quickstart.md)
- [Model editor workflow](user/model-editor-workflow.md)
- [Troubleshooting](user/troubleshooting.md)

Developers should begin with:

- [Developer setup](developer/developer-setup.md)
- [Architecture overview](architecture/architecture-overview.md)
- [Plugin system](plugins/plugin-system.md)
- [Generated API docs](developer/generated-docs.md)

Maintainers should begin with:

- [Media capture plan](operations/media-capture-plan.md)
- [GitHub Actions](ci/github-actions.md)
- [Release process](developer/release-process.md)

## Generated API reference

The hand-written MkDocs site is the primary user and developer documentation. Doxygen output is still generated for API/class/function reference and is available at:

[Generated Doxygen API Reference](generated/html/index.html)
