# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from PySide6.QtCore import QPointF

from fuse.core.model.composite import CompositeComponentDefinition, CompositePortMapping
from fuse.core.persistence.composite_components import (
    get_composite_component_definition,
    save_composite_component_definition,
)
from fuse.core.persistence.project_io import (
    build_project_dict,
    load_project_into_scene,
)
from fuse.core.ui.composite_builder import component_definition_for_composite
from fuse.core.ui.composite_instance_editor import apply_composite_instance_edit
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


def cache_pair_definition(composite_id="instance-edit-pair"):
    definition = CompositeComponentDefinition.make(
        composite_id=composite_id,
        name="Cache Pair",
        mini_model={
            "schemaVersion": "0.1.0",
            "kind": "fuse.composite-mini-model",
            "components": [
                {
                    "id": 1,
                    "element": "memHierarchy",
                    "name": "Cache",
                    "pluginId": "sst",
                    "targetId": "sst-test",
                    "componentId": "cache-type",
                    "instanceName": "cache_a",
                    "parameters": {"cache_size": "4KiB"},
                    "variablePortCounts": {},
                    "position": {"x": 0.0, "y": 0.0},
                },
                {
                    "id": 2,
                    "element": "memHierarchy",
                    "name": "Cache",
                    "pluginId": "sst",
                    "targetId": "sst-test",
                    "componentId": "cache-type",
                    "instanceName": "cache_b",
                    "parameters": {"cache_size": "8KiB"},
                    "variablePortCounts": {},
                    "position": {"x": 180.0, "y": 0.0},
                },
            ],
            "links": [],
            "subcompAttachments": [],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.cpu",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="cpu",
            )
        ],
    )
    return save_composite_component_definition(definition)


def composite_node_for_definition(scene, definition):
    return scene.create_component_node(
        component_definition_for_composite(definition),
        QPointF(0.0, 0.0),
    )


def test_instance_edit_state_is_local_to_selected_composite_instance(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )
    definition = cache_pair_definition("local-instance-edit")
    scene = ModelScene()
    node = composite_node_for_definition(scene, definition)

    edited_model = dict(definition.mini_model)
    edited_model["components"] = [dict(component) for component in definition.mini_model["components"]]
    edited_model["components"][0]["parameters"] = {"cache_size": "32KiB"}
    edited_ports = [
        CompositePortMapping(
            external_port_name="cache_b.mem",
            internal_node_id=2,
            internal_component_name="cache_b",
            internal_port_name="mem",
        )
    ]

    apply_composite_instance_edit(node, edited_model, edited_ports)

    stored_definition = get_composite_component_definition(definition.composite_id)
    assert stored_definition is not None
    assert stored_definition.mini_model["components"][0]["parameters"]["cache_size"] == "4KiB"
    assert node.composite_instance_model["components"][0]["parameters"]["cache_size"] == "32KiB"
    assert node.composite_port_mappings[0].external_port_name == "cache_b.mem"


def test_project_round_trip_preserves_composite_instance_edit_state(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )
    definition = cache_pair_definition("round-trip-instance-edit")
    scene = ModelScene()
    node = composite_node_for_definition(scene, definition)
    edited_model = dict(definition.mini_model)
    edited_model["components"] = [dict(component) for component in definition.mini_model["components"]]
    edited_model["components"][1]["parameters"] = {"cache_size": "64KiB"}
    apply_composite_instance_edit(node, edited_model, definition.port_mappings)

    view = ModelView(scene)
    qtbot.addWidget(view)
    project = build_project_dict(scene, view, project_name="Composite edit test")

    restored_scene = ModelScene()
    load_project_into_scene(project, restored_scene)
    restored_node = restored_scene.component_items()[0]

    assert restored_node.component.composite_id == definition.composite_id
    assert restored_node.composite_instance_model["components"][1]["parameters"]["cache_size"] == "64KiB"
    assert restored_node.composite_port_mappings[0].external_port_name == "cache_a.cpu"


def test_flattening_uses_instance_specific_mini_model(monkeypatch):
    from fuse.core.model.composite_flattening import flatten_scene_for_export
    from fuse.tests.test_composite_flattening import FakeNode, FakePort, FakeScene, composite_component, patch_port_metadata

    patch_port_metadata(monkeypatch)
    definition = cache_pair_definition("flatten-instance-edit")
    node = FakeNode(
        composite_component(definition.composite_id, definition.name),
        20,
        "Cache Pair_1",
        ports=[FakePort("cache_a.cpu")],
    )
    edited_model = dict(definition.mini_model)
    edited_model["components"] = [dict(component) for component in definition.mini_model["components"]]
    edited_model["components"][0]["parameters"] = {"cache_size": "128KiB"}
    node.composite_instance_model = edited_model
    node.composite_port_mappings = list(definition.port_mappings)

    flattened = flatten_scene_for_export(FakeScene([node], []))
    cache_a = next(component for component in flattened.component_items() if component.instance_name == "cache_a_mc1")

    assert cache_a.parameters["cache_size"] == "128KiB"


