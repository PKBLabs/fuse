# Resources and Icons

FUSE includes generic architecture component icons under:

```text
fuse/core/resources/media/arch_component_icons/
```

The application logo is under:

```text
fuse/core/resources/media/fuse_logo.png
```

## Resource path helpers

Resource paths are centralized in:

```text
fuse/core/resource_paths.py
```

Important values include:

- `FUSE_PACKAGE_ROOT`
- `ARCH_COMPONENT_ICON_DIR`
- `FUSE_LOGO_PATH`
- `resolve_icon_path()`

## Component icons

Component icon paths are stored in plugin catalog records and project files. The runtime resolves icon paths with `resolve_icon_path()`.

Resolution supports:

- Absolute paths.
- Paths relative to the current working directory.
- Paths relative to the FUSE package root.
- Bare filenames located in `ARCH_COMPONENT_ICON_DIR`.

## Changing an instance icon

Select a component instance and edit the `Icon Path` property.

The edit applies to that instance and is saved in the `.fse` file.

## Plugin icon mapping

The icons themselves are generic core assets. Plugin-specific mapping belongs to plugins.

For SST, mapping logic is in:

```text
fuse/plugins/community/sst/sst_icon_resolver.py
```

and overrides live in:

```text
fuse/plugins/community/sst/config/sst_icon_overrides.csv
```

## Adding a new icon

1. Add a PNG to `fuse/core/resources/media/arch_component_icons/`.
2. Use a descriptive filename, for example `memory_controller.png`.
3. Update plugin mapping logic or override CSV if needed.
4. Add or update icon resolver tests.

## Recommended icon style

- PNG format.
- Transparent background where possible.
- Clear silhouette at small sizes.
- Avoid embedded text if the icon will be shown small.
