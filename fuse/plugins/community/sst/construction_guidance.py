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
"""Actionable construction guidance for SST models.

SST models often distinguish between:

* a SubComponent slot, which owns another SST object, and
* a real link port, which participates in an SST Link.connect() call.

That distinction is easy to miss when a slot name sounds like a cable. The
classic Firefly example is ``firefly.nic.rtrLink``:

    nic_7_compute.rtrLink -> linkcontrol_7 : merlin.linkcontrol
    linkcontrol_7.rtr_port <-> rtr_1x1.port5

The generic validator can detect that the slot is empty, but the user also
needs to know what child component to create and which port to connect
afterward. This module keeps those SST-specific explanations out of the generic
app shell.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class SlotConstructionGuide:
    """Construction help for one SST parent component slot."""

    parent_type: str
    slot_name: str
    child_type: str
    concise_fix: str
    explanation: str
    example: str = ""
    quick_fix_child_port: str = ""
    quick_fix_target_hint: str = ""


@dataclass(frozen=True)
class UnattachedSubcomponentGuide:
    """Construction help for a standalone SST SubComponent."""

    child_type: str
    concise_fix: str
    explanation: str
    example: str = ""


@dataclass(frozen=True)
class ChildPortConstructionGuide:
    """Construction help for a real port on an attached SST SubComponent."""

    child_type: str
    port_name: str
    concise_fix: str
    explanation: str
    example: str = ""


def _key(component_type: str, slot_name: str) -> tuple[str, str]:
    return (component_type.strip(), slot_name.strip())


SLOT_GUIDES: dict[tuple[str, str], SlotConstructionGuide] = {
    _key("firefly.nic", "rtrLink"): SlotConstructionGuide(
        parent_type="firefly.nic",
        slot_name="rtrLink",
        child_type="merlin.linkcontrol",
        concise_fix=(
            "Create/attach merlin.linkcontrol to this NIC's rtrLink slot, "
            "then connect merlin.linkcontrol.rtr_port to the router port."
        ),
        explanation=(
            "firefly.nic.rtrLink is a SubComponent slot, not a direct router "
            "cable. The NIC owns a merlin.linkcontrol child in this slot. The "
            "real network link is then made from the child's rtr_port."
        ),
        example=(
            "nic_7_compute.rtrLink -> linkcontrol_7 : merlin.linkcontrol; "
            "linkcontrol_7.rtr_port <-> rtr_1x1.port5"
        ),
        quick_fix_child_port="rtr_port",
        quick_fix_target_hint="router port",
    ),
    _key("firefly.nic", "simpleMemoryModel"): SlotConstructionGuide(
        parent_type="firefly.nic",
        slot_name="simpleMemoryModel",
        child_type="firefly.SimpleMemory",
        concise_fix=(
            "Attach firefly.SimpleMemory to simpleMemoryModel as a logical FUSE "
            "child; export should fold its params onto the NIC as "
            "simpleMemoryModel.*."
        ),
        explanation=(
            "firefly.nic creates firefly.SimpleMemory internally when "
            "useSimpleMemoryModel=1. FUSE shows the child visually to make the "
            "model understandable, but SST JSON should not contain a nested "
            "firefly.SimpleMemory subcomponent for this slot."
        ),
        example=(
            "nic_7_compute.simpleMemoryModel -> sm_7_compute; export params as "
            "simpleMemoryModel.id, simpleMemoryModel.memReadLat_ns, ..."
        ),
    ),
    _key("firefly.hades", "virtNic"): SlotConstructionGuide(
        parent_type="firefly.hades",
        slot_name="virtNic",
        child_type="firefly.VirtNic",
        concise_fix=(
            "Attach firefly.VirtNic to hades.virtNic, then connect VirtNic.nic "
            "to the matching firefly.nic.coreN port."
        ),
        explanation=(
            "firefly.hades.virtNic is the OS-owned virtual NIC SubComponent "
            "slot. It is separate from the real link between VirtNic.nic and "
            "the NIC component's core port."
        ),
        example=(
            "hades_7.virtNic -> VirtNic_7; "
            "VirtNic_7.nic <-> nic_7_compute.core0"
        ),
        quick_fix_child_port="nic",
        quick_fix_target_hint="firefly.nic core port",
    ),
    _key("firefly.hades", "proto"): SlotConstructionGuide(
        parent_type="firefly.hades",
        slot_name="proto",
        child_type="firefly.CtrlMsgProto",
        concise_fix=(
            "Attach firefly.CtrlMsgProto to hades.proto. The CtrlMsgProto "
            "child then owns a firefly.ctrlMsg process subcomponent."
        ),
        explanation=(
            "firefly.hades.proto is a SubComponent slot for the control-message "
            "protocol object. Queue/timing/process behavior belongs under "
            "CtrlMsgProto.process."
        ),
        example=(
            "hades_7.proto -> CtrlMsgProto_7; "
            "CtrlMsgProto_7.process -> ctrlMsg_7"
        ),
    ),
    _key("firefly.CtrlMsgProto", "process"): SlotConstructionGuide(
        parent_type="firefly.CtrlMsgProto",
        slot_name="process",
        child_type="firefly.ctrlMsg",
        concise_fix=(
            "Attach firefly.ctrlMsg to CtrlMsgProto.process, then connect "
            "ctrlMsg.loop to firefly.loopBack.nic0core0."
        ),
        explanation=(
            "firefly.CtrlMsgProto.process is the child process implementation. "
            "The loopback path is a real link from the ctrlMsg.loop port to the "
            "loopBack component."
        ),
        example=(
            "CtrlMsgProto_7.process -> ctrlMsg_7; "
            "ctrlMsg_7.loop <-> loopBack_7.nic0core0"
        ),
        quick_fix_child_port="loop",
        quick_fix_target_hint="firefly.loopBack nic/core port",
    ),
    _key("ember.EmberEngine", "OS"): SlotConstructionGuide(
        parent_type="ember.EmberEngine",
        slot_name="OS",
        child_type="firefly.hades",
        concise_fix=(
            "Attach firefly.hades to EmberEngine.OS. Do not attach "
            "firefly.hadesSHMEM there; select SHMEM through api.*.module params."
        ),
        explanation=(
            "EmberEngine.OS is the operating-system SubComponent slot. SHMEM "
            "and Misc APIs are selected by parameters such as api.0.module, not "
            "by attaching them to the OS slot."
        ),
        example=(
            "ember_compute_7.OS -> hades_7; api.0.module = "
            "firefly.hadesSHMEM; api.1.module = firefly.hadesMisc"
        ),
    ),
    _key("ember.EmberEngine", "motif"): SlotConstructionGuide(
        parent_type="ember.EmberEngine",
        slot_name="motif",
        child_type="ember motif generator",
        concise_fix=(
            "Use the logical motif attachment only as a FUSE aid; export should "
            "flatten it to motif_count and motif0.* parameters."
        ),
        explanation=(
            "Ember motifs are loaded anonymously by EmberEngine from "
            "motifN.name parameters. They are not ordinary nested SST "
            "SubComponents."
        ),
        example="motif_count = 1; motif0.name = ember.ShmemFAM_PutMotif",
    ),
    _key("merlin.hr_router", "topology"): SlotConstructionGuide(
        parent_type="merlin.hr_router",
        slot_name="topology",
        child_type="merlin.mesh / merlin.torus / merlin.singlerouter / ...",
        concise_fix=(
            "Attach the intended Merlin topology subcomponent to topology and "
            "keep the router topology parameter consistent."
        ),
        explanation=(
            "Merlin routers use a topology subcomponent plus topology "
            "parameters. For a 2x2 mesh model this should be merlin.mesh, not "
            "merlin.singlerouter."
        ),
        example=(
            "rtr_1x1.topology -> merlin.mesh; topology = merlin.mesh; "
            "mesh.shape = 2x2"
        ),
    ),
}


UNATTACHED_SUBCOMPONENT_GUIDES: dict[str, UnattachedSubcomponentGuide] = {
    "merlin.linkcontrol": UnattachedSubcomponentGuide(
        child_type="merlin.linkcontrol",
        concise_fix=(
            "Attach this merlin.linkcontrol to a NIC rtrLink slot, then connect "
            "its rtr_port to a router port."
        ),
        explanation=(
            "merlin.linkcontrol is normally the network-interface child owned by "
            "a component such as firefly.nic. It should not remain as a "
            "top-level SST JSON component."
        ),
        example=(
            "nic_7_compute.rtrLink -> linkcontrol_7; "
            "linkcontrol_7.rtr_port <-> rtr_1x1.port5"
        ),
    ),
    "firefly.VirtNic": UnattachedSubcomponentGuide(
        child_type="firefly.VirtNic",
        concise_fix="Attach this firefly.VirtNic to firefly.hades.virtNic.",
        explanation=(
            "firefly.VirtNic is the virtual NIC child owned by firefly.hades. "
            "It also needs a real link from VirtNic.nic to firefly.nic.coreN."
        ),
        example=(
            "hades_7.virtNic -> VirtNic_7; "
            "VirtNic_7.nic <-> nic_7_compute.core0"
        ),
    ),
    "firefly.CtrlMsgProto": UnattachedSubcomponentGuide(
        child_type="firefly.CtrlMsgProto",
        concise_fix="Attach this firefly.CtrlMsgProto to firefly.hades.proto.",
        explanation=(
            "firefly.CtrlMsgProto is the protocol child owned by firefly.hades."
        ),
        example="hades_7.proto -> CtrlMsgProto_7",
    ),
    "firefly.ctrlMsg": UnattachedSubcomponentGuide(
        child_type="firefly.ctrlMsg",
        concise_fix="Attach this firefly.ctrlMsg to firefly.CtrlMsgProto.process.",
        explanation=(
            "firefly.ctrlMsg is the process child owned by CtrlMsgProto. Its "
            "loop port should connect to firefly.loopBack.nic0core0."
        ),
        example=(
            "CtrlMsgProto_7.process -> ctrlMsg_7; "
            "ctrlMsg_7.loop <-> loopBack_7.nic0core0"
        ),
    ),
    "firefly.SimpleMemory": UnattachedSubcomponentGuide(
        child_type="firefly.SimpleMemory",
        concise_fix=(
            "Attach this as the NIC simpleMemoryModel logical child; export "
            "should fold its values to simpleMemoryModel.* NIC params."
        ),
        explanation=(
            "firefly.SimpleMemory is created internally by firefly.nic when "
            "useSimpleMemoryModel=1. FUSE may show it visually, but SST JSON "
            "should receive simpleMemoryModel.* params on the NIC."
        ),
        example="nic_7_compute.simpleMemoryModel -> sm_7_compute",
    ),
    "merlin.mesh": UnattachedSubcomponentGuide(
        child_type="merlin.mesh",
        concise_fix="Attach this merlin.mesh to merlin.hr_router.topology.",
        explanation=(
            "merlin.mesh is a router topology child, not a top-level SST "
            "component."
        ),
        example="rtr_1x1.topology -> merlin.mesh",
    ),
}


def _child_port_key(child_type: str, port_name: str) -> tuple[str, str]:
    return (child_type.strip(), port_name.strip())


CHILD_PORT_GUIDES: dict[tuple[str, str], ChildPortConstructionGuide] = {
    _child_port_key("merlin.linkcontrol", "rtr_port"): ChildPortConstructionGuide(
        child_type="merlin.linkcontrol",
        port_name="rtr_port",
        concise_fix="Connect this merlin.linkcontrol.rtr_port to the correct merlin.hr_router port.",
        explanation=(
            "A firefly.nic owns merlin.linkcontrol through its rtrLink slot, but "
            "traffic still cannot reach the network until linkcontrol.rtr_port is "
            "connected to a Merlin router port."
        ),
        example="linkcontrol_7.rtr_port <-> rtr_1x1.port5",
    ),
    _child_port_key("firefly.VirtNic", "nic"): ChildPortConstructionGuide(
        child_type="firefly.VirtNic",
        port_name="nic",
        concise_fix="Connect this firefly.VirtNic.nic port to the matching firefly.nic core port.",
        explanation=(
            "firefly.hades owns a firefly.VirtNic child, but the virtual NIC also "
            "needs a real SST link from VirtNic.nic to the node's firefly.nic core port."
        ),
        example="VirtNic_7.nic <-> nic_7_compute.core0",
    ),
    _child_port_key("firefly.ctrlMsg", "loop"): ChildPortConstructionGuide(
        child_type="firefly.ctrlMsg",
        port_name="loop",
        concise_fix="Connect this firefly.ctrlMsg.loop port to firefly.loopBack.nic0core0.",
        explanation=(
            "firefly.CtrlMsgProto owns a firefly.ctrlMsg process child.  The "
            "process loop port must be connected to the node's Firefly loopBack component."
        ),
        example="ctrlMsg_7.loop <-> loopBack_7.nic0core0",
    ),
}


def sst_type_for_node(node: Any) -> str:
    """Return the SST element.component type string for a FUSE node."""
    if node is None:
        return ""

    component = getattr(node, "component", None)
    if component is None:
        return ""

    element = str(getattr(component, "element", "") or "").strip()
    name = str(getattr(component, "name", "") or "").strip()

    if element and name:
        return f"{element}.{name}"
    return name


def find_node_by_id(scene: Any, node_id: int | None):
    """Find a component node by FUSE node id without depending on scene internals."""
    if scene is None or node_id is None:
        return None

    try:
        for node in scene.component_items():
            if getattr(node, "node_id", None) == node_id:
                return node
    except Exception:
        return None

    return None


def parse_slot_name(issue: Any) -> str:
    """Extract a slot name from an issue parameter or message text."""
    parameter_name = str(getattr(issue, "parameter_name", "") or "").strip()
    if parameter_name:
        return parameter_name

    message = str(getattr(issue, "message", "") or "")
    match = re.search(r"slot '([^']+)'", message)
    if match:
        return match.group(1)

    return ""


def guide_for_slot(parent_type: str, slot_name: str) -> SlotConstructionGuide | None:
    return SLOT_GUIDES.get(_key(parent_type, slot_name))


def guide_for_slot_connector(connector: Any) -> SlotConstructionGuide | None:
    """Return guidance for a FUSE subcomponent slot connector, if known."""
    if connector is None or getattr(connector, "role", "") != "slot":
        return None

    node = getattr(connector, "node", None)
    parent_type = sst_type_for_node(node)
    slot_name = str(getattr(connector, "name", "") or "").strip()

    if not parent_type or not slot_name:
        return None

    return guide_for_slot(parent_type, slot_name)


def guide_for_issue(scene: Any, issue: Any) -> SlotConstructionGuide | None:
    """Return construction guidance for a validation issue, if it names a slot."""
    node = find_node_by_id(scene, getattr(issue, "node_id", None))
    node_type = sst_type_for_node(node)
    slot_name = parse_slot_name(issue)

    if not node_type or not slot_name:
        return None

    return guide_for_slot(node_type, slot_name)


def guide_child_type_is_concrete(child_type: str) -> bool:
    """Return whether child_type names one concrete SST element.component type."""
    value = str(child_type or "").strip()
    if not value:
        return False

    # Concrete SST types look like element.component.  Entries such as
    # "merlin.mesh / merlin.torus / ..." or "ember motif generator" are
    # explanatory only and should not be auto-created.
    if "." not in value:
        return False
    if any(token in value for token in ("/", " ", "...")):
        return False

    element, _, name = value.partition(".")
    return bool(element and name)


def guide_can_create_child(guide: SlotConstructionGuide | None) -> bool:
    """Return whether FUSE can auto-create the guide's child subcomponent."""
    return bool(
        guide is not None
        and guide_child_type_is_concrete(guide.child_type)
    )


