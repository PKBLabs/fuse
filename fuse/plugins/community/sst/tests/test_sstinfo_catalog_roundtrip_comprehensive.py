# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

from pathlib import Path

import pytest

from fuse.plugins.community.sst.tests.catalog_test_helpers import (
    COMPREHENSIVE_SSTINFO,
    MALFORMED_BUT_PARSEABLE_SSTINFO,
)


pytestmark = [pytest.mark.sst, pytest.mark.sst_external]


def _component_by_key(components):
    return {
        (component.element_name, component.name, int(component.is_subcomp)): component
        for component in components
    }


def _catalog_component_by_key(catalog):
    return {
        (
            component["element_name"],
            component["name"],
            int(component.get("is_subcomp", 0) or 0),
        ): component
        for component in catalog["components"]
    }


def test_comprehensive_sstinfo_fixture_parses_all_metadata_classes():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output

    elements, components = parse_sstinfo_output(COMPREHENSIVE_SSTINFO)
    by_key = _component_by_key(components)

    assert {element.name for element in elements} == {"memHierarchy", "customElement"}

    mem = by_key[("memHierarchy", "MemController", 0)]
    assert mem.description == "Synthetic memory controller component"
    assert mem.checkpointable == 0
    assert {parameter.name for parameter in mem.parameters} == {
        "clock",
        "addr_range_start",
        "num_ports",
    }

    clock = next(parameter for parameter in mem.parameters if parameter.name == "clock")
    assert clock.required == 1
    assert clock.default_val == "<required>"

    variable_port = next(port for port in mem.ports if port.name == "highlink%(num_ports)d")
    assert variable_port.is_variable == 1
    assert variable_port.base_name == "highlink"
    assert variable_port.count_parameter == "num_ports"
    assert variable_port.default_count == 1

    backend_slot = next(slot for slot in mem.subcomp_slots if slot.name == "backend")
    assert backend_slot.iface == "SST::MemHierarchy::MemBackend"

    requests = next(stat for stat in mem.statistics if stat.name == "requests")
    assert requests.units == "requests"

    backend = by_key[("memHierarchy", "simpleMemBackend", 1)]
    assert backend.iface == "SST::MemHierarchy::MemBackend"
    assert {parameter.name for parameter in backend.parameters} == {"access_time", "mem_size"}

    custom_mmu = by_key[("customElement", "CustomMMU", 1)]
    assert custom_mmu.iface == "SST::MMU"


def test_sstinfo_catalog_roundtrip_preserves_parameters_ports_slots_stats_and_subcomponents(tmp_path):
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        parsed_sstinfo_from_catalog_dict,
        parsed_sstinfo_to_catalog_dict,
    )

    elements, components = parse_sstinfo_output(COMPREHENSIVE_SSTINFO)

    catalog = parsed_sstinfo_to_catalog_dict(
        version="16.0.0",
        elements=elements,
        components=components,
        source="pytest comprehensive roundtrip",
    )

    path = tmp_path / "sst-16.0.0-comprehensive.json"
    path.write_text(__import__("json").dumps(catalog, indent=2), encoding="utf-8")

    reloaded_catalog = __import__("json").loads(path.read_text(encoding="utf-8"))
    roundtrip_elements, roundtrip_components = parsed_sstinfo_from_catalog_dict(reloaded_catalog)

    assert {element.name for element in roundtrip_elements} == {element.name for element in elements}

    original = _component_by_key(components)
    roundtrip = _component_by_key(roundtrip_components)

    assert set(roundtrip) == set(original)

    mem = roundtrip[("memHierarchy", "MemController", 0)]
    assert [(p.name, p.default_val, p.required) for p in mem.parameters] == [
        ("clock", "<required>", 1),
        ("addr_range_start", "0", 0),
        ("num_ports", "2", 0),
    ]
    assert [
        (
            port.name,
            port.is_variable,
            port.base_name,
            port.count_parameter,
            port.default_count,
        )
        for port in mem.ports
    ] == [
        ("direct_link", 0, "direct_link", "", 1),
        ("highlink%(num_ports)d", 1, "highlink", "num_ports", 1),
    ]
    assert [(slot.name, slot.iface) for slot in mem.subcomp_slots] == [
        ("backend", "SST::MemHierarchy::MemBackend")
    ]
    assert [(stat.name, stat.units) for stat in mem.statistics] == [
        ("requests", "requests")
    ]


def test_parseable_malformed_fixture_keeps_continuations_and_simple_printf_ports():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output

    _, components = parse_sstinfo_output(MALFORMED_BUT_PARSEABLE_SSTINFO)
    odd = components[0]

    assert odd.element_name == "oddElement"
    assert odd.name == "OddComponent"
    assert odd.parameters[0].name == "long_param"
    assert "continued description text" in odd.parameters[0].description

    port = odd.ports[0]
    assert port.name == "port%d"
    assert port.is_variable == 1
    assert port.base_name == "port"
    assert port.count_parameter == "port_ports"
