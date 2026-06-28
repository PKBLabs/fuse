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
def test_sync_parsed_sstinfo_populates_database(sample_sstinfo):
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import (
        get_all_components_for_element,
        get_all_elements,
        get_component_details,
    )
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(sample_sstinfo)
    sync_parsed_sstinfo_to_database(elements, components)

    db_elements = get_all_elements()
    assert len(db_elements) == 1
    assert db_elements[0]["name"] == "testElement"

    db_components = get_all_components_for_element("testElement")
    names = {component["name"] for component in db_components}

    assert names == {"TestCPU", "TestCache", "TestMMU"}

    cpu = next(component for component in db_components if component["name"] == "TestCPU")
    details = get_component_details(cpu["id"])

    assert details is not None
    assert details["component"]["name"] == "TestCPU"
    assert {param["name"] for param in details["parameters"]} == {"clock", "threads"}
    assert {port["name"] for port in details["ports"]} == {"cache_link", "memory_link"}
    assert {slot["name"] for slot in details["subcomp_slots"]} == {"mmu"}
    assert {stat["name"] for stat in details["statistics"]} == {"cycles"}


def test_sync_parsed_sstinfo_is_idempotent(sample_sstinfo):
    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(sample_sstinfo)

    sync_parsed_sstinfo_to_database(elements, components)
    sync_parsed_sstinfo_to_database(elements, components)

    with get_connection() as conn:
        element_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sst_elements"
        ).fetchone()["count"]
        component_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sst_components"
        ).fetchone()["count"]

    assert element_count == 1
    assert component_count == 3


def test_sync_updates_existing_component_metadata(sample_sstinfo, updated_sample_sstinfo):
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import (
        get_all_components_for_element,
        get_component_details,
    )
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(sample_sstinfo)
    sync_parsed_sstinfo_to_database(elements, components)

    updated_elements, updated_components = parse_sstinfo_output(updated_sample_sstinfo)
    sync_parsed_sstinfo_to_database(updated_elements, updated_components)

    db_components = get_all_components_for_element("testElement")
    cpu = next(component for component in db_components if component["name"] == "TestCPU")

    assert cpu["description"] == "Updated test processor component"
    assert cpu["checkpointable"] == 1

    details = get_component_details(cpu["id"])
    assert {param["name"] for param in details["parameters"]} == {"clock"}
    assert {port["name"] for port in details["ports"]} == {"cache_link"}


def test_sync_does_not_overwrite_manual_icon_path(sample_sstinfo):
    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import get_component_id
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(sample_sstinfo)
    sync_parsed_sstinfo_to_database(elements, components)

    component_id = get_component_id("TestCPU", "testElement", False)

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE sst_components
            SET icon_path = ?
            WHERE id = ?
            """,
            ("custom/manual/icon.png", component_id),
        )
        conn.commit()

    sync_parsed_sstinfo_to_database(elements, components)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT icon_path
            FROM sst_components
            WHERE id = ?
            """,
            (component_id,),
        ).fetchone()

    assert row["icon_path"] == "custom/manual/icon.png"