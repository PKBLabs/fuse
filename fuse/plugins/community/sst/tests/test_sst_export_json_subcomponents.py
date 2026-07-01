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

from dataclasses import dataclass, field

import pytest

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.plugins.community.sst.export_json import (
    SSTJsonExportError,
    build_sst_json_dict,
    build_sst_link,
)


@dataclass
class FakeNode:
    node_id: int
    instance_name: str
    component: ComponentDefinition
    parameters: dict = field(default_factory=dict)


class FakeScene:
    def __init__(self, nodes, links=None, attachments=None):
        self._nodes = list(nodes)
        self.links = list(links or [])
        self.subcomp_attachments = list(attachments or [])

    def component_items(self):
        return list(self._nodes)


def _component(element, name, is_subcomp=0):
    return ComponentDefinition(
        plugin_id="sst",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
    )


def test_build_sst_json_nests_subcomponents_and_omits_child_from_roots():
    cpu = FakeNode(
        1,
        "cpu0",
        _component("prospero", "prosperoCPU"),
        {"clock": "2GHz", "empty": ""},
    )
    mmu = FakeNode(
        2,
        "mmu0",
        _component("mmu", "simpleMMU", is_subcomp=1),
        {"page_size": "4096", "port": "legacy-lowlink", "port_name": "legacy-linkcontrol"},
    )
    attachment = ModelSubcompAttachment(
        attachment_id=1,
        name="subcomp_cpu0_mmu_mmu0",
        parent_node_id=1,
        parent_component_name="cpu0",
        slot_name="mmu",
        child_node_id=2,
        child_component_name="mmu0",
        required_interface="SST::MMU",
        provided_interface="SST::MMU",
        plugin_id="sst",
    )

    data = build_sst_json_dict(FakeScene([cpu, mmu], attachments=[attachment]))

    assert len(data["components"]) == 1
    assert data["components"][0]["name"] == "cpu0"
    assert data["components"][0]["params"] == {"clock": "2GHz"}
    assert data["components"][0]["subcomponents"] == [
        {
            "slot_name": "mmu",
            "type": "mmu.simpleMMU",
            "params": {"page_size": "4096"},
        }
    ]


def test_build_sst_json_raises_when_subcomponent_attachment_child_is_missing():
    cpu = FakeNode(1, "cpu0", _component("prospero", "prosperoCPU"))
    attachment = ModelSubcompAttachment(
        attachment_id=1,
        name="missing_child",
        parent_node_id=1,
        parent_component_name="cpu0",
        slot_name="mmu",
        child_node_id=99,
        child_component_name="missing",
    )

    with pytest.raises(SSTJsonExportError, match="missing child node 99"):
        build_sst_json_dict(FakeScene([cpu], attachments=[attachment]))



def test_build_sst_json_rewrites_links_to_attached_subcomponent_slot_ports():
    from fuse.core.model.models import ModelLink

    cpu = FakeNode(
        1,
        "cpu0",
        _component("memHierarchy", "standardCPU"),
        {"clock": "2GHz"},
    )
    iface = FakeNode(
        2,
        "cpu0_iface",
        _component("memHierarchy", "standardInterface", is_subcomp=1),
        {},
    )
    cache = FakeNode(
        3,
        "cpu0_l1",
        _component("memHierarchy", "Cache"),
        {"cache_size": "32KiB"},
    )
    attachment = ModelSubcompAttachment(
        attachment_id=1,
        name="subcomp_cpu0_memory_iface",
        parent_node_id=1,
        parent_component_name="cpu0",
        slot_name="memory",
        child_node_id=2,
        child_component_name="cpu0_iface",
        required_interface="SST::Interfaces::StandardMem",
        provided_interface="SST::Interfaces::StandardMem",
        plugin_id="sst",
    )
    link = ModelLink(
        1,
        "link_cpu_iface_cache",
        2,
        "cpu0_iface",
        "lowlink",
        3,
        "cpu0_l1",
        "highlink",
        source_latency="1ns",
        target_latency="1ns",
    )

    data = build_sst_json_dict(FakeScene([cpu, iface, cache], links=[link], attachments=[attachment]))

    assert data["components"][0]["subcomponents"] == [
        {
            "slot_name": "memory",
            "type": "memHierarchy.standardInterface",
        }
    ]
    assert data["links"] == [
        {
            "name": "link_cpu_iface_cache",
            "noCut": False,
            "nonlocal": False,
            "left": {"component": "cpu0:memory", "port": "lowlink", "latency": "1ns"},
            "right": {"component": "cpu0_l1", "port": "highlink", "latency": "1ns"},
        }
    ]


def test_build_sst_json_uses_nested_subcomponent_references_for_links():
    cpu = FakeNode(
        1,
        "cpu0",
        _component("example", "CPU"),
        {},
    )
    iface = FakeNode(
        2,
        "iface0",
        _component("example", "Interface", is_subcomp=1),
        {},
    )
    adapter = FakeNode(
        3,
        "adapter0",
        _component("example", "Adapter", is_subcomp=1),
        {},
    )
    cache = FakeNode(
        4,
        "cache0",
        _component("example", "Cache"),
        {},
    )
    attachments = [
        ModelSubcompAttachment(
            attachment_id=1,
            name="cpu_memory_iface",
            parent_node_id=1,
            parent_component_name="cpu0",
            slot_name="memory",
            child_node_id=2,
            child_component_name="iface0",
            plugin_id="sst",
        ),
        ModelSubcompAttachment(
            attachment_id=2,
            name="iface_adapter",
            parent_node_id=2,
            parent_component_name="iface0",
            slot_name="adapter",
            child_node_id=3,
            child_component_name="adapter0",
            plugin_id="sst",
        ),
    ]
    link = ModelLink(
        1,
        "link_adapter_cache",
        3,
        "adapter0",
        "lowlink",
        4,
        "cache0",
        "highlink",
        source_latency="1ns",
        target_latency="1ns",
    )

    data = build_sst_json_dict(
        FakeScene([cpu, iface, adapter, cache], links=[link], attachments=attachments)
    )

    assert data["links"][0]["left"] == {
        "component": "cpu0:memory:adapter",
        "port": "lowlink",
        "latency": "1ns",
    }
    assert data["links"][0]["right"] == {
        "component": "cache0",
        "port": "highlink",
        "latency": "1ns",
    }

def test_build_sst_link_emits_independent_endpoint_latencies_and_flags():
    link = ModelLink(
        link_id=7,
        name="link_cpu_cache",
        source_node_id=1,
        source_component_name="cpu0",
        source_port="cache",
        target_node_id=2,
        target_component_name="cache0",
        target_port="cpu",
        source_latency="250ps",
        target_latency="1ns",
    )
    link.no_cut = True
    link.nonlocal_link = True

    assert build_sst_link(link) == {
        "name": "link_cpu_cache",
        "noCut": True,
        "nonlocal": True,
        "left": {"component": "cpu0", "port": "cache", "latency": "250ps"},
        "right": {"component": "cache0", "port": "cpu", "latency": "1ns"},
    }


def test_build_sst_link_rejects_incomplete_endpoint_metadata():
    link = ModelLink(
        link_id=1,
        name="broken",
        source_node_id=1,
        source_component_name="",
        source_port="out",
        target_node_id=2,
        target_component_name="cache0",
        target_port="",
    )

    with pytest.raises(SSTJsonExportError, match="source component, target port"):
        build_sst_link(link)
