# Model Editor Workflow

This guide describes the recommended day-to-day workflow for building a model in FUSE.

## 1. Start FUSE

```bash
fuse-mod
```

The splash screen appears, then the editor opens.

## 2. Verify plugin metadata is loaded

The component palette should show plugin-provided component definitions.

For SST, metadata appears only after the SST plugin has imported `sst-info` output. If the palette is empty, see [Troubleshooting](troubleshooting.md).

## 3. Add model objects

Drag components from the palette into the model canvas.

Each dropped component becomes an instance. Multiple instances may use the same component type, but each instance must have a unique name.

## 4. Configure parameters

Select a component and edit parameters in the properties panel.

Required parameters are marked with `*`.

Example:

```text
clock *     2GHz
threads *   4
```

## 5. Connect ports

Click a source port, then click a target port.

FUSE prompts for link latency:

```text
1ns
```

Each port can participate in only one point-to-point link.

## 6. Inspect links

Click a link to inspect it in the properties panel. Edit the link name or latency if needed.

Example link properties:

```text
Name       link_cpu_cache
Type       point_to_point
Source     cpu0.out
Target     cache0.in
latency    1ns
```

## 7. Save the project

Use `File -> Save As...` and save a `.fse` file.

If validation fails, fix all reported errors before saving.

## 8. Re-open the project

Use `File -> Open...` to verify the model loads correctly.

## Good modeling habits

- Use meaningful instance names such as `cpu0`, `l1cache0`, `router0`.
- Fill all required parameters before adding many links.
- Use the properties panel to inspect selected components and links.
- Save often.
- Keep plugin-specific generated data separate from project files.
