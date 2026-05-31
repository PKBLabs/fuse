# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.

from fuse.plugins.community.sst.get_sstinfo import ParsedComponent, ParsedElement, ParsedPort, ParsedSubcompSlot
from fuse.plugins.community.sst.get_sstinfo import resolve_framework_version_id


def _populate_two_targets():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.core.persistence.database import get_connection
    from fuse.plugins.community.sst.get_sstinfo import sync_parsed_sstinfo_to_database

    ensure_database_ready(run_plugin_bootstrap=False)

    with get_connection() as conn:
        old_target = resolve_framework_version_id(
            conn,
            version="14.0.0",
            label="SST 14.0.0",
            source_kind="test",
            source_path="old",
            is_default=False,
        )
        new_target = resolve_framework_version_id(
            conn,
            version="15.0.0",
            label="SST 15.0.0",
            source_kind="test",
            source_path="new",
            is_default=True,
        )

    elements = [ParsedElement("testElement")]
    sync_parsed_sstinfo_to_database(
        old_target,
        elements,
        [
            ParsedComponent(
                element_name="testElement",
                name="LegacyCPU",
                description="old target component",
                ports=[ParsedPort("legacy_link")],
            )
        ],
    )
    sync_parsed_sstinfo_to_database(
        new_target,
        elements,
        [
            ParsedComponent(
                element_name="testElement",
                name="TestCPU",
                description="new target component",
                ports=[ParsedPort("cache%(num_cache_ports)d", is_variable=1, base_name="cache", count_parameter="num_cache_ports")],
                subcomp_slots=[ParsedSubcompSlot("mmu", iface="SST::MMU")],
            ),
            ParsedComponent(
                element_name="testElement",
                name="TestMMU",
                description="new target subcomponent",
                is_subcomp=1,
                iface="SST::MMU",
            ),
        ],
    )

    return old_target, new_target


def test_sst_plugin_targets_are_ordered_with_default_first():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    old_target, new_target = _populate_two_targets()

    targets = SSTPlugin().list_targets()

    assert [target.target_id for target in targets[:2]] == [str(new_target), str(old_target)]
    assert targets[0].is_default is True
    assert targets[0].display_name == "SST 15.0.0"


def test_sst_plugin_load_palette_items_respects_target_filter():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    old_target, new_target = _populate_two_targets()
    plugin = SSTPlugin()

    old_items = plugin.load_palette_items(target_id=str(old_target))
    new_items = plugin.load_palette_items(target_id=str(new_target))

    assert {item.type_name for item in old_items} == {"LegacyCPU"}
    assert {item.type_name for item in new_items} == {"TestCPU", "TestMMU"}
    assert {item.target_id for item in new_items} == {str(new_target)}


def test_sst_plugin_item_details_expose_variable_ports_and_subcomponent_connectors():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    _, new_target = _populate_two_targets()
    plugin = SSTPlugin()
    cpu_item = next(
        item
        for item in plugin.load_palette_items(target_id=str(new_target))
        if item.type_name == "TestCPU"
    )
    mmu_item = next(
        item
        for item in plugin.load_palette_items(target_id=str(new_target))
        if item.type_name == "TestMMU"
    )

    cpu_details = plugin.load_item_details(cpu_item.item_id, target_id=str(new_target))
    mmu_details = plugin.load_item_details(mmu_item.item_id, target_id=str(new_target))

    assert len(cpu_details.connectors) == 1
    connector = cpu_details.connectors[0]
    assert connector.name == "cache%(num_cache_ports)d"
    assert connector.is_variable is True
    assert connector.base_name == "cache"
    assert connector.count_parameter == "num_cache_ports"

    assert len(cpu_details.subcomp_connectors) == 1
    assert cpu_details.subcomp_connectors[0].name == "mmu"
    assert cpu_details.subcomp_connectors[0].role == "slot"
    assert cpu_details.subcomp_connectors[0].required_interface == "SST::MMU"

    assert len(mmu_details.subcomp_connectors) == 1
    assert mmu_details.subcomp_connectors[0].name == "interface"
    assert mmu_details.subcomp_connectors[0].role == "interface"
    assert mmu_details.subcomp_connectors[0].provided_interface == "SST::MMU"


def test_sst_subcomponent_slot_compatibility_ok_warning_and_error():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    plugin = SSTPlugin()

    ok = plugin.check_subcomponent_slot_compatibility(
        {"required_interface": "SST::MMU"},
        {"provided_interface": "SST::MMU"},
    )
    warning = plugin.check_subcomponent_slot_compatibility(
        {"required_interface": ""},
        {"provided_interface": "SST::MMU"},
    )
    error = plugin.check_subcomponent_slot_compatibility(
        {"required_interface": "SST::MMU"},
        {"provided_interface": "SST::Other"},
    )

    assert ok.can_create is True
    assert ok.severity == "ok"
    assert warning.can_create is True
    assert warning.severity == "warning"
    assert warning.code == "sst.subcomponent_slot_unknown_interface"
    assert error.can_create is False
    assert error.severity == "error"
    assert error.code == "sst.subcomponent_slot_interface_mismatch"
