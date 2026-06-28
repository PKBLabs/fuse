# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import pytest

from fuse.plugins.community.sst.tests.catalog_test_helpers import (
    cache_component,
    custom_mmu_subcomponent,
    memcontroller_component,
)
from fuse.plugins.community.sst.tests.conftest import write_component_catalog, write_policy_catalog


pytestmark = pytest.mark.sst


def test_bundled_bootstrap_is_idempotent_and_target_scoped(sst_env):
    env = sst_env

    write_policy_catalog(env, "15.1.2")
    write_policy_catalog(env, "16.0.0")
    write_component_catalog(env, "15.1.2", [cache_component(default_line_size="32")])
    write_component_catalog(env, "16.0.0", [memcontroller_component()])

    plugin = env.sst_plugin.SSTPlugin()
    plugin.bootstrap_database()
    plugin.bootstrap_database()

    with env.database.get_connection() as conn:
        framework_rows = conn.execute(
            """
            SELECT version, source_kind, source_path, COUNT(*) AS count
            FROM sst_framework_versions
            GROUP BY version, source_kind, source_path
            """
        ).fetchall()
        component_rows = conn.execute(
            """
            SELECT fv.version, c.name, COUNT(*) AS count
            FROM sst_components c
            JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
            GROUP BY fv.version, c.name
            """
        ).fetchall()

    framework_counts = {
        (row["version"], row["source_kind"], row["source_path"]): int(row["count"])
        for row in framework_rows
    }
    component_counts = {
        (row["version"], row["name"]): int(row["count"])
        for row in component_rows
    }

    assert framework_counts[("15.1.2", "bundled-component-catalog", "")] == 1
    assert framework_counts[("16.0.0", "bundled-component-catalog", "")] == 1
    assert component_counts[("15.1.2", "Cache")] == 1
    assert component_counts[("16.0.0", "MemController")] == 1

    targets = {target.framework_version: target for target in plugin.list_targets()}
    assert set(targets) == {"15.1.2", "16.0.0"}


def test_plugin_details_include_subcomponent_interface_connector_and_metadata(sst_env):
    env = sst_env

    catalog_path = write_component_catalog(
        env,
        "16.0.0",
        [memcontroller_component(), custom_mmu_subcomponent()],
    )

    target_id = env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        catalog_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="details import",
        is_default=True,
        clear_existing=True,
    )

    plugin = env.sst_plugin.SSTPlugin()
    items = plugin.load_palette_items(target_id=str(target_id))
    item_by_name = {item.type_name: item for item in items}

    assert item_by_name["CustomMMU"].raw_kind == "SubComponent"

    mem_details = plugin.load_item_details(
        item_by_name["MemController"].item_id,
        target_id=str(target_id),
    )
    slot_names = {slot.name: slot for slot in mem_details.subcomp_connectors}
    assert slot_names["backend"].required_interface == "SST::MemHierarchy::MemBackend"

    mmu_details = plugin.load_item_details(
        item_by_name["CustomMMU"].item_id,
        target_id=str(target_id),
    )
    interface_slots = {
        slot.name: slot
        for slot in mmu_details.subcomp_connectors
    }

    assert "interface" in interface_slots
    assert interface_slots["interface"].provided_interface == "SST::MMU"
    assert {prop.name for prop in mmu_details.properties} == {"page_size"}
