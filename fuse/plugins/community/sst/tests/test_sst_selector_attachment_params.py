# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from fuse.core.model.models import ModelSubcompAttachment
from fuse.plugins.community.sst.export_json import build_sst_json_dict
from fuse.plugins.community.sst.plugin import SSTPlugin
from fuse.plugins.community.sst.tests.scene_test_helpers import FakeScene, make_node


def _attachment(
    attachment_id: int,
    parent,
    child,
    slot_name: str,
) -> ModelSubcompAttachment:
    return ModelSubcompAttachment(
        attachment_id=attachment_id,
        name=f"subcomp_{parent.instance_name}_{slot_name}_{child.instance_name}",
        parent_node_id=parent.node_id,
        parent_component_name=parent.instance_name,
        slot_name=slot_name,
        child_node_id=child.node_id,
        child_component_name=child.instance_name,
        plugin_id="sst",
    )


def test_visual_xbar_arb_attachment_updates_selector_but_exports_no_user_subcomponent():
    router = make_node(
        1,
        "rtr_0",
        "merlin",
        "hr_router",
        parameters={
            "id": "0",
            "num_ports": "4",
            "topology": "merlin.singlerouter",
            "xbar_arb": "merlin.old_arb",
            "link_bw": "256GB/s",
            "xbar_bw": "256GB/s",
            "flit_size": "72B",
            "input_buf_size": "4KiB",
            "output_buf_size": "4KiB",
        },
    )
    xbar = make_node(
        2,
        "xbar_lru_0",
        "merlin",
        "xbar_arb_lru",
        is_subcomp=1,
    )
    scene = FakeScene([router, xbar], attachments=[_attachment(1, router, xbar, "XbarArb")])

    SSTPlugin().on_subcomponent_attachment_created(scene, scene.subcomp_attachments[0])
    data = build_sst_json_dict(scene)

    assert router.parameters["xbar_arb"] == "merlin.xbar_arb_lru"
    assert [component["name"] for component in data["components"]] == ["rtr_0"]
    exported = data["components"][0]
    assert exported["params"]["xbar_arb"] == "merlin.xbar_arb_lru"
    assert "subcomponents" not in exported


def test_user_loaded_topology_attachment_updates_selector_and_still_exports_subcomponent():
    router = make_node(
        1,
        "rtr_0",
        "merlin",
        "hr_router",
        parameters={
            "id": "0",
            "num_ports": "4",
            "topology": "merlin.oldtopo",
            "link_bw": "256GB/s",
            "xbar_bw": "256GB/s",
            "flit_size": "72B",
            "input_buf_size": "4KiB",
            "output_buf_size": "4KiB",
        },
    )
    topology = make_node(
        2,
        "singlerouter_0",
        "merlin",
        "singlerouter",
        is_subcomp=1,
    )
    scene = FakeScene([router, topology], attachments=[_attachment(1, router, topology, "topology")])

    SSTPlugin().on_subcomponent_attachment_created(scene, scene.subcomp_attachments[0])
    data = build_sst_json_dict(scene)

    assert router.parameters["topology"] == "merlin.singlerouter"
    exported = data["components"][0]
    assert exported["params"]["topology"] == "merlin.singlerouter"
    assert exported["subcomponents"] == [
        {
            "slot_name": "topology",
            "type": "merlin.singlerouter",
        }
    ]


def test_subcomponent_attachment_selector_params_are_derived_inside_nested_trees():
    engine = make_node(1, "rank0", "ember", "EmberEngine", parameters={"jobId": "0"})
    hades = make_node(
        2,
        "hades_0",
        "firefly",
        "hades",
        is_subcomp=1,
        parameters={"netMapSize": "4", "nicModule": "firefly.OldNic"},
    )
    virt_nic = make_node(3, "virtNic_0", "firefly", "VirtNic", is_subcomp=1)
    scene = FakeScene(
        [engine, hades, virt_nic],
        attachments=[
            _attachment(1, engine, hades, "OS"),
            _attachment(2, hades, virt_nic, "virtNic"),
        ],
    )

    SSTPlugin().on_subcomponent_attachment_created(scene, scene.subcomp_attachments[1])
    data = build_sst_json_dict(scene)

    os_subcomponent = data["components"][0]["subcomponents"][0]
    assert hades.parameters["nicModule"] == "firefly.VirtNic"
    assert os_subcomponent["params"]["nicModule"] == "firefly.VirtNic"
