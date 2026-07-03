# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from pathlib import Path

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.plugins.community.sst.export_json import build_sst_json_dict, validate_sst_json_export
from fuse.plugins.community.sst.runtime_overlays import (
    available_runtime_overlay_versions,
    load_runtime_overlay,
)
from fuse.plugins.community.sst.tests.scene_test_helpers import FakeNode, FakeScene
from fuse.plugins.community.sst.tools.build_runtime_overlay import (
    build_runtime_overlay_candidate_report,
)


def _component(element: str, name: str, *, is_subcomp: int = 0, version: str = "16.0.0") -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
        framework_version=version,
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


def test_runtime_overlay_is_versioned_and_keeps_catalog_additions_out_of_policy_catalog():
    versions = set(available_runtime_overlay_versions())

    assert {"15.1.2", "16.0.0"}.issubset(versions)
    assert "OS" in load_runtime_overlay("16.0.0").component("ember.EmberEngine").runtime_slots
    assert "OS" in load_runtime_overlay("15.1.2").component("ember.EmberEngine").runtime_slots
    assert load_runtime_overlay("does-not-exist").components == {}


def test_missing_required_runtime_overlay_slot_blocks_export():
    engine = _node(1, "rank0", "ember", "EmberEngine", {"jobId": "0"})

    report = validate_sst_json_export(FakeScene([engine]))

    messages = "\n".join(issue.message for issue in report.errors)
    assert "Required SST runtime subcomponent slot 'OS' is not filled" in messages
    assert not report.can_export


def test_runtime_overlay_slots_make_hidden_ember_firefly_chain_exportable():
    engine = _node(1, "rank0", "ember", "EmberEngine", {"jobId": "0"})
    os = _node(
        2,
        "rank0_os",
        "firefly",
        "hades",
        {"numNodes": "1", "netMapSize": "1", "netMapName": "Firefly0", "netId": "0"},
        is_subcomp=1,
    )
    virt = _node(3, "rank0_virt", "firefly", "VirtNic", is_subcomp=1)
    proto = _node(4, "rank0_proto", "firefly", "CtrlMsgProto", is_subcomp=1)
    process = _node(5, "rank0_process", "firefly", "ctrlMsg", is_subcomp=1)
    nic = _node(6, "nic0", "firefly", "nic", {"nid": "0", "packetSize": "2048B"})
    loopback = _node(7, "loopBack0", "firefly", "loopBack")
    linkcontrol = _node(8, "nic0_linkcontrol", "merlin", "linkcontrol", is_subcomp=1)

    attachments = [
        _attach(1, engine, "OS", os),
        _attach(2, os, "virtNic", virt),
        _attach(3, os, "proto", proto),
        _attach(4, proto, "process", process),
        _attach(5, nic, "rtrLink", linkcontrol),
    ]
    links = [
        ModelLink(1, "rank_nic", 1, "rank0", "nic", 6, "nic0", "core0"),
        ModelLink(2, "rank_loop", 1, "rank0", "loop", 7, "loopBack0", "nic0core0"),
    ]
    scene = FakeScene([engine, os, virt, proto, process, nic, loopback, linkcontrol], links=links, attachments=attachments)

    report = validate_sst_json_export(scene)
    assert report.can_export

    data = build_sst_json_dict(scene)
    links_by_name = {link["name"]: link for link in data["links"]}
    assert links_by_name["rank_nic"]["left"] == {
        "component": "rank0:OS:virtNic",
        "port": "nic",
        "latency": "1ns",
    }
    assert links_by_name["rank_loop"]["left"] == {
        "component": "rank0:OS:proto:process",
        "port": "loop",
        "latency": "1ns",
    }


def test_runtime_overlay_audit_reports_missing_runtime_slots(tmp_path: Path):
    source_root = tmp_path / "sst-elements"
    source_root.mkdir()
    (source_root / "fake.cc").write_text(
        '''
        class HiddenOwner {
          SST_ELI_REGISTER_COMPONENT(HiddenOwner, "fake", "owner", SST_ELI_ELEMENT_VERSION(1,0,0), "", COMPONENT_CATEGORY_UNCATEGORIZED)
          HiddenOwner(SST::ComponentId_t id, SST::Params& params) {
            auto sub = loadUserSubComponent<SST::Fake::API>("hiddenSlot");
          }
        };
        ''',
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text(
        '{"components": [{"element": "fake", "name": "owner", "subcomp_slots": []}]}',
        encoding="utf-8",
    )
    overlay = tmp_path / "overlay.json"
    overlay.write_text('{"components": {}}', encoding="utf-8")

    report = build_runtime_overlay_candidate_report(
        source_root=source_root,
        component_catalog=catalog,
        overlay=overlay,
    )

    assert report["missing_overlay_count"] == 1
    assert report["candidates"][0]["component_type"] == "fake.owner"
    assert report["candidates"][0]["slot_name"] == "hiddenSlot"
    assert report["candidates"][0]["needs_overlay"] is True


def test_runtime_overlay_audit_respects_manual_no_overlay_resolutions(tmp_path: Path):
    source_root = tmp_path / "sst-elements"
    source_root.mkdir()
    (source_root / "base.cc").write_text(
        '''
        class AbstractBase {
          AbstractBase(SST::ComponentId_t id, SST::Params& params) {
            auto sub = loadUserSubComponent<SST::Fake::API>("baseSlot");
          }
        };
        ''',
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.json"
    catalog.write_text('{"components": []}', encoding="utf-8")
    overlay = tmp_path / "overlay.json"
    overlay.write_text(
        '''{
          "manual_resolutions": [
            {
              "owner_class": "AbstractBase",
              "slot_name": "baseSlot",
              "resolution": "declared_by_concrete_types",
              "requires_overlay": false,
              "component_types": ["fake.concrete"],
              "rationale": "Base class only; concrete elements declare this slot."
            }
          ],
          "components": {}
        }''',
        encoding="utf-8",
    )

    report = build_runtime_overlay_candidate_report(
        source_root=source_root,
        component_catalog=catalog,
        overlay=overlay,
    )

    assert report["missing_overlay_count"] == 0
    assert report["unknown_or_ambiguous_owner_count"] == 0
    assert report["reviewed_no_overlay_count"] == 1
    assert report["candidates"][0]["owner_resolution_status"] == "reviewed_no_overlay"


def test_sst_16_overlay_records_manual_review_for_base_class_runtime_slots():
    overlay = load_runtime_overlay("16.0.0")
    # load_runtime_overlay intentionally exposes executable runtime slots, not the
    # audit-only manual review metadata. Read the file directly to verify the
    # durable review decisions that keep base-class scanner hits out of overlays.
    overlay_path = Path(__file__).resolve().parents[1] / "runtime_overlays" / "sst-16.0.0.json"
    raw = __import__("json").loads(overlay_path.read_text(encoding="utf-8"))
    resolutions = {(item["owner_class"], item["slot_name"]): item for item in raw["manual_resolutions"]}

    assert ("VanadisDecoder", "branch_unit") in resolutions
    assert ("VanadisDecoder", "os_handler") in resolutions
    assert resolutions[("VanadisDecoder", "branch_unit")]["requires_overlay"] is False
    assert "vanadis.VanadisRISCV64Decoder" in resolutions[("VanadisDecoder", "branch_unit")]["component_types"]
    assert overlay.component("vanadis.VanadisRISCV64Decoder") is None
