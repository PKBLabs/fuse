# Properties and Validation

The properties panel is the main way to inspect and edit selected model objects. It is also the first line of validation for user-entered values.

## What the properties panel shows

The panel changes based on the current selection:

- Nothing selected: empty state.
- Component selected: component instance metadata and parameters.
- Link selected: link metadata and link parameters.

## Component properties

When a component instance is selected, the panel shows an **Object** section and a **Parameters** section.

The Object section includes:

| Row | Editable | Description |
|---|---:|---|
| `Name` | Yes | Unique component instance name in the current model. |
| `Kind` | No | Component or subcomponent. |
| `Element` | No | Plugin/framework element or namespace. |
| `Component Type` | No | Component type name from plugin metadata. |
| `Interface` | No | Plugin/framework interface metadata, if available. |
| `Target` | No | Selected framework target/catalog label. |
| `Framework Version` | No | Framework version associated with the component metadata. |
| `Icon Path` | Yes | Icon path used to render the component instance. |

The Parameters section is generated from plugin-provided parameter metadata. For example, SST parameters come from imported `sst-info` metadata, while gem5 parameters come from imported live `m5.objects` metadata when available and from the built-in gem5 fallback catalog otherwise.

Required parameters are displayed with `*`:

```text
clock *
cache_size *
associativity
```

## Link properties

When a link is selected, the panel shows:

| Row | Editable | Description |
|---|---:|---|
| `Name` | Yes | Unique link name. |
| `Type` | No | Current link type, usually `point_to_point`. |
| `Source` | No | Source component instance and source port. |
| `Target` | No | Target component instance and target port. |
| `latency` | Yes | Link latency, such as `1ns`. |

## How property editing works

When the user edits a value in the properties panel:

1. The panel validates the value.
2. If invalid, the user receives a warning and the old value is restored.
3. If valid, the value is written to the selected model object.
4. FUSE marks the model as changed/dirty.
5. Later save/export operations use the updated model state.

Component parameter edits are written into the selected component node's `parameters` dictionary.

Example saved component parameters:

```json
"parameters": {
  "clock": "2GHz",
  "numThreads": "2"
}
```

Link edits are written into the selected link object.

Example saved link:

```json
{
  "id": 1,
  "name": "link_cpu_bus",
  "latency": "1ns",
  "type": "point_to_point"
}
```

## Parameter metadata used by the panel

The panel consumes generic parameter metadata from plugin item details.

```python
PropertyDefinition(
    name="clock",
    description="Clock frequency.",
    default_value="1GHz",
    required=True,
    value_type="string",
)
```

Core currently uses:

- `name` for the row key and saved parameter name.
- `description` for user-facing help/tooltips where available.
- `default_value` as the displayed value when the instance has not overridden it.
- `required` to mark required rows and validate non-empty values.
- `value_type` as a future type hint. Current validation mostly infers simple numeric type checks from defaults.

## Current input validation

The properties panel currently validates:

### Names

Component and link names must be non-empty and unique across the model.

Invalid:

```text
""
cache0  # if another component or link already uses cache0
```

Valid:

```text
cpu0
l1_cache_0
link_cpu_cache
```

### Required parameters

If a plugin marks a parameter as required, it must have a non-empty value.

Invalid:

```text
clock *    
```

Valid:

```text
clock *    2GHz
```

### Latency values

Link latency must end with a time unit.

Accepted suffixes:

```text
fs, ps, ns, us, ms, s
```

Valid examples:

```text
500ps
1ns
0.5us
```

Invalid examples:

```text
1
fast
10cycles
```

### Numeric defaults

If a parameter default looks like an integer, edited values must parse as integers.

Example:

```text
default: 4
valid:   8
invalid: eight
```

If a parameter default looks like a floating-point value, edited values must parse as numbers.

Example:

```text
default: 0.25
valid:   0.5
invalid: high
```

## Full model validation

FUSE also validates the model during save/export-oriented workflows.

Current core validation checks:

- Empty component names.
- Duplicate component names.
- Empty link names.
- Duplicate link names.
- Missing required component parameters.
- Missing link latency.

Plugin-provided property definitions can mark parameters as required. The SST plugin maps SST `<required>` defaults to required FUSE parameters.

## Validation feedback

When validation runs, FUSE opens the **Validation Results** panel at the bottom of the main window. The panel behaves like an IDE problems view and lists each result with:

- severity, such as Error, Warning, or Info;
- scope, such as Project, Component, Link, or SubComponent;
- affected object name;
- message;
- suggested fix.

Use the filter control in the panel to show all results or only errors, warnings, or informational entries. Double-click a validation result to select and center the affected object in the Model View when the result refers to a component, link, or subcomponent attachment.

Validation feedback is also reflected in the editor:

- affected component boxes show validation markers;
- affected link and subcomponent attachment edges are highlighted;
- affected component property rows are highlighted where FUSE can map the issue to a property name;
- tooltips on affected objects include validation details.

The user should fix all errors before saving or exporting. Warnings identify suspicious or incomplete model details that may still be editable as a FUSE model, but may need review before simulator export.

Example validation results:

```text
Error | Component | cache0 | Required parameter 'clock' has no value. | Set 'clock' in the Properties panel.
Error | Link      | link0  | Source endpoint latency is required.     | Set 'source_latency' in the Properties panel.
Error | Project   | Project| Mixed-plugin export is not supported.    | Select the correct target or remove unsupported simulator components.
```

## Plugin-specific validation

Core validation is intentionally generic. Plugins may later add richer validation, such as:

- SST latency/unit parsing.
- SST component/subcomponent compatibility checks.
- SST target-version availability checks.
- gem5 SimObject connection compatibility.
- gem5 parameter type/range checks.

The project settings toolchain validation already checks whether the configured simulator/toolchain is reachable and compatible with the selected target version.

## Troubleshooting property edits

If a value keeps reverting:

1. Check whether the value is empty for a required field.
2. Check whether the field expects a number based on its default value.
3. Check whether a link latency includes a valid time suffix.
4. Check whether the name is already used by another component or link.
5. Check whether the selected component belongs to the expected framework target.
