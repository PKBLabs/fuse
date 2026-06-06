# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition
from fuse.core.ui.composite_builder import (
    build_composite_definition_from_selection,
    replace_selection_with_composite_instance,
    selection_boundary_report,
)
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.selection_helpers import (
    selected_internal_connection_items,
    update_selection_dependent_highlights,
)
from fuse.plugin_api.interfaces import LinkCompatibilityResult


def component(name: str) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
    )


def make_linked_scene(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    first = scene.create_component_node(component("First"), QPointF(50.0, 80.0))
    second = scene.create_component_node(component("Second"), QPointF(350.0, 120.0))

    first.parameters["clock"] = "2GHz"
    second.parameters["size"] = "4KiB"

    first_out = next(port for port in first.ports if port.name == "out")
    second_in = next(port for port in second.ports if port.name == "in")

    link = scene.create_link_between_ports(
        first_out,
        second_in,
        LinkCompatibilityResult(can_create=True, severity="ok"),
    )
    link.link.source_latency = "3ns"
    link.link.target_latency = "5ns"

    return scene, first, second, link


def test_build_composite_definition_preserves_fragment_and_external_ports(qtbot, monkeypatch):
    scene, first, second, link = make_linked_scene(monkeypatch)
    first.setSelected(True)
    second.setSelected(True)
    update_selection_dependent_highlights(scene)

    definition = build_composite_definition_from_selection(
        name="Pair",
        icon_path="icons/pair.png",
        components=[first, second],
        internal_connections=selected_internal_connection_items(scene),
        internal_attachments=[],
        description="Reusable pair",
    )

    assert definition.name == "Pair"
    assert definition.description == "Reusable pair"
    assert definition.icon_path == "icons/pair.png"
    assert [component["instanceName"] for component in definition.mini_model["components"]] == [
        first.instance_name,
        second.instance_name,
    ]
    assert definition.mini_model["components"][0]["position"] == {"x": 0.0, "y": 0.0}
    assert definition.mini_model["components"][1]["position"] == {"x": 300.0, "y": 40.0}
    assert definition.mini_model["links"][0]["sourceLatency"] == "3ns"
    assert definition.mini_model["links"][0]["targetLatency"] == "5ns"
    assert [mapping.external_port_name for mapping in definition.port_mappings] == [
        f"{first.instance_name}.in",
        f"{second.instance_name}.out",
    ]
    assert definition.port_mappings[0].internal_node_id == first.node_id
    assert definition.port_mappings[1].internal_component_name == second.instance_name
    assert [mapping.exposed for mapping in definition.port_mappings] == [False, False]


def test_replace_selection_with_composite_instance_removes_fragment_and_keeps_composite_node(qtbot, monkeypatch, tmp_path):
    scene, first, second, link = make_linked_scene(monkeypatch)
    first.setSelected(True)
    second.setSelected(True)
    update_selection_dependent_highlights(scene)

    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "composites.db"))

    definition = build_composite_definition_from_selection(
        name="Pair",
        icon_path="",
        components=[first, second],
        internal_connections=[link],
        internal_attachments=[],
    )

    from fuse.core.persistence.composite_components import save_composite_component_definition

    definition = save_composite_component_definition(definition)

    composite_node = replace_selection_with_composite_instance(
        scene,
        definition,
        [first, second],
        [link],
        [],
    )

    assert scene.component_items() == [composite_node]
    assert scene.links == []
    assert composite_node.component.is_composite == 1
    assert composite_node.component.composite_id == definition.composite_id
    assert composite_node.instance_name == "Pair_1"
    assert composite_node.pos() == QPointF(50.0, 80.0)
    assert [mapping.exposed for mapping in composite_node.composite_port_mappings] == [False, False]
    assert [port.name for port in composite_node.ports] == []


def test_boundary_report_blocks_selection_with_link_to_unselected_component(qtbot, monkeypatch):
    scene, first, second, internal_link = make_linked_scene(monkeypatch)
    third = scene.create_component_node(component("Third"), QPointF(650.0, 120.0))

    second_out = next(port for port in second.ports if port.name == "out")
    third_in = next(port for port in third.ports if port.name == "in")
    boundary_link = scene.create_link_between_ports(
        second_out,
        third_in,
        LinkCompatibilityResult(can_create=True, severity="ok"),
    )

    report = selection_boundary_report(
        scene,
        [first, second],
        [internal_link],
        [],
    )

    assert report.has_boundary_items is True
    assert report.boundary_connections == [boundary_link]


def test_project_save_dict_preserves_composite_identity(qtbot, monkeypatch):
    from fuse.core.model.composite import CompositeComponentDefinition
    from fuse.core.persistence.project_io import component_node_to_save_dict
    from fuse.core.ui.composite_builder import component_definition_for_composite

    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    definition = CompositeComponentDefinition.make(
        composite_id="pair-template",
        name="Pair",
        port_mappings=[],
    )
    scene = ModelScene()
    node = scene.create_component_node(
        component_definition_for_composite(definition),
        QPointF(0.0, 0.0),
    )

    saved = component_node_to_save_dict(node)

    assert node.component.is_composite == 1
    assert saved["isComposite"] == 1
    assert saved["compositeId"] == "pair-template"
