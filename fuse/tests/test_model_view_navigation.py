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




def test_model_view_zoom_is_capped_at_200_percent(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    view.set_zoom_percent(400.0)

    assert view.zoom_percent == 200.0
    assert view.nearest_zoom_level(1) == 200.0
    assert view.toolbar.zoom_selector.findText("400%") == -1


def test_model_view_anchor_zoom_keeps_cursor_scene_position_stable(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)
    view.centerOn(900.0, 600.0)

    cursor_position = QPoint(610, 430)
    scene_before = view.mapToScene(cursor_position)

    view.set_zoom_percent(200.0, cursor_position)

    scene_after = view.mapToScene(cursor_position)
    assert abs(scene_after.x() - scene_before.x()) <= 1.0
    assert abs(scene_after.y() - scene_before.y()) <= 1.0



def test_model_view_grid_matches_component_box_size(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    assert view.GRID_CELL_WIDTH == float(ComponentNodeItem.WIDTH)
    assert view.GRID_CELL_HEIGHT == float(ComponentNodeItem.HEIGHT)
    assert scene.snap_grid_width == float(ComponentNodeItem.WIDTH)
    assert scene.snap_grid_height == float(ComponentNodeItem.HEIGHT)


def test_model_view_snap_to_grid_toggle_updates_scene_toolbar_and_state(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    view.set_snap_to_grid(True)

    assert view.snap_to_grid_enabled is True
    assert scene.snap_to_grid_enabled is True
    assert view.toolbar.snap_to_grid_button.isChecked() is True
    assert view.editor_state()["snapToGrid"] is True

    view.set_snap_to_grid(False)

    assert view.snap_to_grid_enabled is False
    assert scene.snap_to_grid_enabled is False
    assert view.toolbar.snap_to_grid_button.isChecked() is False


def test_model_view_snap_to_grid_state_restores(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.set_snap_to_grid(True)

    restored = ModelView(scene)
    qtbot.addWidget(restored)
    restored.apply_editor_state(view.editor_state())

    assert restored.snap_to_grid_enabled is True
    assert scene.snap_to_grid_enabled is True
    assert restored.toolbar.snap_to_grid_button.isChecked() is True


def test_model_view_snap_to_grid_snaps_new_and_moved_components(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.set_snap_to_grid(True)

    node = scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="a", element="test", name="CPU"),
        QPointF(91.0, 88.0),
    )

    assert node.pos() == QPointF(view.GRID_CELL_WIDTH, view.GRID_CELL_HEIGHT)

    node.setPos(QPointF(275.0, 260.0))

    assert node.pos() == QPointF(view.GRID_CELL_WIDTH * 2.0, view.GRID_CELL_HEIGHT * 2.0)


def test_model_view_snap_to_grid_allows_free_drag_and_snaps_on_release(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.set_snap_to_grid(True)

    node = scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="a", element="test", name="CPU"),
        QPointF(91.0, 88.0),
    )

    scene.begin_node_drag()
    unsnapped_drag_position = QPointF(275.0, 260.0)
    node.setPos(unsnapped_drag_position)

    assert node.pos() == unsnapped_drag_position

    scene.end_node_drag(node)

    assert node.pos() == QPointF(view.GRID_CELL_WIDTH * 2.0, view.GRID_CELL_HEIGHT * 2.0)


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

    # The toolbar may be wider than small/offscreen test viewports now that
    # composite-edit tools are available. Clamp the persisted toolbar anchor
    # point to the viewport instead of requiring the entire toolbar rectangle to
    # fit.
    assert view.toolbar.pos().x() <= view.viewport().width() - 4
    assert view.toolbar.pos().y() <= view.viewport().height() - 4


def test_model_view_toolbar_restores_natural_width_after_resize(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)

    natural_width = view.toolbar.sizeHint().width()
    assert view.toolbar.width() >= natural_width

    view.resize(90, 120)
    qtbot.wait(20)
    view.resize(800, 600)
    qtbot.wait(20)
    view.set_toolbar_position(12, 12)

    assert view.toolbar.width() >= natural_width
