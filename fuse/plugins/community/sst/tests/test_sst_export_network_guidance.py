# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from fuse.core.model.models import ComponentDefinition, ModelSubcompAttachment
from fuse.plugins.community.sst.export_json import build_sst_json_dict, validate_sst_json_export
from fuse.plugins.community.sst.tests.scene_test_helpers import FakeNode, FakeScene


def _component(element: str, name: str, *, is_subcomp: int = 0) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
    )


def _node(node_id: int, name: str, element: str, component: str, params=None, *, is_subcomp: int = 0):
    return FakeNode(
        node_id=node_id,
        instance_name=name,
        component=_component(element, component, is_subcomp=is_subcomp),
        parameters=dict(params or {}),
    )


def _attach(attachment_id: int, parent: FakeNode, slot: str, child: FakeNode) -> ModelSubcompAttachment:
    return ModelSubcompAttachment(
        attachment_id=attachment_id,
        name=f"subcomp_{parent.instance_name}_{slot}_{child.instance_name}",
        parent_node_id=parent.node_id,
        parent_component_name=parent.instance_name,
        slot_name=slot,
        child_node_id=child.node_id,
        child_component_name=child.instance_name,
        plugin_id="sst",
    )


def test_hr_router_topology_param_is_derived_from_attached_topology_subcomponent():
    router = _node(
        1,
        "rtr",
        "merlin",
        "hr_router",
        {
            "id": "0",
            "num_ports": "3",
            "flit_size": "72B",
            "xbar_bw": "256GB/s",
        },
    )
    topology = _node(
        2,
        "rtr_topology",
        "merlin",
        "singlerouter",
        {"network_name": "network0"},
        is_subcomp=1,
    )
    scene = FakeScene([router, topology], attachments=[_attach(1, router, "topology", topology)])

    data = build_sst_json_dict(scene)

    assert data["components"] == [
        {
            "name": "rtr",
            "type": "merlin.hr_router",
            "params": {
                "flit_size": "72B",
                "id": "0",
                "num_ports": "3",
                "topology": "merlin.singlerouter",
                "xbar_bw": "256GB/s",
            },
            "subcomponents": [
                {
                    "slot_name": "topology",
                    "type": "merlin.singlerouter",
                    "params": {"network_name": "network0"},
                }
            ],
        }
    ]


def _networked_memhierarchy_scene(*, cpu_flush_freq="0", mem_destinations=None, cpu0_destinations="1"):
    cpu = _node(
        1,
        "cpu0",
        "memHierarchy",
        "standardCPU",
        {
            "clock": "2GHz",
            "memSize": "1GiB",
            "read_freq": "60",
            "write_freq": "40",
            "flush_freq": cpu_flush_freq,
            "flushcache_freq": "0",
            "flushinv_freq": "0",
            "llsc_freq": "0",
        },
    )
    iface = _node(2, "cpu0_iface", "memHierarchy", "standardInterface", is_subcomp=1)
    cpu_nic_params = {"group": "0"}
    if cpu0_destinations is not None:
        cpu_nic_params["destinations"] = cpu0_destinations
    cpu_nic = _node(3, "cpu0_nic", "memHierarchy", "MemNIC", cpu_nic_params, is_subcomp=1)
    mc = _node(
        4,
        "mc",
        "memHierarchy",
        "MemController",
        {"clock": "1GHz", "addr_range_start": "0", "addr_range_end": "1073741823"},
    )
    mem_nic_params = {"group": "1", "sources": "0"}
    if mem_destinations is not None:
        mem_nic_params["destinations"] = mem_destinations
    mem_nic = _node(5, "mc_nic", "memHierarchy", "MemNIC", mem_nic_params, is_subcomp=1)

    attachments = [
        _attach(1, cpu, "memory", iface),
        _attach(2, iface, "lowlink", cpu_nic),
        _attach(3, mc, "highlink", mem_nic),
    ]
    return FakeScene([cpu, iface, cpu_nic, mc, mem_nic], attachments=attachments)


def test_memory_controller_memnic_destination_to_requester_group_is_export_error():
    report = validate_sst_json_export(
        _networked_memhierarchy_scene(mem_destinations="0")
    )

    messages = "\n".join(issue.message for issue in report.errors)
    assert "Memory-controller-side MemNIC should not list requester groups as destinations" in messages
    assert not report.can_export


def test_requester_memnic_without_destinations_warns_but_does_not_block_export():
    report = validate_sst_json_export(
        _networked_memhierarchy_scene(cpu0_destinations=None)
    )

    messages = "\n".join(issue.message for issue in report.warnings)
    assert "Requester-side MemNIC has no destinations" in messages
    assert report.can_export


def test_direct_cpu_to_memnic_flush_traffic_warns():
    report = validate_sst_json_export(
        _networked_memhierarchy_scene(cpu_flush_freq="1")
    )

    messages = "\n".join(issue.message for issue in report.warnings)
    assert "connected directly to a MemNIC without a cache" in messages
    assert "flush_freq" in messages
    assert report.can_export
