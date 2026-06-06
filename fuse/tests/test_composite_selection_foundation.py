# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition
from fuse.plugin_api.interfaces import LinkCompatibilityResult
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.selection_helpers import (
    can_create_composite_from_selection,
    is_internal_selected_connection,
    request_composite_from_selection,
    selected_component_items,
    selected_internal_connection_items,
    update_selection_dependent_highlights,
)


def component(name: str) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
    )


def make_three_node_scene(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    first = scene.create_component_node(component("First"), QPointF(0.0, 0.0))
    second = scene.create_component_node(component("Second"), QPointF(320.0, 0.0))
    third = scene.create_component_node(component("Third"), QPointF(640.0, 0.0))

    first_out = next(port for port in first.ports if port.name == "out")
    second_in = next(port for port in second.ports if port.name == "in")
    second_out = next(port for port in second.ports if port.name == "out")
    third_in = next(port for port in third.ports if port.name == "in")

    first_second = scene.create_link_between_ports(
        first_out,
        second_in,
        LinkCompatibilityResult(can_create=True, severity="ok"),
    )
    second_third = scene.create_link_between_ports(
        second_out,
        third_in,
        LinkCompatibilityResult(can_create=True, severity="ok"),
    )

    return scene, first, second, third, first_second, second_third


def test_multiselection_highlights_only_links_with_both_endpoints_selected(qtbot, monkeypatch):
    scene, first, second, third, first_second, second_third = make_three_node_scene(monkeypatch)

    first.setSelected(True)
    second.setSelected(True)
    update_selection_dependent_highlights(scene)

    assert can_create_composite_from_selection(scene) is True
    assert selected_component_items(scene) == [first, second]
    assert selected_internal_connection_items(scene) == [first_second]
    assert is_internal_selected_connection(scene, first_second) is True
    assert is_internal_selected_connection(scene, second_third) is False
    assert first_second.pen().widthF() == 4.0
    assert second_third.pen().widthF() == 2.0

    third.setSelected(True)
    update_selection_dependent_highlights(scene)

    assert selected_internal_connection_items(scene) == [first_second, second_third]
    assert first_second.pen().widthF() == 4.0
    assert second_third.pen().widthF() == 4.0


def test_selected_component_uses_highlight_style_instead_of_default_dashed_border(qtbot, monkeypatch):
    scene, first, second, *_ = make_three_node_scene(monkeypatch)

    normal_color = first.brush().color().name()
    first.setSelected(True)
    update_selection_dependent_highlights(scene)

    assert first.brush().color().name() != normal_color
    assert first.pen().color().name() == "#2563eb"
    assert first.pen().widthF() == 2.5

    first.setSelected(False)
    second.setSelected(True)
    update_selection_dependent_highlights(scene)

    assert first.brush().color().name() == normal_color
    assert first.pen().widthF() == 1.25


def test_create_composite_request_reports_selected_fragment(monkeypatch):
    scene, first, second, third, first_second, second_third = make_three_node_scene(monkeypatch)
    captured = {}

    def record_request(components, links, attachments):
        captured["components"] = components
        captured["links"] = links
        captured["attachments"] = attachments

    first.setSelected(True)
    second.setSelected(True)
    update_selection_dependent_highlights(scene)

    request_composite_from_selection(scene, record_request)

    assert captured["components"] == [first, second]
    assert captured["links"] == [first_second]
    assert captured["attachments"] == []
    assert second_third not in captured["links"]
    assert third not in captured["components"]
