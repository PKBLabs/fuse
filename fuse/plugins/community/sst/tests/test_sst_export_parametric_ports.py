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
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
# PARTICULAR PURPOSE. See the GNU General Public License for more details.
from types import SimpleNamespace

from fuse.plugins.community.sst.export_json import build_sst_link


def _node(node_id: int, instance_name: str, element: str, name: str, parameters=None):
    return SimpleNamespace(
        node_id=node_id,
        instance_name=instance_name,
        parameters=parameters or {},
        variable_port_counts={},
        component=SimpleNamespace(
            element=element,
            name=name,
            framework_version="16.0.0",
        ),
    )


def test_export_resolves_saved_loopback_parametric_port_template():
    loopback = _node(
        1,
        "loopBack0",
        "firefly",
        "loopBack",
        parameters={
            "numCores": "1",
            "nicsPerNode": "1",
        },
    )
    endpoint = _node(2, "ctrl0", "firefly", "ctrlMsg")

    link = SimpleNamespace(
        link_id=1,
        name="loop",
        latency="1ns",
        source_latency="",
        target_latency="",
        no_cut=False,
        nonlocal_link=False,
        source_node_id=1,
        source_component_name="loopBack0",
        source_port="nic%(nicsPerNode)dcore%(num_vNics/nicsPerNode)d",
        target_node_id=2,
        target_component_name="ctrl0",
        target_port="loop",
    )

    exported = build_sst_link(link, nodes_by_id={1: loopback, 2: endpoint})

    assert exported["left"]["component"] == "loopBack0"
    assert exported["left"]["port"] == "nic0core0"
