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

from fuse.plugins.community.sst.get_sstinfo import (
    parse_sstinfo_output,
    parse_variable_port_name,
)


def test_parse_variable_port_name_recognizes_named_printf_count_parameter():
    info = parse_variable_port_name("lowlink%(num_ports)d")

    assert info.is_variable is True
    assert info.base_name == "lowlink"
    assert info.count_parameter == "num_ports"
    assert info.default_count == 1


def test_parse_variable_port_name_recognizes_simple_printf_port_family():
    info = parse_variable_port_name("port%d")

    assert info.is_variable is True
    assert info.base_name == "port"
    assert info.count_parameter == "port_ports"


def test_parse_variable_port_name_leaves_regular_ports_static():
    info = parse_variable_port_name("cache_link")

    assert info.is_variable is False
    assert info.base_name == "cache_link"
    assert info.count_parameter == ""


def test_sstinfo_parser_captures_variable_ports_slots_and_continuations():
    stdout = """
ELEMENT LIBRARY 0 = merlin (Merlin network element)
Components (1 total)
Component 0: hr_router
Description: High radix router
Parameters (1 total)
num_ports: Number of router ports [4]
Ports (2 total)
port%(num_ports)d: Router network port
  accepts packets from endpoints and other routers
ctrl%d: Control plane port
SubComponent Slots (1 total)
topology: Topology slot [SST::Merlin::Topology]
Statistics (1 total)
packets: Packet count, (units="packets") Enable level = 1
"""

    _, components = parse_sstinfo_output(stdout)
    router = components[0]

    assert router.name == "hr_router"
    assert len(router.ports) == 2

    variable_port = router.ports[0]
    assert variable_port.name == "port%(num_ports)d"
    assert variable_port.is_variable == 1
    assert variable_port.base_name == "port"
    assert variable_port.count_parameter == "num_ports"
    assert "accepts packets" in variable_port.description

    simple_variable_port = router.ports[1]
    assert simple_variable_port.name == "ctrl%d"
    assert simple_variable_port.is_variable == 1
    assert simple_variable_port.base_name == "ctrl"
    assert simple_variable_port.count_parameter == "ctrl_ports"

    assert router.subcomp_slots[0].name == "topology"
    assert router.subcomp_slots[0].iface == "SST::Merlin::Topology"
