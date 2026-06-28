# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import pytest

from fuse.plugins.community.sst.tests.catalog_test_helpers import (
    baseline_catalog,
    custom_cpu_component,
    discovered_custom_catalog,
    write_catalog,
)
from fuse.plugins.community.sst.tests.fake_toolchains import command_result, local_toolchain
from fuse.plugins.community.sst.tests.scene_test_helpers import make_node, scene_with_nodes


pytestmark = [pytest.mark.sst, pytest.mark.sst_external]


def _seed_target(env):
    base = baseline_catalog("16.0.0")
    discovered = discovered_custom_catalog("16.0.0")

    baseline_path = write_catalog(env.tmp_path / "baseline-runtime-edge.json", base)
    env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        baseline_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="baseline",
        is_default=True,
        clear_existing=True,
    )

    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — runtime edge",
        source_fingerprint="runtime-edge",
        discovered_catalog=discovered,
        baseline_catalog=base,
        entries=env.component_catalog.classify_discovered_catalog(
            version="16.0.0",
            discovered_catalog=discovered,
            baseline_catalog=base,
        ),
        previous_enabled_keys=set(),
        command_text="sst-info",
    )

    return env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={env.component_catalog.component_key(custom_cpu_component())},
        project_uid="runtime-edge-project",
    )[:2]


def test_runtime_verification_stops_on_version_mismatch_before_component_scan(sst_env, monkeypatch):
    env = sst_env
    target_id, target_label = _seed_target(env)

    calls = {"sst_info": 0}
    version_result = command_result(env.get_sstinfo, stdout="SST 15.1.2", command=["sst-info", "--version"])

    monkeypatch.setattr(
        env.component_catalog,
        "validate_sst_toolchain",
        lambda **kwargs: (False, "Expected SST 16.0.0 but found SST 15.1.2", version_result),
    )

    def fake_get_sstinfo_for_toolchain(*args, **kwargs):
        calls["sst_info"] += 1
        raise AssertionError("full sst-info should not run after version mismatch")

    monkeypatch.setattr(
        env.component_catalog,
        "get_sstinfo_for_toolchain",
        fake_get_sstinfo_for_toolchain,
    )

    report = env.component_catalog.verify_project_sst_runtime(
        scene=scene_with_nodes(
            make_node(1, "custom_cpu0", "customElement", "CustomCPU", target_id=target_id)
        ),
        framework_version_id=target_id,
        expected_version="16.0.0",
        target_label=target_label,
        toolchain=local_toolchain(),
    )

    assert not report.ok
    assert calls["sst_info"] == 0
    assert "Expected SST 16.0.0" in report.message()


def test_runtime_verification_warns_for_enabled_unused_component_missing_from_runtime(sst_env, monkeypatch):
    env = sst_env
    target_id, target_label = _seed_target(env)

    result = command_result(env.get_sstinfo, stdout="runtime metadata")
    monkeypatch.setattr(
        env.component_catalog,
        "validate_sst_toolchain",
        lambda **kwargs: (True, "ok", result),
    )
    monkeypatch.setattr(
        env.component_catalog,
        "get_sstinfo_for_toolchain",
        lambda *args, **kwargs: result,
    )
    monkeypatch.setattr(
        env.component_catalog,
        "parse_sstinfo_output",
        lambda stdout: ([], [
            env.get_sstinfo.ParsedComponent(
                element_name="memHierarchy",
                name="Cache",
                description="Cache",
                is_subcomp=0,
            )
        ]),
    )

    report = env.component_catalog.verify_project_sst_runtime(
        scene=scene_with_nodes(
            make_node(1, "cache0", "memHierarchy", "Cache", target_id=target_id)
        ),
        framework_version_id=target_id,
        expected_version="16.0.0",
        target_label=target_label,
        toolchain=local_toolchain(),
    )

    assert report.ok
    assert not report.missing_used_component_keys
    assert env.component_catalog.component_key(custom_cpu_component()) in report.missing_enabled_component_keys
    assert report.warnings
    assert "not used by the current model" in report.message()


def test_runtime_verification_reports_sst_info_command_failure(sst_env, monkeypatch):
    env = sst_env
    target_id, target_label = _seed_target(env)

    version_result = command_result(env.get_sstinfo, stdout="SST 16.0.0")
    failed_result = command_result(
        env.get_sstinfo,
        stdout="",
        stderr="library load failed",
        return_code=2,
    )
    monkeypatch.setattr(
        env.component_catalog,
        "validate_sst_toolchain",
        lambda **kwargs: (True, "ok", version_result),
    )
    monkeypatch.setattr(
        env.component_catalog,
        "get_sstinfo_for_toolchain",
        lambda *args, **kwargs: failed_result,
    )

    report = env.component_catalog.verify_project_sst_runtime(
        scene=scene_with_nodes(
            make_node(1, "custom_cpu0", "customElement", "CustomCPU", target_id=target_id)
        ),
        framework_version_id=target_id,
        expected_version="16.0.0",
        target_label=target_label,
        toolchain=local_toolchain(),
    )

    assert not report.ok
    assert "sst-info failed" in report.message()
    assert "library load failed" in report.message()
