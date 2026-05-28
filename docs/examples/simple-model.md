# Example: Build a Simple Model

This example walks through a minimal model-building flow in FUSE.

The exact components available depend on the active plugin and selected target. The workflow is the same for SST, gem5, and future plugins.

## Goal

Create a small model with:

- Two component instances.
- Edited parameter values.
- One point-to-point link.
- A saved `.fse` project.

## 1. Start FUSE

```bash
fuse-mod
```

## 2. Create a project

Use:

```text
File -> New Project
```

Open Project Settings and choose the target you want to model against.

Example SST project:

```text
Enable SST for this project: checked
Active framework/plugin: SST
Target version/catalog: SST 15.1.2
Execution location: Local machine
```

Example gem5 project:

```text
Enable gem5 for this project: checked
Active framework/plugin: gem5
Target version/catalog: gem5 25.1.0.1
Execution location: Local machine
```

Use **Validate Enabled Toolchains** if the model will depend on a local or remote simulator installation.

## 3. Add the first component

Drag a component from the palette to the canvas.

FUSE will:

- Decode the component drag metadata.
- Convert the drop point into model coordinates.
- Create a component instance at that coordinate.
- Generate a unique default instance name.

Example generated names:

```text
Cache_1
TimingSimpleCPU_1
System_1
```

## 4. Rename the component

Click the component. In the properties panel, edit:

```text
Object -> Name
```

Example:

```text
TimingSimpleCPU_1 -> cpu0
```

Names must be unique across components and links.

## 5. Edit required parameters

Required parameters are marked with `*`.

Example gem5 CPU parameters:

```text
numThreads *  1
clock *       2GHz
```

Example SST cache parameters might include:

```text
cache_frequency *  2GHz
cache_size *       32KiB
associativity *    8
```

Edit values in the right column. FUSE validates simple type expectations and required fields before accepting the edit.

## 6. Add a second component

Drag another compatible component to the canvas.

Example gem5 model:

```text
SystemXBar_1 -> membus0
```

Example SST model:

```text
Cache_2 -> l2cache0
```

## 7. Connect ports

Click one unconnected port, then click another unconnected port.

FUSE prompts for latency:

```text
1ns
```

After accepting, FUSE creates a link.

Current rule:

```text
Each point-to-point port can be connected to at most one link.
```

## 8. Edit the link

Click the link line. In the properties panel, edit:

```text
Object -> Name
Parameters -> latency
```

Example:

```text
Name:    link_cpu_bus
latency: 1ns
```

## 9. Validate and save

Use:

```text
File -> Save As...
```

FUSE validates the model before saving. If validation fails, fix the listed issues and save again.

Common validation issues:

- Duplicate component names.
- Duplicate link names.
- Missing required parameters.
- Missing link latency.

## 10. Reopen the project

Use:

```text
File -> Open...
```

FUSE restores:

- Project settings.
- Component instances.
- Positions.
- Instance names.
- Parameters.
- Links.
- Link latency.

## 11. Optional: export simulator-specific output

For SST projects, use the SST export action to generate SST JSON.

The FUSE `.fse` file remains the editable project. The SST JSON file is a generated simulator configuration.

## Example saved component entry

```json
{
  "id": 1,
  "pluginId": "gem5",
  "targetId": "1",
  "targetLabel": "gem5 25.1.0.1",
  "frameworkVersion": "25.1.0.1",
  "componentId": "timing_simple_cpu",
  "element": "gem5",
  "name": "TimingSimpleCPU",
  "instanceName": "cpu0",
  "parameters": {
    "numThreads": "1",
    "clock": "2GHz"
  },
  "position": {
    "x": 150.0,
    "y": 180.0
  }
}
```

## Example saved link entry

```json
{
  "id": 1,
  "name": "link_cpu_bus",
  "latency": "1ns",
  "type": "point_to_point",
  "source": {
    "nodeId": 1,
    "componentName": "cpu0",
    "port": "dcache_port"
  },
  "target": {
    "nodeId": 2,
    "componentName": "membus0",
    "port": "cpu_side_ports"
  }
}
```
