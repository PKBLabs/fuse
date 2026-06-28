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
    custom_mmu_subcomponent,
    discovered_changed_catalog,
    discovered_custom_catalog,
)


pytestmark = [pytest.mark.sst, pytest.mark.sst_external]


def test_external_classification_covers_custom_subcomponents_and_changed_interfaces(sst_env):
    env = sst_env

    entries = env.component_catalog.classify_discovered_catalog(
        version="16.0.0",
        discovered_catalog=discovered_changed_catalog("16.0.0"),
        baseline_catalog=baseline_catalog("16.0.0"),
    )
    status_by_name = {entry.display_name: entry.status for entry in entries}

    assert status_by_name["customElement.CustomCPU"] == "custom"
    assert status_by_name["memHierarchy.Cache"] == "changed"
    assert "customElement.CustomMMU (SubComponent)" not in status_by_name

    cache_diff = env.component_catalog.describe_component_metadata_diff(
        key=env.component_catalog.component_key(cache_component()),
        baseline_catalog=baseline_catalog("16.0.0"),
        discovered_catalog=discovered_changed_catalog("16.0.0"),
    )
    text = "\n".join(cache_diff.lines)

    assert cache_diff.status == "changed"
    assert "Changed parameters" in text
    assert "Changed ports" in text
    assert "cache_line_size" in text
    assert "highlink" in text


def test_external_custom_subcomponent_can_be_enabled_and_loaded_from_custom_target(sst_env):
    env = sst_env
    base = baseline_catalog("16.0.0")
    discovered = discovered_custom_catalog("16.0.0")

    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — external subcomponent",
        source_fingerprint="external-subcomponent",
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

    enabled_keys = {
        env.component_catalog.component_key(custom_cpu_component()),
        env.component_catalog.component_key(custom_mmu_subcomponent()),
    }
    target_id, _, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys=enabled_keys,
        project_uid="external-subcomponent-project",
    )

    plugin = env.sst_plugin.SSTPlugin()
    items = plugin.load_palette_items(target_id=str(target_id))
    by_name = {item.type_name: item for item in items}

    assert {"Cache", "MemController", "simpleMemBackend", "CustomCPU", "CustomMMU"}.issubset(by_name)
    assert by_name["CustomMMU"].raw_kind == "SubComponent"

    details = plugin.load_item_details(by_name["CustomMMU"].item_id, target_id=str(target_id))
    assert any(slot.name == "interface" and slot.provided_interface == "SST::MMU" for slot in details.subcomp_connectors)
    assert {prop.name for prop in details.properties} == {"page_size"}


def test_missing_baseline_components_are_not_enabled_by_default(sst_env):
    env = sst_env

    discovered = {
        **baseline_catalog("16.0.0"),
        "components": [cache_component()],
    }

    entries = env.component_catalog.classify_discovered_catalog(
        version="16.0.0",
        discovered_catalog=discovered,
        baseline_catalog=baseline_catalog("16.0.0"),
    )

    missing = [entry for entry in entries if entry.status == "missing"]
    assert {entry.display_name for entry in missing} == {
        "memHierarchy.MemController",
        "memHierarchy.simpleMemBackend",
    }
    assert all(not entry.enabled_by_default for entry in missing)
