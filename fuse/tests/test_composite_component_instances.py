from PySide6.QtCore import QPointF

from fuse.core.model.composite import CompositeComponentDefinition
from fuse.core.persistence.project_io import component_node_to_save_dict
from fuse.core.ui.composite_builder import component_definition_for_composite
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.properties_panel import PropertiesPanel


def composite_component(name="Pair", composite_id="pair-template", icon_path="icons/pair.png"):
    definition = CompositeComponentDefinition.make(
        composite_id=composite_id,
        name=name,
        icon_path=icon_path,
        port_mappings=[],
    )
    return component_definition_for_composite(definition)


def tree_item_by_name(panel: PropertiesPanel, name: str):
    for root_index in range(panel.tree.topLevelItemCount()):
        root = panel.tree.topLevelItem(root_index)
        if root.text(0) == name:
            return root

        for child_index in range(root.childCount()):
            child = root.child(child_index)
            if child.text(0) == name:
                return child

    return None


def test_composite_instances_use_template_name_with_incrementing_suffix(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair")

    first = scene.create_component_node(component, QPointF(0.0, 0.0))
    second = scene.create_component_node(component, QPointF(200.0, 0.0))

    assert first.instance_name == "Pair_1"
    assert second.instance_name == "Pair_2"


def test_explicit_composite_instance_name_does_not_consume_next_default(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair")

    explicit = scene.create_component_node(
        component,
        QPointF(0.0, 0.0),
        instance_name="CustomPair",
    )
    default = scene.create_component_node(component, QPointF(200.0, 0.0))

    assert explicit.instance_name == "CustomPair"
    assert default.instance_name == "Pair_1"


def test_composite_instance_save_preserves_instance_name_icon_and_template_identity(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair", composite_id="pair-template")
    node = scene.create_component_node(component, QPointF(0.0, 0.0))
    node.set_instance_name("UserNamedPair")
    node.set_icon_path("custom/pair-instance.png")

    saved = component_node_to_save_dict(node)

    assert saved["instanceName"] == "UserNamedPair"
    assert saved["iconPath"] == "custom/pair-instance.png"
    assert saved["isComposite"] == 1
    assert saved["compositeId"] == "pair-template"


def test_properties_panel_labels_composite_instance_and_keeps_template_metadata(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair", composite_id="pair-template")
    node = scene.create_component_node(component, QPointF(0.0, 0.0))
    panel = PropertiesPanel()
    qtbot.addWidget(panel)

    panel.show_component(node)

    assert panel.title.text() == "Composite Component Instance"
    assert tree_item_by_name(panel, "Kind").text(1) == "Composite Component"
    assert tree_item_by_name(panel, "Template Name").text(1) == "Pair"
    assert tree_item_by_name(panel, "Template ID").text(1) == "pair-template"


def test_properties_panel_edits_only_composite_instance_name_and_icon(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair", composite_id="pair-template")
    node = scene.create_component_node(component, QPointF(0.0, 0.0))
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    name_item = tree_item_by_name(panel, "Name")
    icon_item = tree_item_by_name(panel, "Icon Path")

    name_item.setText(1, "EditedPair")
    panel.on_item_changed(name_item, 1)
    icon_item.setText(1, "icons/edited-instance.png")
    panel.on_item_changed(icon_item, 1)

    assert node.instance_name == "EditedPair"
    assert node.icon_path == "icons/edited-instance.png"
    assert node.component.name == "Pair"
    assert node.component.icon_path == "icons/pair.png"
    assert node.component.composite_id == "pair-template"
