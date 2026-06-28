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
from fuse.plugins.community.sst.tests.fake_toolchains import local_toolchain, ssh_toolchain


pytestmark = [pytest.mark.sst, pytest.mark.sst_external]


def _seed_baseline(env, *, version: str = "16.0.0"):
    catalog = baseline_catalog(version)
    path = write_catalog(env.tmp_path / f"baseline-{version}.json", catalog)

    target_id = env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        path,
        version=version,
        label=f"SST {version}",
        source_kind="bundled-component-catalog",
        source_path="",
        command="pytest baseline",
        is_default=True,
        clear_existing=True,
    )
    return target_id, catalog


def _custom_discovery(env, *, project_uid: str, toolchain=None, version: str = "16.0.0"):
    toolchain = toolchain or local_toolchain()
    _, base = _seed_baseline(env, version=version)
    discovered = discovered_custom_catalog(version)
    fingerprint = env.component_catalog._toolchain_fingerprint(
        version,
        toolchain,
        project_uid=project_uid,
    )

    return env.component_catalog.SSTComponentDiscovery(
        version=version,
        source_label=f"SST {version} — pytest custom",
        source_fingerprint=fingerprint,
        discovered_catalog=discovered,
        baseline_catalog=base,
        entries=env.component_catalog.classify_discovered_catalog(
            version=version,
            discovered_catalog=discovered,
            baseline_catalog=base,
        ),
        previous_enabled_keys=set(),
        command_text="sst-info",
    )


def test_project_uid_participates_in_custom_target_identity_and_enablement(sst_env):
    env = sst_env
    custom_key = env.component_catalog.component_key(custom_cpu_component())

    discovery_a = _custom_discovery(env, project_uid="project-a")
    target_a, _, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery_a,
        enabled_keys={custom_key},
        project_uid="project-a",
    )

    discovery_b = _custom_discovery(env, project_uid="project-b")
    target_b, _, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery_b,
        enabled_keys=set(),
        project_uid="project-b",
    )

    assert target_a != target_b

    plugin = env.sst_plugin.SSTPlugin()

    names_a = {item.type_name for item in plugin.load_palette_items(target_id=str(target_a))}
    names_b = {item.type_name for item in plugin.load_palette_items(target_id=str(target_b))}

    assert "CustomCPU" in names_a
    assert "CustomCPU" not in names_b
    assert {"Cache", "MemController", "simpleMemBackend"}.issubset(names_b)

    with env.database.get_connection() as conn:
        rows = conn.execute(
            """
            SELECT project_key, component_key, enabled
            FROM sst_project_component_enablement
            ORDER BY project_key, component_key
            """
        ).fetchall()

    enabled_by_project = {
        (row["project_key"], row["component_key"]): int(row["enabled"])
        for row in rows
    }

    assert enabled_by_project[("project-a", custom_key)] == 1
    assert enabled_by_project[("project-b", custom_key)] == 0


def test_delete_custom_target_requires_force_when_project_enablement_exists(sst_env):
    env = sst_env
    custom_key = env.component_catalog.component_key(custom_cpu_component())

    discovery = _custom_discovery(env, project_uid="project-a")
    target_id, _, snapshot = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={custom_key},
        project_uid="project-a",
    )

    ok, message = env.component_catalog.delete_custom_catalog_target(target_id, force=False)

    assert not ok
    assert "project-scoped enablement" in message
    assert snapshot.exists()

    ok, message = env.component_catalog.delete_custom_catalog_target(target_id, force=True)

    assert ok, message
    assert not snapshot.exists()


def test_baseline_targets_are_protected_from_custom_catalog_deletion(sst_env):
    env = sst_env
    baseline_target_id, _ = _seed_baseline(env)

    ok, message = env.component_catalog.delete_custom_catalog_target(baseline_target_id, force=True)

    assert not ok
    assert "Only toolchain-discovered custom SST catalog targets" in message

    plugin = env.sst_plugin.SSTPlugin()
    assert str(baseline_target_id) in {target.target_id for target in plugin.list_targets()}


def test_catalog_source_summary_detects_remote_toolchain_and_project_fingerprint_changes(sst_env):
    env = sst_env
    toolchain = ssh_toolchain(host="alpha.example.test", username="sstuser")
    custom_key = env.component_catalog.component_key(custom_cpu_component())

    discovery = _custom_discovery(
        env,
        project_uid="project-a",
        toolchain=toolchain,
    )
    target_id, _, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={custom_key},
        project_uid="project-a",
    )

    summary = env.component_catalog.catalog_source_summary_for_target(
        target_id,
        toolchain=toolchain,
        project_uid="project-a",
    )
    assert summary.is_custom
    assert not summary.fingerprint_stale
    assert summary.enabled_custom_count == 1

    same_toolchain_other_project = env.component_catalog.catalog_source_summary_for_target(
        target_id,
        toolchain=toolchain,
        project_uid="project-b",
    )
    assert same_toolchain_other_project.fingerprint_stale

    changed_remote = ssh_toolchain(host="beta.example.test", username="sstuser")
    stale_summary = env.component_catalog.catalog_source_summary_for_target(
        target_id,
        toolchain=changed_remote,
        project_uid="project-a",
    )
    assert stale_summary.fingerprint_stale
