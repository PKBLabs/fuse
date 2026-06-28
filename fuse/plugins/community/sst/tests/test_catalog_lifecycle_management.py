from __future__ import annotations

from fuse.core.model.project_settings import ToolchainSettings
from fuse.plugins.community.sst.tests.conftest import (
    cache_component,
    custom_cpu_component,
    make_catalog,
    write_catalog,
    write_component_catalog,
    write_policy_catalog,
)


def _make_custom_target(env, *, project_uid: str = "project-a"):
    write_policy_catalog(env, "16.0.0")
    write_component_catalog(env, "16.0.0", [cache_component()])

    plugin = env.sst_plugin.SSTPlugin()
    plugin.bootstrap_database()

    targets = {
        target.framework_version: target
        for target in plugin.list_targets()
        if target.framework_version == "16.0.0"
    }
    baseline_target = targets["16.0.0"]

    baseline_catalog = env.component_catalog.load_component_catalog("16.0.0")
    discovered_catalog = make_catalog(
        "16.0.0",
        [cache_component(), custom_cpu_component()],
    )

    toolchain = ToolchainSettings(
        backend="local",
        tool_paths={
            "sstInfo": "/opt/sst-16/bin/sst-info",
            "sst": "/opt/sst-16/bin/sst",
        },
    )
    fingerprint = env.component_catalog._toolchain_fingerprint(
        "16.0.0",
        toolchain,
        project_uid=project_uid,
    )

    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — Local custom (/opt/sst-16/bin)",
        source_fingerprint=fingerprint,
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        entries=env.component_catalog.classify_discovered_catalog(
            version="16.0.0",
            discovered_catalog=discovered_catalog,
            baseline_catalog=baseline_catalog,
        ),
        previous_enabled_keys=set(),
        command_text="/opt/sst-16/bin/sst-info",
    )

    custom_key = env.component_catalog.component_key(custom_cpu_component())
    custom_target_id, custom_label, custom_path = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={custom_key},
        project_uid=project_uid,
    )

    return baseline_target, custom_target_id, toolchain, custom_label, custom_path


def test_catalog_source_summary_reports_custom_counts_and_stale_toolchain(sst_env):
    env = sst_env
    baseline_target, custom_target_id, toolchain, _, _ = _make_custom_target(env)

    summary = env.component_catalog.catalog_source_summary_for_target(
        custom_target_id,
        toolchain=toolchain,
        project_uid="project-a",
    )

    assert summary.is_custom
    assert summary.version == "16.0.0"
    assert summary.enabled_custom_count == 1
    assert summary.enabled_changed_count == 0
    assert summary.baseline_component_count == 1
    assert not summary.fingerprint_stale
    assert "Local custom" in summary.message()

    stale_toolchain = ToolchainSettings(
        backend="local",
        tool_paths={"sstInfo": "/different/sst-info"},
    )
    stale_summary = env.component_catalog.catalog_source_summary_for_target(
        custom_target_id,
        toolchain=stale_toolchain,
        project_uid="project-a",
    )

    assert stale_summary.fingerprint_stale
    assert "differ from the toolchain used to create this custom catalog" in stale_summary.message()

    baseline_summary = env.component_catalog.catalog_source_summary_for_target(
        baseline_target.target_id,
        toolchain=toolchain,
        project_uid="project-a",
    )

    assert baseline_summary.is_baseline
    assert baseline_summary.component_count == 1


def test_revert_and_delete_custom_catalog_preserves_bundled_baseline(sst_env):
    env = sst_env
    baseline_target, custom_target_id, _, _, custom_path = _make_custom_target(env)

    reverted = env.component_catalog.revert_target_to_bundled_baseline(custom_target_id)

    assert reverted == (baseline_target.target_id, baseline_target.display_name)

    ok, message = env.component_catalog.delete_custom_catalog_target(
        custom_target_id,
        force=True,
    )

    assert ok, message
    assert not custom_path.exists()

    plugin = env.sst_plugin.SSTPlugin()
    targets = plugin.list_targets()

    assert baseline_target.target_id in {target.target_id for target in targets}
    assert str(custom_target_id) not in {target.target_id for target in targets}

    baseline_items = plugin.load_palette_items(target_id=baseline_target.target_id)
    assert {item.type_name for item in baseline_items} == {"Cache"}
