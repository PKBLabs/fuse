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
def populate_sample_database():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(SAMPLE_SSTINFO)
    sync_parsed_sstinfo_to_database(elements, components)


def test_get_element_by_name_returns_element():
    from fuse.plugins.community.sst.db_utils import get_element_by_name

    populate_sample_database()

    element = get_element_by_name("testElement")

    assert element is not None
    assert element["name"] == "testElement"


def test_get_component_id_can_filter_by_element_and_kind():
    from fuse.plugins.community.sst.db_utils import get_component_id

    populate_sample_database()

    cpu_id = get_component_id(
        component_name="TestCPU",
        element_name="testElement",
        is_subcomp=False,
    )

    mmu_id = get_component_id(
        component_name="TestMMU",
        element_name="testElement",
        is_subcomp=True,
    )

    assert isinstance(cpu_id, int)
    assert isinstance(mmu_id, int)
    assert cpu_id != mmu_id


def test_get_components_and_subcomponents_are_separated():
    from fuse.plugins.community.sst.db_utils import (
        get_components_for_element,
        get_subcomponents_for_element,
    )

    populate_sample_database()

    components = get_components_for_element("testElement")
    subcomponents = get_subcomponents_for_element("testElement")

    component_names = {component["name"] for component in components}
    subcomponent_names = {component["name"] for component in subcomponents}

    assert component_names == {"TestCPU", "TestCache"}
    assert subcomponent_names == {"TestMMU"}


def test_get_component_details_returns_nested_statistics_parameters():
    from fuse.plugins.community.sst.db_utils import (
        get_all_components_for_element,
        get_component_details,
    )

    populate_sample_database()

    components = get_all_components_for_element("testElement")
    cpu = next(component for component in components if component["name"] == "TestCPU")

    details = get_component_details(cpu["id"])

    assert details is not None
    assert "component" in details
    assert "parameters" in details
    assert "ports" in details
    assert "subcomp_slots" in details
    assert "statistics" in details

    assert details["component"]["name"] == "TestCPU"
    assert {param["name"] for param in details["parameters"]} == {"clock", "threads"}

    cycles = next(stat for stat in details["statistics"] if stat["name"] == "cycles")
    assert cycles["parameters"] == []