def test_project_dict_for_nested_composite_mini_model_normalizes_duplicate_ids():
    from fuse.core.persistence.project_io import validate_project_dict
    from fuse.core.ui.composite_instance_editor import project_dict_for_mini_model

    mini_model = {
        "schemaVersion": "0.1.0",
        "kind": "fuse.composite-mini-model",
        "components": [
            {
                "id": 14,
                "element": "Composite Components",
                "name": "Cache Pair",
                "pluginId": "core",
                "targetId": "fuse-composite",
                "componentId": "small-composite",
                "isComposite": 1,
                "compositeId": "small-composite",
                "instanceName": "Cache Pair_1",
                "parameters": {},
                "variablePortCounts": {},
                "position": {"x": 0.0, "y": 0.0},
                "compositeInstance": {
                    "miniModel": {
                        "schemaVersion": "0.1.0",
                        "kind": "fuse.composite-mini-model",
                        "components": [
                            {
                                "id": 1,
                                "element": "memHierarchy",
                                "name": "Cache",
                                "pluginId": "sst",
                                "targetId": "sst-test",
                                "componentId": "cache-type",
                                "instanceName": "cache_a",
                                "parameters": {},
                                "variablePortCounts": {},
                                "position": {"x": 0.0, "y": 0.0},
                            }
                        ],
                        "links": [],
                        "subcompAttachments": [],
                    },
                    "portMappings": [],
                },
            },
            {
                "id": 14,
                "element": "Composite Components",
                "name": "Cache Pair",
                "pluginId": "core",
                "targetId": "fuse-composite",
                "componentId": "small-composite",
                "isComposite": 1,
                "compositeId": "small-composite",
                "instanceName": "Cache Pair_2",
                "parameters": {},
                "variablePortCounts": {},
                "position": {"x": 240.0, "y": 0.0},
                "compositeInstance": {
                    "miniModel": {
                        "schemaVersion": "0.1.0",
                        "kind": "fuse.composite-mini-model",
                        "components": [
                            {
                                "id": 1,
                                "element": "memHierarchy",
                                "name": "Cache",
                                "pluginId": "sst",
                                "targetId": "sst-test",
                                "componentId": "cache-type",
                                "instanceName": "cache_b",
                                "parameters": {},
                                "variablePortCounts": {},
                                "position": {"x": 0.0, "y": 0.0},
                            }
                        ],
                        "links": [],
                        "subcompAttachments": [],
                    },
                    "portMappings": [],
                },
            },
        ],
        "links": [],
        "subcompAttachments": [],
    }

    project = project_dict_for_mini_model(mini_model)
    ids = [component["id"] for component in project["components"]]

    assert ids == [14, 15]
    validate_project_dict(project)


def test_apply_composite_instance_edit_normalizes_duplicate_nested_ids(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )
    definition = cache_pair_definition("normalize-instance-edit")
    scene = ModelScene()
    node = composite_node_for_definition(scene, definition)
    edited_model = dict(definition.mini_model)
    edited_model["components"] = [
        dict(definition.mini_model["components"][0]),
        dict(definition.mini_model["components"][1]),
    ]
    edited_model["components"][1]["id"] = edited_model["components"][0]["id"]

    apply_composite_instance_edit(node, edited_model, definition.port_mappings)
    ids = [component["id"] for component in node.composite_instance_model["components"]]

    assert ids == [1, 2]


def test_instance_editor_exposes_and_hides_unlinked_internal_port(qtbot, monkeypatch):
    from fuse.core.ui.composite_instance_editor import CompositeInstanceEditorWidget

    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["cpu", "mem"],
    )
    definition = cache_pair_definition("instance-port-exposure")
    definition.port_mappings[0].exposed = False
    save_composite_component_definition(definition)

    scene = ModelScene()
    node = composite_node_for_definition(scene, definition)
    widget = CompositeInstanceEditorWidget(node)
    qtbot.addWidget(widget)

    internal_node = next(item for item in widget.editor_scene.component_items() if item.instance_name == "cache_a")
    port = next(port for port in internal_node.ports if port.name == "cpu")

    assert widget.port_is_exposed(port) is False
    assert [port.name for port in node.ports] == []

    assert widget.set_port_exposed(port, True) is True
    assert widget.port_is_exposed(port) is True
    assert [port.name for port in node.ports] == ["cache_a.cpu"]

    assert widget.set_port_exposed(port, False) is True
    assert widget.port_is_exposed(port) is False
    assert [port.name for port in node.ports] == []


def test_template_editor_saves_exposed_port_state_to_database(qtbot, monkeypatch):
    from fuse.core.ui.composite_instance_editor import CompositeTemplateEditorWidget

    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["cpu", "mem"],
    )
    definition = cache_pair_definition("template-port-exposure")
    definition.port_mappings[0].exposed = False
    save_composite_component_definition(definition)

    widget = CompositeTemplateEditorWidget(definition)
    qtbot.addWidget(widget)

    internal_node = next(item for item in widget.editor_scene.component_items() if item.instance_name == "cache_a")
    port = next(port for port in internal_node.ports if port.name == "cpu")

    assert widget.port_is_exposed(port) is False
    assert widget.set_port_exposed(port, True) is True
    saved = widget.save_template_changes()

    assert saved.port_mappings[0].exposed is True
    stored = get_composite_component_definition(definition.composite_id)
    assert stored is not None
    assert stored.port_mappings[0].exposed is True
