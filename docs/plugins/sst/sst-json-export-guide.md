# SST JSON Export Guide

FUSE v0.5.0 focuses on making SST-only FUSE models export to SST JSON that can be passed to SST without hand editing.

The `.fse` file remains the editable FUSE project file. The `.sst.json` file is a generated simulator artifact. Users should edit the `.fse` model in FUSE and regenerate SST JSON rather than manually editing generated JSON.

## Release goal

The v0.5.0 SST export goal is:

```text
Build SST model in FUSE -> validate for SST export -> export SST JSON -> run with SST without manual JSON changes.
```

This guide documents the expected workflow, validation rules, JSON mapping, verification commands, export reports, and known limitations for that goal.

## Export workflow

1. Create or open an SST project.
2. Select the intended SST target/version in Project Settings.
3. Build the model using SST components from that target.
4. Run **Validate for Export**.
5. Fix all errors shown in the Validation Results panel.
6. Review any warnings. Warnings do not block export, but they identify connections or metadata that FUSE could not prove completely.
7. Choose **File -> Export -> SST JSON...**.
8. Save the generated `.sst.json` file.
9. Run the exported file with SST.

Recommended filename convention:

```text
model.fse          # editable FUSE project
model.sst.json     # generated SST JSON
model.export-report.json  # optional export warning/report sidecar
```

## Validation requirements before export

SST JSON export requires the model to be a valid SST-only graph. FUSE blocks export when it detects errors such as:

- no components in the model
- non-SST components in an SST export graph
- missing or duplicate component instance names
- missing or duplicate link names
- missing component type metadata
- links whose source or target component no longer exists
- links missing source/target ports
- unattached SST SubComponent instances
- subcomponent attachments with missing parent/child nodes
- subcomponent attachments without a slot name
- subcomponent interface mismatches
- multiple SST target/version IDs in the same export graph

Warnings are reported for uncertain but potentially exportable cases, such as:

- link ports that are not present in available component metadata
- link compatibility marked as uncertain by FUSE
- subcomponent interface metadata that is incomplete
- link endpoint latencies that are blank and must be defaulted to `1ns`

Warnings are shown in Validation Results and can also be written to an export report when using the exporter programmatically.

## FUSE validation vs SST export validation

FUSE distinguishes between two related checks:

| Validation type | Purpose | Blocks SST export? |
|---|---|---|
| FUSE model validation | Checks the generic editor graph: duplicate names, dangling links, missing required values, and internal consistency. | Sometimes, if the problem also prevents SST export. |
| SST export validation | Checks whether the current graph can be converted into SST JSON for the selected SST target/version. | Yes, errors block export. Warnings do not. |

A model can be valid as an editable FUSE model but not export-ready for SST. For example, a mixed SST/Gem5 model can be saved as `.fse`, but SST JSON export must reject it until hybrid export exists.

## Plugin ownership and core separation

SST JSON export is implemented by the SST plugin. The FUSE core owns generic concepts such as the scene graph, validation result display, file dialogs, and plugin dispatch. It does not encode the SST JSON schema, SST port rules, or SST subcomponent-slot semantics.

The SST plugin advertises its export format as `sst.json`, validates SST export readiness, writes the generated JSON, and optionally writes a sidecar export report when warnings are present. This keeps SST-specific behavior isolated from Gem5 and from plugin-agnostic core editor code.

## Expected SST JSON shape

FUSE exports a deterministic JSON object with this top-level shape:

```json
{
  "program_options": {},
  "shared_params": [],
  "statistics_options": {},
  "components": [],
  "statistics_group": [],
  "links": []
}
```

The top-level sections are always present so downstream tests and review tools can rely on a stable structure.

## Component mapping

Each root component is emitted as:

```json
{
  "name": "cache0",
  "type": "memHierarchy.Cache",
  "params": {
    "cache_size": "32KiB"
  }
}
```

Mapping rules:

