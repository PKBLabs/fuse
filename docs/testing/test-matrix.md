# Test Matrix

## Core/app tests

| Area | Tests | Location |
|---|---|---|
| App launch | launch/shutdown subprocess | `fuse/tests/test_app_launch.py` |
| Main window | construct, show, close | `fuse/tests/test_main_window.py` |
| Plugin discovery/manager | SST/gem5 discovery, broken plugin handling, manifest loading, plugin filtering, item detail dispatch | `fuse/tests/test_plugin_discovery.py`, `fuse/tests/test_discovery_and_plugin_manager_extended.py` |
| Plugin metadata validation | invalid manifests/metadata handling | `fuse/tests/test_plugin_metadata_validation.py` |
| Database | core and plugin table initialization | `fuse/tests/test_database_initialization.py` |
| Component palette | component catalog/list and palette population | `fuse/tests/test_component_palette.py` |
| Component drag metadata | drag payload serialization/deserialization | `fuse/tests/test_component_definition_drag.py` |
| Model-view drop | drag/drop creation and drop coordinate conversion | `fuse/tests/test_model_view_component_drop.py` |
| Component instances | unique default names, outline/callbacks, dirty state | `fuse/tests/test_component_instance_naming_outline_dirty.py` |
| Undo/redo and unsaved indicator | component creation/deletion/property edit history, action enabled state, dirty indicator | `fuse/tests/test_undo_redo_history.py` |
| Properties panel | parameter display, input validation, write-back, dirty state | `fuse/tests/test_properties_panel_parameter_editing.py` |
| Project I/O | `.fse` save/load, validation, endpoint latencies, plugin metadata, subcomponent attachments, legacy compatibility | `fuse/tests/test_project_io.py` |
| Model roundtrip | save/load components and links | `fuse/tests/test_fuse_model_roundtrip.py` |
| Resources | logo and icon path resolution | `fuse/tests/test_resource_paths.py` |
| Routing | path simplification and route validity | `fuse/tests/test_routing.py` |
| Validation | duplicate names, required params, link endpoint latencies, plugin validation delegation, subcomponent attachments | `fuse/tests/test_validation.py`, `fuse/tests/test_validation_core_extended.py` |
| UI | splash/about/palette, variable ports, model outline, dirty state | `fuse/tests/` |
| Project/plugin settings | project settings, plugin settings, toolchain settings, legacy field compatibility | `fuse/tests/test_project_settings.py` |
| Toolchains | local/SSH command providers, executable discovery, version parsing and match policies | `fuse/tests/test_toolchain_utilities.py`, `fuse/tests/test_discovery_and_plugin_manager_extended.py` |
| Plugin API models | compatibility result/report and migration plan helpers | `fuse/tests/test_plugin_api_models.py` |

## Requested behavior coverage

| Behavior | Test location |
|---|---|
| Component catalog/list | `test_component_palette.py` |
| Population of component list from database/plugin metadata | `test_component_palette.py`, `test_database_initialization.py` |
| Handling invalid metadata files/manifests | `test_plugin_metadata_validation.py`, `test_plugin_discovery.py` |
| Drag/drop behavior for new component creation | `test_component_definition_drag.py`, `test_model_view_component_drop.py` |
| Creation of component instance upon drop | `test_model_view_component_drop.py` |
| Conversion of drop position into model coordinates | `test_model_view_component_drop.py` |
| Component addition to model outline/callbacks | `test_component_instance_naming_outline_dirty.py` |
| Unique default component names | `test_component_instance_naming_outline_dirty.py` |
| Parameter editor/properties panel from metadata | `test_properties_panel_parameter_editing.py` |
| Correct parameter information for selected component | `test_properties_panel_parameter_editing.py` |
| Parameter input type validation | `test_properties_panel_parameter_editing.py` |
| Required parameter validation | `test_validation.py`, `test_properties_panel_parameter_editing.py` |
| Writing component parameter updates back to model | `test_properties_panel_parameter_editing.py` |
| Dirty state after edits | `test_component_instance_naming_outline_dirty.py`, `test_properties_panel_parameter_editing.py`, `test_undo_redo_history.py` |
| Undo/redo for editing actions | `test_undo_redo_history.py` |
| Unsaved status-bar indicator | `test_undo_redo_history.py` |

## SST plugin tests

| Area | Tests | Location |
|---|---|---|
| Schema | `sst_*` tables created | `fuse/plugins/community/sst/tests/test_sst_schema.py` |
| Parser | sample `sst-info` parsing, variable ports, slot interfaces, multiline metadata | `fuse/plugins/community/sst/tests/test_sst_parser.py` |
| Parser edge cases | brackets, colons, missing units | `test_sst_parser_edge_cases.py` |
| Import | sync parsed metadata to database | `test_sst_import.py` |
| DB utils | plugin query helpers | `test_sst_db_utils.py` |
| Negative DB cases | missing records | `test_sst_db_utils_negative.py` |
| File import | `--from-file` behavior | `test_sst_file_import.py` |
| Command sync | monkeypatched `sst-info` | `test_sst_sync_command.py` |
| SST JSON export | SST JSON structure, endpoint latencies, nested subcomponents, validation errors, live execution where applicable | `test_sst_json*.py` |
| Compatibility/migration | target compatibility reports, migration plans, scene mutation/rerouting | `test_sst_compatibility_and_migration.py` |
| Plugin API behavior | target filtering, variable connector metadata, subcomponent connector metadata | `test_sst_plugin.py` |
| Live SST | real `sst-info`/`sst` integration | `test_sst_live_integration.py` |

## gem5 plugin tests

| Area | Tests | Location |
|---|---|---|
| Built-in metadata | gem5 targets/items/details, catalog integrity, connector/property mapping | `fuse/plugins/community/gem5/tests/` |
| Toolchain validation | command selection, version checks, non-gem5 output, command failures | `test_gem5_plugin_unit.py` |
| Export readiness | gem5 topology validation, target consistency, required CPU/xbar/memory connections | `test_gem5_plugin_unit.py` |
| Python export | generated gem5 Python configuration content and file writing | `test_gem5_plugin_unit.py` |
| Live gem5 | real gem5 binary smoke test | `fuse/plugins/community/gem5/tests/test_gem5_live_integration.py` |

## CI mapping

| Workflow | Command | Trigger summary |
|---|---|---|
| Core Tests | `pytest -q -m "not sst_live and not gem5_live"` | Pull requests and pushes to `main`/`develop` |
| SST Integration | `pytest -q -m "sst_live"` | Manual, weekly, relevant SST/plugin/core path pushes, and relevant PRs targeting `develop` |
| gem5 Integration | `pytest -q -m "gem5_live"` | Manual, weekly, relevant gem5/plugin/core path pushes, and relevant PRs targeting `develop` |

Adding dependency-light unit tests under `fuse/tests/`, `fuse/plugins/community/sst/tests/`, or `fuse/plugins/community/gem5/tests/` does not require changing the workflow triggers. Only add or edit workflow path filters when the CI execution policy itself changes.

## Release-readiness recommendation

Before tagging a release:

1. Run dependency-light tests locally.
2. Confirm Core Tests pass on GitHub Actions.
3. Rebuild simulator CI images only if Dockerfiles or simulator versions changed.
4. Confirm SST Integration Tests pass on the release-prep PR or run them manually on `develop`.
5. Confirm gem5 Integration Tests pass on the release-prep PR or run them manually on `develop`.
6. Confirm README testing badges are green for the intended branch/event.
