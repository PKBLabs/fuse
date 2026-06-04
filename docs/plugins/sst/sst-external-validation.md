# SST External Validation Harness

The SST plugin owns a backend-only acceptance harness for checking FUSE-generated SST JSON against real SST tooling. This harness is intended for FUSE developers, CI jobs, and release validation. It is not a user-facing workflow and should not be surfaced in the normal editor UI.

The harness lives entirely in the SST plugin:

```text
fuse/plugins/community/sst/external_validation/
fuse/plugins/community/sst/tests/test_sst_external_validation.py
```

Do not move SST-specific acceptance logic into FUSE core or core tests. Core remains plugin-agnostic; the SST plugin owns SST JSON export validation, SST runtime checks, `sst-info` dependency checks, and any `sst-ext-tests`-inspired behavior.

## Purpose

The harness answers a deeper release-validation question than the normal UI validator:

```text
Can representative models generated through the SST plugin exporter be accepted by real SST tooling?
```

The intended acceptance ladder is:

```text
SST plugin fixture/model builder
  -> SST export-readiness validation
  -> SST JSON export
  -> JSON syntax check with python -m json.tool
  -> expected SST JSON contract checks
  -> optional SST element/component availability checks through sst-info
  -> optional sst --run-mode=init
  -> optional short SST runtime smoke check
  -> optional expected output-file/stdout/stderr checks
```

The default test suite still runs quickly and does not require SST. Real external validation is opt-in.

## Test marker

External SST acceptance tests use the `sst_ext` pytest marker. Run only the backend harness tests with:

```bash
cd ~/research/fuse/fuse
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -m "sst_ext"
```

The normal dependency-light suite should continue to exclude live/external simulator work:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q \
  -m "not sst_live and not gem5_live and not sst_ext"
```

## Environment gates

External validation is skipped unless it is explicitly enabled:

```bash
export FUSE_ENABLE_SST_EXT_TESTS=1
```

When this variable is not set to a truthy value, the harness still exercises generated fixture export and JSON checks, but real SST execution stages are reported as skipped.

Optional interoperability with a local `sst-ext-tests` checkout can be enabled with:

```bash
export SST_EXT_TESTS_ROOT=/path/to/sst-ext-tests
```

This path is validated for developer diagnostics only. FUSE does not vendor `sst-ext-tests`, and the SST plugin must not require it for normal tests.

## Fixture metadata

Fixtures use `SSTExternalValidationMetadata` to describe their backend acceptance requirements. Metadata can include:

| Field | Meaning |
|---|---|
| `name` | Stable fixture name used in reports and generated file names. |
| `description` | Developer-facing explanation of what the fixture covers. |
| `min_sst_version` / `max_sst_version` | Optional SST version bounds. |
| `required_elements` | SST element libraries required by the fixture. |
| `required_components` | Specific SST components expected to be available through `sst-info`. |
| `run_mode` | `json`, `init`, or `run`. |
| `timeout_seconds` | Command timeout for external stages. |
| `runtime_args` | Additional arguments for runtime-mode SST execution. |
| `expected_stdout_fragments` / `expected_stderr_fragments` | Output fragments required for runtime-mode fixtures. |
| `expected_output_files` | Runtime-generated files expected after execution. |
| `external_suite_tags` | Tags for future filtering or optional external-suite interoperability. |

Run modes mean:

| Run mode | Behavior |
|---|---|
| `json` | Export and validate JSON only. No real SST execution is attempted. |
| `init` | Run `sst --run-mode=init` when external validation is enabled and requirements are available. |
| `run` | Run SST normally with optional runtime arguments and expected-output checks. |

## Current fixture coverage

The backend fixture registry currently includes representative generated models such as:

| Fixture | Run mode | Coverage |
|---|---|---|
| `minimal_two_component_link` | `json` | Basic component/link export contract and top-level JSON structure. |
| `explicit_latency_parameters` | `json` | Typed parameters, empty-parameter omission, stable names, and asymmetric endpoint latencies. |
| `subcomponent_slot_assignment` | `json` | Native SST SubComponent nesting and slot-name export. |
| `simple_element_example_init` | `init` | Real-SST init path using the `simpleElementExample` element when available. |

Fixture coverage should grow as the SST plugin exposes more SST features. For each supported SST feature exposed by the plugin, prefer at least one backend fixture that validates export behavior and, where practical, runs through real SST initialization or runtime smoke checks.

## Adding a new fixture

Add new fixtures under the SST plugin, usually in:

```text
fuse/plugins/community/sst/external_validation/fixtures.py
```

A new fixture should:

1. Build a model through the SST plugin fixture helpers rather than hand-writing final JSON.
2. Define precise `SSTExternalValidationMetadata`.
3. Declare required SST elements/components when real SST execution is expected.
4. Use `run_mode="json"` until a real SST-compatible component model is available.
5. Add focused assertions in `fuse/plugins/community/sst/tests/test_sst_external_validation.py`.
6. Remain backend-only and avoid any UI/user-facing dependency.

## Relationship to `sst-ext-tests`

`sst-ext-tests` is useful as an external reference and possible interoperability point, especially for metadata conventions such as version bounds, dependency-aware skips, and CTest-style external validation. FUSE should not vendor it and should not treat its current test corpus as the complete definition of valid SST behavior.

The FUSE-specific goal is:

```text
Representative FUSE-generated SST JSON fixtures validate, initialize, and where practical run under real SST installations that satisfy their metadata requirements.
```

That keeps the user-facing product simple while giving FUSE developers stronger release confidence.