| FUSE field | SST JSON field |
|---|---|
| component instance name | `components[].name` |
| SST element + component name | `components[].type` |
| non-empty component parameters | `components[].params` |
| optional rank/thread metadata | component partition metadata, when present |
| attached SubComponents | `components[].subcomponents` |

Parameters with empty names or empty string values are omitted. Non-empty scalar values such as strings, numbers, and booleans are preserved.

## SubComponent mapping

SubComponents are nested under their parent component and include their slot name:

```json
{
  "name": "cpu0",
  "type": "prospero.prosperoCPU",
  "subcomponents": [
    {
      "name": "mmu0",
      "type": "mmu.simpleMMU",
      "slot_name": "mmu"
    }
  ]
}
```

Mapping rules:

| FUSE field | SST JSON field |
|---|---|
| attachment parent | parent component containing `subcomponents` |
| child SubComponent instance name | `subcomponents[].name` |
| child SST element + component name | `subcomponents[].type` |
| attachment slot name | `subcomponents[].slot_name` |
| child parameters | `subcomponents[].params`, when non-empty |

A SubComponent node that is not attached to a parent slot is not exportable.

## Link mapping

Links are exported with endpoint component names, ports, and endpoint latencies:

```json
{
  "name": "link_cpu_cache",
  "noCut": false,
  "nonlocal": false,
  "left": {
    "component": "cpu0",
    "port": "cache",
    "latency": "250ps"
  },
  "right": {
    "component": "cache0",
    "port": "highlink",
    "latency": "1ns"
  }
}
```

Mapping rules:

| FUSE field | SST JSON field |
|---|---|
| link name | `links[].name` |
| source component instance | `links[].left.component` |
| source port | `links[].left.port` |
| source endpoint latency | `links[].left.latency` |
| target component instance | `links[].right.component` |
| target port | `links[].right.port` |
| target endpoint latency | `links[].right.latency` |
| no-cut flag, when modeled | `links[].noCut` |
| non-local flag, when modeled | `links[].nonlocal` |

Endpoint component names are resolved from the current component instances during export. This prevents stale link endpoint names from appearing in the generated JSON after a component is renamed.

If a link endpoint latency is not explicitly set, the exporter uses the default `1ns` latency and records a warning in the export-readiness report. This keeps the generated JSON runnable while still telling the user that FUSE had to fill in missing timing data.

## Name and ordering behavior

FUSE preserves component and link names in the generated JSON. Automatically generated instance names remain stable unless the user renames them. Export validation requires links to have stable, unique names for the same reason component instance names must be stable: SST JSON should be repeatable, reviewable, and runnable without post-export editing.

Exporter output is deterministic:

- root components are sorted by instance name and node ID
- subcomponent attachments are sorted by parent, slot, name, and attachment ID
- links are sorted by link name and link ID
- parameters are sorted by parameter name

This makes exported JSON suitable for golden-file regression tests and code review.

## Export reports and warnings

FUSE does not embed warning annotations into SST JSON. The generated JSON should stay focused on the SST simulator input format.

When export validation produces warnings, FUSE can write a sidecar export report. The report is intended for users and CI logs, not for SST itself. It should include:

- export status
- errors, if export was blocked
- warnings, if export proceeded with assumptions
- affected component/link/subcomponent names where available
- messages explaining what FUSE inferred or defaulted

Example warning report entry:

```json
{
  "severity": "warning",
  "scope": "link",
  "object": "link_cpu_cache",
  "message": "Link source latency was not set; exporter will use 1ns."
}
```

## Full export contract coverage

The v0.5.0 exporter contract covers the SST JSON fields that FUSE currently emits:

- top-level `program_options`, `shared_params`, `statistics_options`, `components`, `statistics_group`, and `links` sections
- component `name`, `type`, optional `params`, and optional partition metadata
- nested `subcomponents` with `slot_name`
- link `name`, `noCut`, `nonlocal`, `left`, and `right` endpoint objects
- endpoint `component`, `port`, and `latency` fields

