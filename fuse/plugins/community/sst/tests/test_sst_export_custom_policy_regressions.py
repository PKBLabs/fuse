# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import pytest

from fuse.plugins.community.sst.tests.catalog_test_helpers import (
    baseline_catalog,
    cache_component,
    custom_cpu_component,
    discovered_changed_catalog,
    discovered_custom_catalog,
    write_catalog,
)
from fuse.plugins.community.sst.tests.scene_test_helpers import (
    make_node,
    scene_with_nodes,
)


pytestmark = [pytest.mark.sst, pytest.mark.sst_external, pytest.mark.golden]


def _seed_custom_target(env, *, catalog, enabled_keys, fingerprint: str = "export-custom-policy-fixture"):
    base = baseline_catalog("16.0.0")
    baseline_path = write_catalog(env.tmp_path / "baseline-export.json", base)
    env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        baseline_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="pytest baseline",
        is_default=True,
        clear_existing=True,
    )

    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — pytest export custom",
        source_fingerprint=fingerprint,
        discovered_catalog=catalog,
        baseline_catalog=base,
        entries=env.component_catalog.classify_discovered_catalog(
            version="16.0.0",
            discovered_catalog=catalog,
            baseline_catalog=base,
        ),
        previous_enabled_keys=set(),
        command_text="sst-info",
    )
    return env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys=enabled_keys,
        project_uid="export-regression",
    )[0]


def _warning_messages(report):
    return [str(getattr(issue, "message", "") or "") for issue in report.warnings]


def test_custom_component_export_uses_user_parameters_without_bundled_default_injection(sst_env):
    from fuse.plugins.community.sst.export_json import build_sst_json_dict, validate_sst_json_export

    env = sst_env
    custom_key = env.component_catalog.component_key(custom_cpu_component())
    target_id = _seed_custom_target(
        env,
        catalog=discovered_custom_catalog("16.0.0"),
        enabled_keys={custom_key},
    )

    scene = scene_with_nodes(
        make_node(
            1,
            "custom_cpu0",
            "customElement",
            "CustomCPU",
            target_id=target_id,
            parameters={
                "custom_width": "8",
                "empty_should_drop": "",
            },
        )
    )

    data = build_sst_json_dict(scene)
    exported = data["components"][0]

    assert exported["type"] == "customElement.CustomCPU"
    assert exported["params"] == {"custom_width": "8"}

    report = validate_sst_json_export(scene)
    assert report.can_export
    assert any("uses custom SST components" in message for message in _warning_messages(report))


def test_changed_baseline_component_export_reports_grouped_warning_without_custom_spam(sst_env):
    from fuse.plugins.community.sst.export_json import build_sst_json_dict, validate_sst_json_export

    env = sst_env
    cache_key = env.component_catalog.component_key(cache_component())
    target_id = _seed_custom_target(
        env,
        catalog=discovered_changed_catalog("16.0.0"),
        enabled_keys={cache_key},
    )

    scene = scene_with_nodes(
        make_node(
            1,
            "cache0",
            "memHierarchy",
            "Cache",
            target_id=target_id,
            parameters={"cache_line_size": "128"},
        )
    )

    data = build_sst_json_dict(scene)
    assert data["components"][0]["params"]["cache_line_size"] == "128"

    report = validate_sst_json_export(scene)
    messages = _warning_messages(report)

    assert report.can_export
    assert any("metadata differs from the bundled baseline" in message for message in messages)
    assert any("memHierarchy.Cache" in message for message in messages)
    assert not any("uses custom SST components" in message for message in messages)


def test_export_policy_diagnostics_ignore_non_sst_and_multi_target_scenes(sst_env):
    from fuse.plugins.community.sst.component_catalog import export_policy_diagnostics_for_scene
    from fuse.plugins.community.sst.tests.scene_test_helpers import FakeNode, make_sst_component

    env = sst_env
    custom_key = env.component_catalog.component_key(custom_cpu_component())
    target_id = _seed_custom_target(
        env,
        catalog=discovered_custom_catalog("16.0.0"),
        enabled_keys={custom_key},
    )

    other_target_id = _seed_custom_target(
        env,
        catalog=discovered_custom_catalog("16.0.0"),
        enabled_keys={custom_key},
        fingerprint="export-custom-policy-fixture-other",
    )

    scene = scene_with_nodes(
        make_node(
            1,
            "custom_cpu0",
            "customElement",
            "CustomCPU",
            target_id=target_id,
            parameters={"custom_width": "8"},
        ),
        make_node(
            2,
            "custom_cpu1",
            "customElement",
            "CustomCPU",
            target_id=other_target_id,
            parameters={"custom_width": "4"},
        ),
        FakeNode(
            3,
            "gem5_like",
            make_sst_component(
                "gem5Element",
                "Gem5CPU",
                plugin_id="gem5",
                target_id="gem5-target",
            ),
            {},
        ),
    )

    diagnostics = export_policy_diagnostics_for_scene(scene)

    assert diagnostics.custom_component_keys == set()
    assert diagnostics.changed_component_keys == set()
    assert custom_key in diagnostics.used_component_keys
