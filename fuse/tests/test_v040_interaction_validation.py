from types import SimpleNamespace

from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition, ModelSubcompAttachment
from fuse.core.model.validation import validate_model_for_export
from fuse.core.ui.graphics_items import ComponentNodeItem, SubcompAttachmentItem
from fuse.core.ui.model_scene import ModelScene


def _component(plugin_id="sst", name="Parent", *, is_subcomp=0, iface=""):
    return ComponentDefinition(
        plugin_id=plugin_id,
        target_id="1",
        component_id=name,
        element="test",
        name=name,
        is_subcomp=is_subcomp,
        iface=iface,
    )


def _subcomp_metadata(plugin_id, component_id, target_id=None):
    if component_id == "Parent":
        return [{"name": "slot", "role": "slot", "required_interface": "Iface", "interface": "Iface"}]
    if component_id == "Child":
        return [{"name": "iface", "role": "interface", "provided_interface": "Iface", "interface": "Iface"}]
    return []


def test_subcomponent_attachment_can_be_deleted_by_id(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_subcomp_connector_metadata_for_component",
        _subcomp_metadata,
    )
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    parent = ComponentNodeItem(_component(name="Parent"), instance_name="parent0")
    child = ComponentNodeItem(_component(name="Child", is_subcomp=1, iface="Iface"), instance_name="child0")
    parent.setPos(QPointF(0, 0))
    child.setPos(QPointF(300, 0))
    scene.addItem(parent)
    scene.addItem(child)

    attachment = ModelSubcompAttachment(1, "attach", parent.node_id, "parent0", "slot", child.node_id, "child0", "Iface", "Iface")
    scene.subcomp_attachments.append(attachment)
    item = SubcompAttachmentItem(attachment, parent.subcomp_connectors[0], child.subcomp_connectors[0])
    scene.addItem(item)

    assert len(scene.subcomp_attachments) == 1
    assert scene.find_subcomp_attachment_by_id(1) is item

    scene.delete_subcomp_attachment_by_id(1)

    assert scene.subcomp_attachments == []
    assert scene.find_subcomp_attachment_by_id(1) is None


def test_export_validation_rejects_mixed_plugin_model():
    sst_node = SimpleNamespace(
        node_id=1,
        instance_name="sst0",
        parameters={},
        component=SimpleNamespace(plugin_id="sst", component_id="sst", target_id="1"),
    )
    gem5_node = SimpleNamespace(
        node_id=2,
        instance_name="gem50",
        parameters={},
        component=SimpleNamespace(plugin_id="gem5", component_id="system", target_id="1"),
    )

    class Scene:
        active_plugin_id = "sst"
        links = []
        subcomp_attachments = []

        def component_items(self):
            return [sst_node, gem5_node]

    issues = validate_model_for_export(Scene(), "sst")

    assert any(issue.issue_type == "export_target" for issue in issues)
    assert any("Mixed-plugin" in issue.message for issue in issues)