The test suite includes a full golden-style export model that verifies components, parameters, links, subcomponents, generated names, explicit latencies, default latency warnings, and deterministic ordering.

## Minimal sample model

A minimal exportable SST model should contain:

1. At least one SST root component.
2. A valid SST component type from the selected SST target/version.
3. Required parameters set or valid defaults available.
4. Stable component and link names.
5. Valid links only when both endpoints and ports exist.

For a linked model, use two compatible SST components and a link with explicit endpoint latencies. For a subcomponent model, attach each SubComponent to a parent component slot before export.

## Manual verification with SST

After export, verify the JSON with SST:

```bash
sst --run-mode=init path/to/model.sst.json
```

A successful `--run-mode=init` check means SST accepted the generated configuration structure. It does not guarantee the simulation is physically meaningful or algorithmically correct.

Where practical, also run a small simulation smoke test:

```bash
sst path/to/model.sst.json
```

Recommended manual release check:

```bash
# 1. Open FUSE and export an SST-only sample model.
# 2. Confirm the file exists and is readable JSON.
python -m json.tool path/to/model.sst.json >/dev/null

# 3. Ask SST to initialize the configuration.
sst --run-mode=init path/to/model.sst.json

# 4. Optionally run the model if it is expected to terminate quickly.
sst path/to/model.sst.json
```

## Automated verification

The non-live test suite verifies deterministic JSON shape, validation errors, warning reports, subcomponent serialization, and link endpoint mapping without requiring SST.

The live SST suite verifies exporter behavior against a real SST installation where suitable catalog components are available. Live tests are marked with `sst_live` and should be run in an SST-capable environment:

```bash
pytest -m "sst_live"
```

For release preparation, run both:

```bash
pytest -m "not sst_live and not gem5_live"
pytest -m "sst_live"
```

## Troubleshooting

### Export is blocked because a non-SST component exists

SST JSON export is intentionally SST-only. Remove Gem5 or other simulator components, or save the mixed model as `.fse` without exporting it to SST JSON.

### Export is blocked because a SubComponent is unattached

Attach the SubComponent to a valid parent slot. A standalone SST SubComponent node cannot become a root SST JSON component.

### Export succeeds but reports defaulted latency warnings

Edit the link properties and set explicit endpoint latencies. If the default `1ns` value is intentional, the warning can be treated as informational.

### SST rejects the JSON even though FUSE validation passed

Run with `sst --run-mode=init` and inspect the SST error. Common causes include component-specific parameter combinations that are not fully described by `sst-info`, SST version drift, or component behavior that requires additional runtime files or environment setup.

### Ports appear invalid after changing SST target/version

Refresh or re-import SST metadata for the selected target/version, then rerun export validation. Target migration may be needed if component or port names changed between SST versions.

## Known limitations

- Mixed SST/Gem5 models can be saved as FUSE projects, but SST JSON export is SST-only.
- FUSE validates graph completeness and exportability, but it cannot prove every SST model is semantically meaningful.
- Some SST components require parameter combinations that are not fully expressible from `sst-info` metadata alone.
- Warning annotations are not embedded into the SST JSON itself; they are shown in FUSE validation results and can be emitted as a separate export report.
- Remote/cluster execution of the exported JSON is outside the JSON exporter. Use the generated file with your normal SST run environment.
- Advanced SST features not represented in the FUSE model graph are not exported until explicit FUSE UI/model support exists for them.

## Unsupported or not-yet-modeled SST features

The exporter should reject or omit features that FUSE does not model explicitly. Known areas that may need future support include:

- custom Python configuration logic outside SST JSON
- runtime files or external resources required by specific components
- advanced statistics groups beyond the currently modeled metadata
- complex partitioning or rank/thread placement beyond stored component metadata
- simulator-specific features not visible in imported `sst-info` metadata
- hybrid SST/Gem5 execution or co-simulation

Unsupported features should be documented, validated where possible, and added to tests when FUSE gains first-class support for them.