def issue_can_create_child(scene: Any, issue: Any) -> bool:
    """Return whether a validation issue has a known child-subcomponent fix."""
    return guide_can_create_child(guide_for_issue(scene, issue))


def guide_has_quick_fix(guide: SlotConstructionGuide | None) -> bool:
    """Return whether the guide can create a child and continue with a port link."""
    return bool(
        guide is not None
        and guide.child_type
        and guide.quick_fix_child_port
    )


def guide_for_unattached_subcomponent(
    child_type: str,
) -> UnattachedSubcomponentGuide | None:
    return UNATTACHED_SUBCOMPONENT_GUIDES.get(child_type.strip())


def suggested_fix_for_issue(scene: Any, issue: Any) -> str:
    """Return an SST-specific suggested fix for a validation issue, if known."""
    issue_type = str(getattr(issue, "issue_type", "") or "")

    if issue_type == "sst_export_deprecated_connector":
        node = find_node_by_id(scene, getattr(issue, "node_id", None))
        connector_name = parse_slot_name(issue)
        connector_kind = (
            "slot"
            if getattr(issue, "attachment_id", None) is not None
            else "port"
        )
        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_rule_for_node,
            )

            rule = deprecated_connector_rule_for_node(
                node,
                connector_name,
                connector_kind,
            )
        except Exception:
            rule = None

        replacement = str(getattr(rule, "replacement_name", "") or "").strip()
        replacement_kind = str(getattr(rule, "replacement_kind", "") or "").strip()
        if replacement:
            return f"Use {replacement} {replacement_kind or connector_kind} instead."
        return (
            "Replace this deprecated SST connector with the current connector "
            "recommended by the selected SST Elements version."
        )

    if issue_type == "sst_export_memhierarchy_slot_port_mode_conflict":
        return (
            "Choose one memHierarchy connection mode on this side: keep the "
            "direct port link and delete the same-named SubComponent slot "
            "attachment, or keep the slot manager child and delete the direct "
            "port link."
        )

    if issue_type == "sst_export_shadowed_raw_port":
        if str(getattr(issue, "severity", "") or "") == "warning":
            return (
                "Review whether this advanced/raw direct port path is intentional; "
                "guided models should use the slot-based construction when available."
            )
        return (
            "Replace the direct raw-port link with the required slot child, "
            "then connect the child real port to the peer port."
        )

    if issue_type == "sst_export_runtime_child_port":
        child_port_fix = child_port_suggested_fix_for_issue(scene, issue)
        if child_port_fix:
            return child_port_fix

    guide = guide_for_issue(scene, issue)
    if guide is not None:
        return guide.concise_fix

    node = find_node_by_id(scene, getattr(issue, "node_id", None))
    node_type = sst_type_for_node(node)
    message = str(getattr(issue, "message", "") or "")

    if "SubComponent instances must be attached to a parent slot" in message:
        guide = guide_for_unattached_subcomponent(node_type)
        if guide is not None:
            return guide.concise_fix

    return ""
