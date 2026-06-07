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
"""Graphics view and toolbar behavior for the FUSE model canvas.

The scene owns model items; this module owns how the user views and navigates
them. ``ModelView`` provides zooming, panning, drag-and-drop component creation,
grid drawing, persisted editor viewport state, and a small floating toolbar for
interaction modes. It intentionally delegates model mutations to ``ModelScene``
so that view code stays focused on input interpretation and presentation.
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, QRectF
from PySide6.QtGui import QAction, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsView,
    QHBoxLayout,
    QSizePolicy,
    QToolButton,
)

from fuse.core.model.models import ComponentDefinition, MIME_COMPONENT
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.selection_helpers import update_selection_dependent_highlights


class FloatingModelToolbar(QFrame):
    """Floating control strip for canvas interaction modes and zoom.

    The toolbar is parented to the view viewport so it moves with the editor
    surface rather than with model contents. It exposes common canvas commands
    such as select/move, multiselect, composite port exposure mode, zoom, and
    undo/redo hooks.
    """
    def __init__(self, view: "ModelView"):
        super().__init__(view.viewport())
        self.view = view
        self.drag_start_position: QPoint | None = None
        self.drag_origin: QPoint | None = None

        self.setObjectName("floatingModelToolbar")
        self.setFrameShape(QFrame.StyledPanel)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.setStyleSheet(
            """
            QFrame#floatingModelToolbar {
                background: rgba(248, 250, 252, 230);
                border: 1px solid #cbd5e1;
                border-radius: 6px;
            }
            QToolButton {
                min-width: 28px;
                min-height: 24px;
                padding: 2px 6px;
            }
            QToolButton:checked {
                background: #dbeafe;
                border: 1px solid #60a5fa;
                border-radius: 4px;
            }
            QComboBox {
                min-width: 84px;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        self.select_button = self.make_button("Select/Move", checkable=True)
        self.select_button.setChecked(True)
        self.select_button.clicked.connect(view.enable_select_move_mode)
        layout.addWidget(self.select_button)

        self.multiselect_button = self.make_button("Multiselect", checkable=True)
        self.multiselect_button.clicked.connect(view.enable_multiselect_mode)
        layout.addWidget(self.multiselect_button)

        self.expose_ports_button = self.make_button("Expose Ports", checkable=True)
        self.expose_ports_button.setToolTip("Toggle whether internal ports are exposed on the composite boundary")
        self.expose_ports_button.clicked.connect(view.enable_composite_port_exposure_mode)
        self.expose_ports_button.setEnabled(False)
        layout.addWidget(self.expose_ports_button)

        layout.addWidget(self.make_separator())

        self.undo_button = self.make_button("Undo")
        self.undo_button.clicked.connect(view.request_undo)
        layout.addWidget(self.undo_button)

        self.redo_button = self.make_button("Redo")
        self.redo_button.clicked.connect(view.request_redo)
        layout.addWidget(self.redo_button)

        layout.addWidget(self.make_separator())

        self.zoom_selector = QComboBox(self)
        self.zoom_selector.addItems(["12.5%", "25%", "50%", "100%", "200%"])
        self.zoom_selector.setEditable(True)
        self.zoom_selector.setCurrentText("100%")
        self.zoom_selector.currentTextChanged.connect(self.on_zoom_text_changed)
        layout.addWidget(self.zoom_selector)

        self.zoom_in_button = self.make_button("Zoom In")
        self.zoom_in_button.clicked.connect(view.zoom_in)
        layout.addWidget(self.zoom_in_button)

        self.zoom_out_button = self.make_button("Zoom Out")
        self.zoom_out_button.clicked.connect(view.zoom_out)
        layout.addWidget(self.zoom_out_button)

        self.adjustSize()

    def make_button(self, text: str, checkable: bool = False) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(text)
        button.setCheckable(checkable)
        return button

    def make_separator(self) -> QFrame:
        separator = QFrame(self)
        separator.setFrameShape(QFrame.VLine)
        separator.setFrameShadow(QFrame.Sunken)
        return separator

    def on_zoom_text_changed(self, text: str) -> None:
        try:
            percent = float(text.replace("%", "").strip())
        except ValueError:
            return
        self.view.set_zoom_percent(percent)

    def set_zoom_percent(self, percent: float) -> None:
        text = f"{percent:g}%"
        index = self.zoom_selector.findText(text)
        self.zoom_selector.blockSignals(True)
        if index >= 0:
            self.zoom_selector.setCurrentIndex(index)
        else:
            self.zoom_selector.setEditText(text)
        self.zoom_selector.blockSignals(False)

    def set_mode(self, mode: str) -> None:
        self.select_button.blockSignals(True)
        self.multiselect_button.blockSignals(True)
        self.expose_ports_button.blockSignals(True)
        self.select_button.setChecked(mode == "select")
        self.multiselect_button.setChecked(mode == "multiselect")
        self.expose_ports_button.setChecked(mode == "expose_ports")
        self.select_button.blockSignals(False)
        self.multiselect_button.blockSignals(False)
        self.expose_ports_button.blockSignals(False)

    def set_port_exposure_tools_available(self, available: bool) -> None:
        self.expose_ports_button.setEnabled(bool(available))
        if not available and self.expose_ports_button.isChecked():
            self.view.enable_select_move_mode()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_start_position = event.globalPosition().toPoint()
            self.drag_origin = self.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_start_position is not None and self.drag_origin is not None:
            delta = event.globalPosition().toPoint() - self.drag_start_position
            next_position = self.drag_origin + delta
            self.view.set_toolbar_position(next_position.x(), next_position.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        moved = self.drag_start_position is not None
        self.drag_start_position = None
        self.drag_origin = None
        if moved:
            self.view.notify_editor_state_changed()
        super().mouseReleaseEvent(event)


class ModelView(QGraphicsView):
    """Qt graphics view used to display and navigate a ``ModelScene``.

    ``ModelView`` translates viewport input into editor commands. It handles
    wheel zoom, middle-button panning, rubber-band/multiselect behavior,
    drop-to-create-component interactions, and persistence of the viewport
    center/zoom/toolbar position in project files.
    """
    ZOOM_LEVELS = [12.5, 25.0, 50.0, 100.0, 200.0]
    GRID_SPACING = 200.0

    def __init__(self, scene: ModelScene):
        super().__init__(scene)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setSceneRect(QRectF(-5000.0, -5000.0, 10000.0, 10000.0))

        self.mode = "select"
        self.zoom_percent = 100.0
        self.undo_callback = None
        self.redo_callback = None
        self.is_panning = False
        self.pan_start_position = QPoint()
        self.pan_start_h_value = 0
        self.pan_start_v_value = 0

        self.toolbar = FloatingModelToolbar(self)
        self.toolbar.move(12, 12)
        self.toolbar.show()
        self.editor_state_changed_callback = None
        scene.selectionChanged.connect(self.update_selection_highlights)

        self.zoom_in_action = QAction("Zoom In", self)
        self.zoom_in_action.setShortcuts([QKeySequence.ZoomIn, QKeySequence("Shift++"), QKeySequence("Ctrl++")])
        self.zoom_in_action.triggered.connect(self.zoom_in)
        self.addAction(self.zoom_in_action)

        self.zoom_out_action = QAction("Zoom Out", self)
        self.zoom_out_action.setShortcuts([QKeySequence.ZoomOut, QKeySequence("Shift+-"), QKeySequence("Ctrl+-")])
        self.zoom_out_action.triggered.connect(self.zoom_out)
        self.addAction(self.zoom_out_action)


    def update_selection_highlights(self) -> None:
        scene = self.scene()
        update_selection_dependent_highlights(
            scene,
            getattr(scene, "selection_changed_callback", None),
            getattr(scene, "properties_panel", None),
        )

    def notify_editor_state_changed(self) -> None:
        if self.editor_state_changed_callback is not None:
            self.editor_state_changed_callback(self.editor_state())

    def editor_state(self) -> dict:
        center = self.mapToScene(self.viewport().rect().center())
        # QGraphicsView centers through integer scroll bars. Keeping persisted
        # centers on integer scene coordinates avoids half-pixel round-trip drift
        # in saved files and undo/redo history snapshots.
        return {
            "viewCenter": {"x": round(center.x()), "y": round(center.y())},
            "zoomPercent": self.zoom_percent,
            "mode": self.mode,
            "toolbarPosition": {
                "x": self.toolbar.pos().x(),
                "y": self.toolbar.pos().y(),
            },
        }

    def apply_editor_state(self, editor: dict | None) -> None:
        editor = editor or {}

        zoom_percent = editor.get("zoomPercent", editor.get("zoom_percent", 100.0))
        try:
            self.set_zoom_percent(float(zoom_percent))
        except (TypeError, ValueError):
            self.set_zoom_percent(100.0)

        mode = str(editor.get("mode", "select") or "select")
        if mode == "multiselect":
            self.enable_multiselect_mode()
        elif mode == "expose_ports" and self.port_exposure_tools_available():
            self.enable_composite_port_exposure_mode()
        else:
            self.enable_select_move_mode()

        position = editor.get("toolbarPosition", editor.get("toolbar_position", {})) or {}
        try:
            self.set_toolbar_position(int(position.get("x", 12)), int(position.get("y", 12)))
        except (TypeError, ValueError):
            self.set_toolbar_position(12, 12)

        center = editor.get("viewCenter", editor.get("view_center", {})) or {}
        try:
            if "x" in center and "y" in center:
                self.centerOn(float(center["x"]), float(center["y"]))
        except (TypeError, ValueError):
            pass

    def set_toolbar_position(self, x: int, y: int) -> None:
        margin = 4
        available_width = max(1, self.viewport().width() - (margin * 2))
        available_height = max(1, self.viewport().height() - (margin * 2))

        if self.toolbar.maximumWidth() != available_width:
            self.toolbar.setMaximumWidth(available_width)
        if self.toolbar.maximumHeight() != available_height:
            self.toolbar.setMaximumHeight(available_height)

        # Clamp the toolbar anchor point to the viewport rather than requiring
        # the full toolbar rectangle to fit. Composite-edit tools can make the
        # toolbar wider than small/offscreen test viewports, and persisted
        # anchor positions should still round-trip in that case.
        max_x = max(margin, self.viewport().width() - margin)
        max_y = max(margin, self.viewport().height() - margin)
        self.toolbar.move(max(margin, min(int(x), max_x)), max(margin, min(int(y), max_y)))
        self.toolbar.raise_()


    def itemAt(self, *args):
        item = super().itemAt(*args)

        position = None
        if len(args) == 1 and isinstance(args[0], QPoint):
            position = args[0]
        elif len(args) >= 2:
            position = QPoint(int(args[0]), int(args[1]))

        if position is None:
            return item

        from fuse.core.ui.graphics_items import ConnectionItem, PortItem

        if isinstance(item, PortItem):
            return item

        if item is not None and not isinstance(item, ConnectionItem):
            return item

        scene = self.scene()
        if scene is None:
            return item

        scene_point = self.mapToScene(position)
        view_scale = max(abs(self.transform().m11()), 0.001)
        search_radius = max(PortItem.RADIUS + 3.0, 10.0 / view_scale)
        search_rect = QRectF(
            scene_point.x() - search_radius,
            scene_point.y() - search_radius,
            search_radius * 2.0,
            search_radius * 2.0,
        )

        for candidate in scene.items(search_rect):
            if not isinstance(candidate, PortItem):
                continue
            center = candidate.scene_center()
            dx = center.x() - scene_point.x()
            dy = center.y() - scene_point.y()
            if dx * dx + dy * dy <= search_radius * search_radius:
                return candidate

        return item

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_toolbar_position(self.toolbar.pos().x(), self.toolbar.pos().y())

    def request_undo(self) -> None:
        if self.undo_callback is not None:
            self.undo_callback()

    def request_redo(self) -> None:
        if self.redo_callback is not None:
            self.redo_callback()

    def set_port_exposure_tools_available(self, available: bool) -> None:
        self.toolbar.set_port_exposure_tools_available(bool(available))

    def port_exposure_tools_available(self) -> bool:
        return bool(self.toolbar.expose_ports_button.isEnabled())

    def set_scene_port_exposure_mode(self, enabled: bool) -> None:
        scene = self.scene()
        if scene is not None:
            scene.composite_port_exposure_mode = bool(enabled)

    def enable_select_move_mode(self) -> None:
        self.mode = "select"
        self.setDragMode(QGraphicsView.NoDrag)
        self.set_scene_port_exposure_mode(False)
        self.toolbar.set_mode(self.mode)
        self.notify_editor_state_changed()

    def enable_multiselect_mode(self) -> None:
        self.mode = "multiselect"
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.set_scene_port_exposure_mode(False)
        self.toolbar.set_mode(self.mode)
        self.notify_editor_state_changed()

    def enable_composite_port_exposure_mode(self) -> None:
        if not self.port_exposure_tools_available():
            self.enable_select_move_mode()
            return
        self.mode = "expose_ports"
        self.setDragMode(QGraphicsView.NoDrag)
        self.set_scene_port_exposure_mode(True)
        self.toolbar.set_mode(self.mode)
        self.notify_editor_state_changed()

    def nearest_zoom_level(self, direction: int) -> float:
        levels = self.ZOOM_LEVELS
        current = self.zoom_percent
        if direction > 0:
            for level in levels:
                if level > current + 0.001:
                    return level
            return levels[-1]
        for level in reversed(levels):
            if level < current - 0.001:
                return level
        return levels[0]

    def zoom_in(self) -> None:
        self.set_zoom_percent(self.nearest_zoom_level(1))

    def zoom_out(self) -> None:
        self.set_zoom_percent(self.nearest_zoom_level(-1))

    def set_zoom_percent(self, percent: float, anchor_view_position: QPoint | None = None) -> None:
        bounded = max(self.ZOOM_LEVELS[0], min(self.ZOOM_LEVELS[-1], float(percent)))
        if anchor_view_position is not None:
            anchor_scene_position = self.mapToScene(anchor_view_position)
        else:
            anchor_scene_position = None

        self.zoom_percent = bounded
        scale_factor = bounded / 100.0
        self.resetTransform()
        self.scale(scale_factor, scale_factor)

        if anchor_view_position is not None and anchor_scene_position is not None:
            shifted_anchor = self.mapFromScene(anchor_scene_position)
            delta = shifted_anchor - anchor_view_position
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() + delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() + delta.y())

        self.toolbar.set_zoom_percent(bounded)
        self.notify_editor_state_changed()

    def wheelEvent(self, event):
        anchor_position = event.position().toPoint()
        if event.angleDelta().y() > 0:
            self.set_zoom_percent(self.nearest_zoom_level(1), anchor_position)
        elif event.angleDelta().y() < 0:
            self.set_zoom_percent(self.nearest_zoom_level(-1), anchor_position)
        event.accept()

    def mousePressEvent(self, event):
        if (
            self.mode == "select"
            and event.button() == Qt.LeftButton
            and self.itemAt(event.position().toPoint()) is None
        ):
            self.is_panning = True
            self.pan_start_position = event.position().toPoint()
            self.pan_start_h_value = self.horizontalScrollBar().value()
            self.pan_start_v_value = self.verticalScrollBar().value()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.is_panning:
            delta = event.position().toPoint() - self.pan_start_position
            self.horizontalScrollBar().setValue(self.pan_start_h_value - delta.x())
            self.verticalScrollBar().setValue(self.pan_start_v_value - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.is_panning and event.button() == Qt.LeftButton:
            self.is_panning = False
            self.unsetCursor()
            self.notify_editor_state_changed()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def drawBackground(self, painter: QPainter, rect):
        super().drawBackground(painter, rect)
        grid_spacing = self.GRID_SPACING
        left = int(rect.left() // grid_spacing) * grid_spacing
        top = int(rect.top() // grid_spacing) * grid_spacing

        pen = QPen(Qt.lightGray)
        pen.setWidthF(0.0)
        painter.setPen(pen)

        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid_spacing

        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid_spacing

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_COMPONENT):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_COMPONENT):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_COMPONENT):
            super().dropEvent(event)
            return

        raw = bytes(event.mimeData().data(MIME_COMPONENT)).decode("utf-8")
        component = ComponentDefinition.from_drag_text(raw)

        scene_pos = self.mapToScene(event.position().toPoint())
        scene = self.scene()

        if hasattr(scene, "create_component_node"):
            scene.create_component_node(component, scene_pos)
        else:
            from fuse.core.ui.graphics_items import ComponentNodeItem

            node = ComponentNodeItem(component)
            node.setPos(scene_pos)
            scene.addItem(node)

        event.acceptProposedAction()
