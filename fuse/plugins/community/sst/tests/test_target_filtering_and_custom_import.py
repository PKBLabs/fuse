
from __future__ import annotations

from fuse.plugins.community.sst.tests.conftest import (
    cache_component,
    custom_cpu_component,
    memcontroller_component,
    write_component_catalog,
    write_policy_catalog,
)


def test_bundled_catalog_bootstrap_registers_targets_and_keeps_versions_separate(sst_env):
    env = sst_env

    write_policy_catalog(env, "15.1.2")
    write_policy_catalog(env, "16.0.0")
    write_component_catalog(env, "15.1.2", [cache_component(default_line_size="32")])
    write_component_catalog(env, "16.0.0", [memcontroller_component()])

    plugin = env.sst_plugin.SSTPlugin()
    plugin.bootstrap_database()

    targets = plugin.list_targets()
    by_version = {target.framework_version: target for target in targets}

    assert {"15.1.2", "16.0.0"}.issubset(by_version)

    items_15 = plugin.load_palette_items(target_id=by_version["15.1.2"].target_id)
    items_16 = plugin.load_palette_items(target_id=by_version["16.0.0"].target_id)

    assert {item.type_name for item in items_15} == {"Cache"}
    assert {item.framework_version for item in items_15} == {"15.1.2"}

    assert {item.type_name for item in items_16} == {"MemController"}
    assert {item.framework_version for item in items_16} == {"16.0.0"}


def test_custom_target_does_not_pollute_bundled_baseline_target(sst_env):
    env = sst_env

    baseline = env.component_catalog.load_component_catalog = lambda version: {
        "schema_version": "1.0.0",
        "sst_version": version,
        "elements": [{"name": "memHierarchy", "description": "memHierarchy element"}],
        "components": [cache_component()],
    }

    baseline_catalog = baseline("16.0.0")
    baseline_path = env.tmp_path / "baseline.json"
    from fuse.plugins.community.sst.tests.conftest import write_catalog, make_catalog
    write_catalog(baseline_path, baseline_catalog)

    baseline_id = env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        baseline_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="baseline",
        is_default=True,
        clear_existing=True,
    )

    discovered_catalog = make_catalog("16.0.0", [cache_component(), custom_cpu_component()])
    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — pytest custom",
        source_fingerprint="pytestcustom",
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        entries=env.component_catalog.classify_discovered_catalog(
            version="16.0.0",
            discovered_catalog=discovered_catalog,
            baseline_catalog=baseline_catalog,
        ),
        previous_enabled_keys=set(),
        command_text="sst-info",
    )

    custom_key = env.component_catalog.component_key(custom_cpu_component())
    custom_target_id, _, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={custom_key},
        project_uid="project-a",
    )

    plugin = env.sst_plugin.SSTPlugin()

    baseline_items = plugin.load_palette_items(target_id=str(baseline_id))
    custom_items = plugin.load_palette_items(target_id=str(custom_target_id))

    assert {item.type_name for item in baseline_items} == {"Cache"}
    assert {item.type_name for item in custom_items} == {"Cache", "CustomCPU"}
