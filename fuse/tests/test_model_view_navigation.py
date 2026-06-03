# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from PySide6.QtCore import QPoint, QPointF, Qt

from fuse.core.model.models import ComponentDefinition
from fuse.plugin_api.interfaces import LinkCompatibilityResult
from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, PortItem
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


def test_model_view_zoom_controls_update_transform(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    view.set_zoom_percent(200.0)

    assert view.zoom_percent == 200.0
    assert round(view.transform().m11(), 2) == 2.0

    view.zoom_out()
    assert view.zoom_percent == 100.0


def test_model_view_select_and_multiselect_modes_toggle_drag_behavior(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    view.enable_multiselect_mode()
    assert view.mode == "multiselect"
    assert view.dragMode() == ModelView.RubberBandDrag

    view.enable_select_move_mode()
    assert view.mode == "select"
    assert view.dragMode() == ModelView.NoDrag


def test_model_view_hit_testing_still_finds_component_port_and_link_when_zoomed(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)

    source = scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="a", element="test", name="CPU"),
        QPointF(-140.0, 0.0),
    )
    target = scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="b", element="test", name="Cache"),
        QPointF(180.0, 0.0),
    )
    source_port = next(port for port in source.ports if port.name == "out")
    target_port = next(port for port in target.ports if port.name == "in")
    connection = scene.create_link_between_ports(
        source_port,
        target_port,
        LinkCompatibilityResult(can_create=True, severity="ok"),
    )

    for percent in (50.0, 200.0):
        view.set_zoom_percent(percent)

        component_point = view.mapFromScene(source.sceneBoundingRect().center())
        port_point = view.mapFromScene(source_port.scene_center())
        link_point = view.mapFromScene(connection.path().pointAtPercent(0.5))

        assert isinstance(view.itemAt(component_point), ComponentNodeItem)
        assert isinstance(view.itemAt(port_point), PortItem)
        assert isinstance(view.itemAt(link_point), ConnectionItem)


def test_model_view_background_drag_pans_without_moving_component(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)
    view.enable_select_move_mode()

    node = scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="a", element="test", name="CPU"),
        QPointF(1000.0, 1000.0),
    )
    original_node_pos = node.pos()
    original_h = view.horizontalScrollBar().value()
    original_v = view.verticalScrollBar().value()

    start = view.viewport().rect().center()
    end = start + QPointF(80.0, 60.0).toPoint()
    qtbot.mousePress(view.viewport(), Qt.LeftButton, pos=start)
    qtbot.mouseMove(view.viewport(), pos=end)
    qtbot.mouseRelease(view.viewport(), Qt.LeftButton, pos=end)

    assert node.pos() == original_node_pos
    assert (
        view.horizontalScrollBar().value() != original_h
        or view.verticalScrollBar().value() != original_v
    )


def test_model_view_editor_state_restores_zoom_mode_center_and_toolbar(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)

    view.set_zoom_percent(200.0)
    view.enable_multiselect_mode()
    view.set_toolbar_position(96, 44)
    view.centerOn(250.0, -125.0)

    state = view.editor_state()

    restored = ModelView(scene)
    qtbot.addWidget(restored)
    restored.resize(800, 600)
    restored.show()
    qtbot.waitExposed(restored)

    restored.apply_editor_state(state)

    assert restored.zoom_percent == 200.0
    assert restored.mode == "multiselect"
    assert restored.dragMode() == ModelView.RubberBandDrag
    assert restored.toolbar.pos() == QPoint(96, 44)
    center = restored.mapToScene(restored.viewport().rect().center())
    assert abs(center.x() - state["viewCenter"]["x"]) <= 1.0
    assert abs(center.y() - state["viewCenter"]["y"]) <= 1.0


def test_model_view_toolbar_position_is_clamped_to_viewport(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(260, 120)
    view.show()
    qtbot.waitExposed(view)

    view.set_toolbar_position(10000, 10000)

    assert view.toolbar.pos().x() <= view.viewport().width() - view.toolbar.width() - 4
    assert view.toolbar.pos().y() <= view.viewport().height() - view.toolbar.height() - 4
