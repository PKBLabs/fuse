# Test Matrix

## Core/app tests

| Area | Tests | Location |
|---|---|---|
| App launch | launch/shutdown subprocess | `fuse/tests/test_app_launch.py` |
| Main window | construct, show, close | `fuse/tests/test_main_window.py` |
| Plugin discovery | SST/gem5 discovery, broken plugin handling | `fuse/tests/test_plugin_discovery.py` |
| Database | core and plugin table initialization | `fuse/tests/test_database_initialization.py` |
| Project I/O | `.fse` save/load and validation | `fuse/tests/test_project_io.py` |
| Model roundtrip | save/load components and links | `fuse/tests/test_fuse_model_roundtrip.py` |
| Resources | logo and icon path resolution | `fuse/tests/test_resource_paths.py` |
| Routing | path simplification and route validity | `fuse/tests/test_routing.py` |
| Validation | duplicate names, required params | `fuse/tests/test_validation.py` |
| UI | splash/about/palette | `fuse/tests/` |

## SST plugin tests

| Area | Tests | Location |
|---|---|---|
| Schema | `sst_*` tables created | `fuse/plugins/community/sst/tests/test_sst_schema.py` |
| Parser | sample `sst-info` parsing | `fuse/plugins/community/sst/tests/test_sst_parser.py` |
| Parser edge cases | brackets, colons, missing units | `test_sst_parser_edge_cases.py` |
| Import | sync parsed metadata to database | `test_sst_import.py` |
| DB utils | plugin query helpers | `test_sst_db_utils.py` |
| Negative DB cases | missing records | `test_sst_db_utils_negative.py` |
| File import | `--from-file` behavior | `test_sst_file_import.py` |
| Command sync | monkeypatched `sst-info` | `test_sst_sync_command.py` |
| Live SST | real `sst-info` integration | `test_sst_live_integration.py` |

## gem5 plugin tests

| Area | Tests | Location |
|---|---|---|
| Live gem5 | real gem5 binary smoke test | `fuse/plugins/community/gem5/tests/test_gem5_live_integration.py` |

## CI mapping

| Workflow | Command |
|---|---|
| Core Tests | `pytest -q -m "not sst_live and not gem5_live"` |
| SST Integration | `pytest -q -m "sst_live"` |
| gem5 Integration | `pytest -q -m "gem5_live"` |
