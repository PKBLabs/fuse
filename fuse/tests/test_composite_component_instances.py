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


def test_composite_instances_use_template_name_with_incrementing_suffix(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="Pair")

    first = scene.create_component_node(component, QPointF(0.0, 0.0))
    second = scene.create_component_node(component, QPointF(200.0, 0.0))

    assert first.instance_name == "Pair_0"
    assert second.instance_name == "Pair_1"


def test_explicit_composite_instance_name_does_not_consume_next_default(qtbot, monkeypatch):
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
    assert default.instance_name == "Pair_0"


def test_composite_instance_save_preserves_instance_name_icon_and_template_identity(qtbot, monkeypatch):
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

    assert panel.title.text() == "Composite Component Properties"
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


def test_name_token_controls_component_copy_numbering(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    scene = ModelScene()
    component = composite_component(name="tile%d")

    first = scene.create_component_node(component, QPointF(0.0, 0.0))
    second = scene.create_component_node(component, QPointF(200.0, 0.0))

    assert first.instance_name == "tile0"
    assert second.instance_name == "tile1"

    renamed = scene.rename_component_node(first, "my_%d_tile")
    assert renamed == "my_0_tile"
    assert first.instance_name == "my_0_tile"

    scene.clearSelection()
    first.setSelected(True)
    assert scene.copy_selection_to_clipboard() is True
    pasted = scene.paste_clipboard(QPointF(400.0, 0.0))

    assert len(pasted) == 1
    assert pasted[0].instance_name == "my_1_tile"


def test_repeated_composite_instances_get_unique_internal_component_names(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "composites.db"))

    from fuse.core.model.composite import CompositePortMapping
    from fuse.core.persistence.composite_components import save_composite_component_definition

    definition = CompositeComponentDefinition.make(
        composite_id="internal-name-copy-test",
        name="Pair",
        mini_model={
            "schemaVersion": "0.1.0",
            "kind": "fuse.composite-mini-model",
            "components": [
                {
                    "id": 1,
                    "element": "test",
                    "name": "Cache",
                    "pluginId": "core",
                    "targetId": "",
                    "componentId": "cache",
                    "instanceName": "cache_a",
                    "parameters": {},
                    "variablePortCounts": {},
                    "position": {"x": 0.0, "y": 0.0},
                },
                {
                    "id": 2,
                    "element": "test",
                    "name": "Cache",
                    "pluginId": "core",
                    "targetId": "",
                    "componentId": "cache",
                    "instanceName": "cache_b",
                    "parameters": {},
                    "variablePortCounts": {},
                    "position": {"x": 180.0, "y": 0.0},
                },
            ],
            "links": [
                {
                    "id": 1,
                    "name": "cache_link",
                    "sourceLatency": "1ns",
                    "targetLatency": "1ns",
                    "type": "point_to_point",
                    "source": {"nodeId": 1, "componentName": "cache_a", "port": "out"},
                    "target": {"nodeId": 2, "componentName": "cache_b", "port": "in"},
                }
            ],
            "subcompAttachments": [],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.in",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="in",
                exposed=True,
            )
        ],
    )
    definition = save_composite_component_definition(definition)

    scene = ModelScene()
    component = component_definition_for_composite(definition)
    first = scene.create_component_node(component, QPointF(0.0, 0.0))
    second = scene.create_component_node(component, QPointF(240.0, 0.0))

    first_names = [item["instanceName"] for item in first.composite_instance_model["components"]]
    second_names = [item["instanceName"] for item in second.composite_instance_model["components"]]

    assert first_names == ["cache_a", "cache_b"]
    assert second_names == ["cache_a_1", "cache_b_1"]
    assert not set(first_names).intersection(second_names)
    assert second.composite_instance_model["links"][0]["source"]["componentName"] == "cache_a_1"
    assert second.composite_instance_model["links"][0]["target"]["componentName"] == "cache_b_1"
    assert second.composite_port_mappings[0].internal_component_name == "cache_a_1"
    assert second.composite_port_mappings[0].exposed is True



def test_copy_pasted_composite_instance_updates_internal_link_names_and_endpoints(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )
    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "composites.db"))

    from fuse.core.model.composite import CompositePortMapping
    from fuse.core.persistence.composite_components import save_composite_component_definition

    definition = CompositeComponentDefinition.make(
        composite_id="internal-link-copy-test",
        name="Pair",
        mini_model={
            "schemaVersion": "0.1.0",
            "kind": "fuse.composite-mini-model",
            "components": [
                {
                    "id": 1,
                    "element": "test",
                    "name": "Cache",
                    "pluginId": "core",
                    "targetId": "",
                    "componentId": "cache",
                    "instanceName": "cache_a",
                    "parameters": {},
                    "variablePortCounts": {},
                    "position": {"x": 0.0, "y": 0.0},
                },
                {
                    "id": 2,
                    "element": "test",
                    "name": "Cache",
                    "pluginId": "core",
                    "targetId": "",
                    "componentId": "cache",
                    "instanceName": "cache_b",
                    "parameters": {},
                    "variablePortCounts": {},
                    "position": {"x": 180.0, "y": 0.0},
                },
            ],
            "links": [
                {
                    "id": 1,
                    "name": "link_cache_a_cache_b",
                    "sourceLatency": "1ns",
                    "targetLatency": "1ns",
                    "type": "point_to_point",
                    "source": {"nodeId": 1, "componentName": "cache_a", "port": "out"},
                    "target": {"nodeId": 2, "componentName": "cache_b", "port": "in"},
                }
            ],
            "subcompAttachments": [],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.in",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="in",
                exposed=True,
            )
        ],
    )
    definition = save_composite_component_definition(definition)

    scene = ModelScene()
    component = component_definition_for_composite(definition)
    first = scene.create_component_node(component, QPointF(0.0, 0.0))
    scene.clearSelection()
    first.setSelected(True)

    assert scene.copy_selection_to_clipboard() is True
    pasted = scene.paste_clipboard(QPointF(240.0, 0.0))
    assert len(pasted) == 1
    second = pasted[0]

    link = second.composite_instance_model["links"][0]
    assert link["source"]["componentName"] == "cache_a_1"
    assert link["target"]["componentName"] == "cache_b_1"
    assert link["name"] == "link_cache_a_1_cache_b_1"
    assert second.composite_port_mappings[0].internal_component_name == "cache_a_1"
