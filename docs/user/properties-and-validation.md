# Properties and Validation

The properties panel is the main way to inspect and edit component instances and links.

## Component properties

When a component instance is selected, the panel shows:

- Name
- Kind
- Element/category/type metadata
- Interface
- Icon path
- Parameters

Required parameters are displayed with `*`.

## Link properties

When a link is selected, the panel shows:

- Name
- Type
- Source endpoint
- Target endpoint
- Latency

## Validation rules

The current validation system checks common model issues, including:

- Duplicate component instance names.
- Duplicate link names.
- Missing required parameter values.
- Missing required link values such as latency.

Plugin-provided property definitions can mark parameters as required.

## Required parameters

A parameter is treated as required when plugin item details mark it as required. The SST plugin maps `sst-info` defaults of `<required>` to required FUSE properties.

Example:

```text
clock *
num_cores *
```

A value must be supplied before saving.

## Validation feedback

When save validation fails:

- FUSE shows one summary dialog listing issues.
- Affected component boxes receive a validation warning marker.
- Affected rows in the properties panel may be highlighted.
- The first affected component can be selected and centered.

## Fixing validation problems

1. Read the validation summary dialog.
2. Click a marked component.
3. Fill missing required values.
4. Rename duplicate instances or links.
5. Save again.

## Example validation errors

```text
cpu0: Required parameter 'clock' is missing a value.
cache0: Required parameter 'size' is missing a value.
link_3: Link latency is required.
```

## Plugin-specific validation

FUSE core currently handles generic validation. Plugins may add plugin-specific validation later through the plugin API.

Examples of future SST-specific validation:

- Memory sizes must include valid units.
- SST link latency strings must be parseable by SST.
- Required SST subcomponents must be attached.
