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
def test_parse_sstinfo_output_extracts_elements(sample_sstinfo=None):
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    elements, components = parse_sstinfo_output(SAMPLE_SSTINFO)

    assert len(elements) == 1
    assert elements[0].name == "testElement"
    assert len(components) == 3


def test_parse_sstinfo_output_extracts_components():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    _, components = parse_sstinfo_output(SAMPLE_SSTINFO)

    names = {component.name for component in components}

    assert names == {"TestCPU", "TestCache", "TestMMU"}


def test_parse_sstinfo_output_marks_subcomponents():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    _, components = parse_sstinfo_output(SAMPLE_SSTINFO)

    mmu = next(component for component in components if component.name == "TestMMU")

    assert mmu.is_subcomp == 1
    assert mmu.iface == "SST::MMU"
    assert mmu.category == "SUBCOMPONENT"


def test_parse_sstinfo_output_extracts_required_parameters():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    _, components = parse_sstinfo_output(SAMPLE_SSTINFO)

    cpu = next(component for component in components if component.name == "TestCPU")
    required = [param for param in cpu.parameters if param.required]

    assert len(required) == 1
    assert required[0].name == "threads"
    assert required[0].default_val == "<required>"


def test_parse_sstinfo_output_extracts_ports_slots_and_statistics():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    _, components = parse_sstinfo_output(SAMPLE_SSTINFO)

    cpu = next(component for component in components if component.name == "TestCPU")

    assert [port.name for port in cpu.ports] == ["cache_link", "memory_link"]
    assert [slot.name for slot in cpu.subcomp_slots] == ["mmu"]
    assert len(cpu.statistics) == 1
    assert cpu.statistics[0].name == "cycles"
    assert cpu.statistics[0].units == "cycles"


def test_parser_handles_empty_input():
    from fuse.plugins.community.sst.get_sstinfo import parse_sstinfo_output

    elements, components = parse_sstinfo_output("")

    assert elements == []
    assert components == []