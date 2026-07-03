# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from fuse.core.model.models import ComponentDefinition, ModelSubcompAttachment
from fuse.plugins.community.sst.export_json import build_sst_json_dict, validate_sst_json_export
from fuse.plugins.community.sst.plugin import (
    EMBER_MOTIF_ATTACHMENT_KIND,
    EMBER_MOTIF_INTERFACE,
    SSTPlugin,
)
from fuse.plugins.community.sst.tests.scene_test_helpers import FakeNode, FakeScene


def _component(element: str, name: str, *, is_subcomp: int = 0, iface: str = "", version: str = "16.0.0"):
    return ComponentDefinition(
        plugin_id="sst",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
        iface=iface,
        framework_version=version,
    )


def _node(
    node_id: int,
    name: str,
    element: str,
    component: str,
    params=None,
    *,
    is_subcomp: int = 0,
    iface: str = "",
):
    return FakeNode(
        node_id=node_id,
        instance_name=name,
        component=_component(element, component, is_subcomp=is_subcomp, iface=iface),
        parameters=dict(params or {}),
    )


def _motif_attachment(attachment_id: int, parent: FakeNode, child: FakeNode) -> ModelSubcompAttachment:
    return ModelSubcompAttachment(
        attachment_id=attachment_id,
        name=f"subcomp_{parent.instance_name}_motif_{child.instance_name}",
        parent_node_id=parent.node_id,
        parent_component_name=parent.instance_name,
        slot_name="motif",
        child_node_id=child.node_id,
        child_component_name=child.instance_name,
        required_interface=EMBER_MOTIF_INTERFACE,
        provided_interface=EMBER_MOTIF_INTERFACE,
        plugin_id="sst",
        plugin_metadata={
            "visual_only": True,
            "allow_multiple": True,
            "visual_attachment_kind": EMBER_MOTIF_ATTACHMENT_KIND,
        },
    )


def test_visual_ember_motif_attachments_export_as_engine_params_not_subcomponents():
    engine = _node(1, "rank0", "ember", "EmberEngine", {"jobId": "0"})
    allreduce = _node(
        2,
        "rank0_allreduce",
        "ember",
        "AllreduceMotif",
        {"arg.count": "8", "arg.iterations": "10", "_jobId": "ignored"},
        is_subcomp=1,
        iface=EMBER_MOTIF_INTERFACE,
    )
    fini = _node(
        3,
        "rank0_fini",
        "ember",
        "FiniMotif",
        is_subcomp=1,
        iface=EMBER_MOTIF_INTERFACE,
    )
    scene = FakeScene(
        [engine, allreduce, fini],
        attachments=[
            _motif_attachment(1, engine, allreduce),
            _motif_attachment(2, engine, fini),
        ],
    )

    data = build_sst_json_dict(scene)

    assert [component["name"] for component in data["components"]] == ["rank0"]
    rank = data["components"][0]
    assert "subcomponents" not in rank
    assert rank["params"]["motif_count"] == "2"
    assert rank["params"]["motif0"] == "ember.AllreduceMotif"
    assert rank["params"]["motif0.arg.count"] == "8"
    assert rank["params"]["motif0.arg.iterations"] == "10"
    assert "motif0._jobId" not in rank["params"]
    assert rank["params"]["motif1"] == "ember.FiniMotif"


def test_visual_ember_motif_children_do_not_trigger_unattached_subcomponent_validation():
    engine = _node(1, "rank0", "ember", "EmberEngine", {"jobId": "0"})
    allreduce = _node(
        2,
        "rank0_allreduce",
        "ember",
        "AllreduceMotif",
        {"arg.count": "8"},
        is_subcomp=1,
        iface=EMBER_MOTIF_INTERFACE,
    )
    scene = FakeScene(
        [engine, allreduce],
        attachments=[_motif_attachment(1, engine, allreduce)],
    )

    report = validate_sst_json_export(scene)

    messages = "\n".join(issue.message for issue in report.errors)
    assert "rank0_allreduce" not in messages
    assert "SST SubComponent instances must be attached to a parent slot before export" not in messages


def test_sst_plugin_hook_syncs_ember_engine_motif_params_after_attachment_changes():
    engine = _node(1, "rank0", "ember", "EmberEngine", {"jobId": "0", "motif0": "old"})
    allreduce = _node(
        2,
        "rank0_allreduce",
        "ember",
        "AllreduceMotif",
        {"arg.count": "8"},
        is_subcomp=1,
        iface=EMBER_MOTIF_INTERFACE,
    )
    fini = _node(
        3,
        "rank0_fini",
        "ember",
        "FiniMotif",
        is_subcomp=1,
        iface=EMBER_MOTIF_INTERFACE,
    )
    first = _motif_attachment(1, engine, allreduce)
    second = _motif_attachment(2, engine, fini)
    scene = FakeScene([engine, allreduce, fini], attachments=[first, second])
    plugin = SSTPlugin()

    plugin.on_subcomponent_attachment_created(scene, second)

    assert engine.parameters["jobId"] == "0"
    assert engine.parameters["motif_count"] == "2"
    assert engine.parameters["motif0"] == "ember.AllreduceMotif"
    assert engine.parameters["motif0.arg.count"] == "8"
    assert engine.parameters["motif1"] == "ember.FiniMotif"

    scene.subcomp_attachments.remove(first)
    plugin.on_subcomponent_attachment_deleted(scene, first)

    assert engine.parameters["motif_count"] == "1"
    assert engine.parameters["motif0"] == "ember.FiniMotif"
    assert "motif1" not in engine.parameters
    assert "motif0.arg.count" not in engine.parameters
