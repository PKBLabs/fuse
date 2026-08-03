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
"""Qt graphics items used by the FUSE canvas.

This module contains the visual primitives that appear in a ``ModelScene``:
component nodes, ports, port-to-port links, subcomponent connectors,
subcomponent attachments, and helper controls. These classes are responsible
for rendering, hit testing, context menus, and local visual state. They should
not perform project-level persistence or simulator-specific export logic.

Most items keep a reference to the corresponding model dataclass so UI updates,
validation highlights, and serializers can stay synchronized.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPolygonItem,
    QGraphicsPathItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
    QMessageBox,
    QMenu,
    QStyle,
    QStyleOptionGraphicsItem,
)

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.core.model.port_templates import expand_parametric_port_template
from fuse.core.model.name_generation import (
    has_name_index_token,
    render_name_template,
    template_for_source_name,
)
from fuse.core.persistence.db_access import (
    load_port_metadata_for_component,
    load_port_names_for_component,
    load_subcomp_connector_metadata_for_component,
)
from fuse.core.resource_paths import resolve_icon_path
from fuse.core.routing.routing import (
    RoutingConfig,
    route_length,
    route_orthogonal_path,
    segment_intersects_rect,
    simplify_points,
)


VALID_PORT_SIDES = {"left", "right", "top", "bottom"}

# QPixmap loading/scaling is a GUI-thread operation and can be surprisingly
# costly when opening large models with many repeated component types. Cache the
# scaled icon by resolved path and size for the lifetime of the application.
_SCALED_ICON_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def _safe_int(value, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class PortItem(QGraphicsEllipseItem):
    """Visual endpoint for a component port.

    A port item renders the small connection handle on a component boundary,
    tracks its side/position, and delegates click handling to ``ModelScene``.
    Ports may represent fixed metadata-defined ports, expanded members of a
    variable port group, or exposed composite boundary ports.
    """
    RADIUS = 5.0
    HIT_RADIUS = 10.0
    EDGE_GAP = 4.0
    LABEL_GAP = 8.0
    LABEL_SCALE = 1.0

    def __init__(
            self,
            node: "ComponentNodeItem",
            name: str,
            x: float,
            y: float,
            side: str = "right",
            metadata: dict | None = None,
    ):
        super().__init__(
            -self.RADIUS,
            -self.RADIUS,
            self.RADIUS * 2.0,
            self.RADIUS * 2.0,
            node,
        )

        self.node = node
        self.name = name
        self.side = side if side in VALID_PORT_SIDES else "right"
        self.metadata = metadata or {}
        self.interface = (
                self.metadata.get("iface", "")
                or self.metadata.get("interface", "")
                or ""
        )
        self.connections: list[ConnectionItem] = []
        self.is_composite_exposed_port = False
        self.is_deprecated_connector = False

        self.default_port_brush = QBrush(QColor("#2f80ed"))
        self.default_port_pen = QPen(QColor("#1f4e79"), 1)
        self.composite_port_brush = QBrush(QColor("#f97316"))
        self.composite_port_pen = QPen(QColor("#c2410c"), 2)
        self.deprecated_port_brush = QBrush(QColor("#f97316"))
        self.deprecated_port_pen = QPen(QColor("#9a3412"), 2.2)
        self.connected_port_brush = QBrush(QColor("#6b7280"))
        self.connected_port_pen = QPen(QColor("#4b5563"), 1.2)

        self.setPos(x, y)
        self.setBrush(self.default_port_brush)
        self.setPen(self.default_port_pen)
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        tooltip = f"Port: {name}"
        if self.interface:
            tooltip += f"\nInterface: {self.interface}"
        self.setToolTip(tooltip)
        self.setZValue(30)

        self.label = QGraphicsTextItem(name, node)
        self.default_label_color = QColor("#333333")
        self.deprecated_label_color = QColor("#9a3412")
        self.label.setDefaultTextColor(self.default_label_color)
        self.label.setScale(self.LABEL_SCALE)
        self.label.setZValue(31)

        self.update_label_position()

    def set_name(self, name: str):
        """Update this port's canonical name and visible label."""

        self.name = str(name)
        self.label.setPlainText(self.name)
        self.update_connection_state()
        self.update_label_position()

    def set_layout_position(self, x: float, y: float, side: str):
        self.side = side if side in VALID_PORT_SIDES else "right"
        self.setPos(x, y)
        self.update_label_position()

    def update_label_position(self):
        """
        Place the label outside the component body.

        Left/right labels are horizontal. Top/bottom labels are rotated so
        labels do not run into each other when many ports are placed along an
        edge.
        """
        x = self.pos().x()
        y = self.pos().y()
        label_rect = self.label.boundingRect()
        text_width = label_rect.width() * self.LABEL_SCALE
        text_height = label_rect.height() * self.LABEL_SCALE

        gap = self.RADIUS + self.LABEL_GAP

        self.label.setRotation(0)

        if self.side == "left":
            self.label.setRotation(0)
            self.label.setPos(x - gap - text_width, y - text_height / 2.0)
            return

        if self.side == "right":
            self.label.setRotation(0)
            self.label.setPos(x + gap, y - text_height / 2.0)
            return

        if self.side == "top":
            self.label.setRotation(-90)
            self.label.setPos(x - text_height / 2.0, y - gap)
            return

        if self.side == "bottom":
            self.label.setRotation(90)
            self.label.setPos(x + text_height / 2.0, y + gap)
            return

    def scene_center(self) -> QPointF:
        return self.mapToScene(self.boundingRect().center())

    def shape(self) -> QPainterPath:
        """Return a forgiving hit target without changing the visible port size."""
        path = QPainterPath()
        path.addEllipse(
            -self.HIT_RADIUS,
            -self.HIT_RADIUS,
            self.HIT_RADIUS * 2.0,
            self.HIT_RADIUS * 2.0,
        )
        return path

    def contains(self, point) -> bool:
        return self.shape().contains(point)

    def is_connected(self) -> bool:
        """Each SST port may participate in at most one link."""
        return len(self.connections) > 0

    def apply_visual_state(self):
        """Apply the base port glyph colors for normal, deprecated, and occupied states."""
        if self.is_connected():
            self.setBrush(self.connected_port_brush)
            if self.is_deprecated_connector:
                self.setPen(self.deprecated_port_pen)
                self.label.setDefaultTextColor(self.deprecated_label_color)
            else:
                self.setPen(self.connected_port_pen)
                self.label.setDefaultTextColor(self.default_label_color)
            return

        if self.is_deprecated_connector:
            self.setBrush(self.deprecated_port_brush)
            self.setPen(self.deprecated_port_pen)
            self.label.setDefaultTextColor(self.deprecated_label_color)
            return

        if bool(getattr(self, "is_composite_exposed_port", False)):
            self.setBrush(self.composite_port_brush)
            self.setPen(self.composite_port_pen)
        else:
            self.setBrush(self.default_port_brush)
            self.setPen(self.default_port_pen)

        self.label.setDefaultTextColor(self.default_label_color)

    def set_deprecated_visual_state(self, deprecated: bool):
        """Style a visible port as deprecated without changing its name."""
        self.is_deprecated_connector = bool(deprecated)
        self.apply_visual_state()

    def update_connection_state(self):
        self.apply_visual_state()

        if self.is_connected():
            self.setToolTip(f"⚠ Port Occupied\n{self.name}")
        else:
            tooltip = f"Port: {self.name}"
            if self.interface:
                tooltip += f"\nInterface: {self.interface}"
            if bool(getattr(self, "is_composite_exposed_port", False)):
                tooltip += "\nExposed on composite boundary"
            self.setToolTip(tooltip)

        # If a hidden advanced/raw SST port becomes connected while a project is
        # loading or a user creates a raw-port link in advanced mode, reveal and
        # relayout it so existing models remain visible/editable.
        if self.is_connected() and hasattr(self.node, "apply_port_visibility"):
            try:
                self.node.apply_port_visibility()
            except Exception:
                pass

    def contextMenuEvent(self, event):
        scene = self.scene()
        node = self.node
        variable_base_name = node.variable_port_family_for_port(self.name)
        has_composite_menu = (
            scene is not None
            and hasattr(scene, "composite_port_exposure_requested_callback")
        )

        if variable_base_name is None and not has_composite_menu:
            super().contextMenuEvent(event)
            return

        if scene is not None:
            if hasattr(scene, "cancel_pending_connection"):
                scene.cancel_pending_connection()
            if hasattr(scene, "cancel_pending_subcomp_attachment"):
                scene.cancel_pending_subcomp_attachment()

        menu = QMenu()
        remove_port_action = None
        exposure_action = None
        is_exposed = False

        if variable_base_name is not None:
            remove_port_action = menu.addAction("Remove Port")

        if has_composite_menu:
            if remove_port_action is not None:
                menu.addSeparator()

            state_callback = getattr(scene, "composite_port_exposure_state_callback", None)
            if state_callback is not None:
                is_exposed = bool(state_callback(self))

            action_text = "Hide Port from Composite" if is_exposed else "Expose Port on Composite"
            exposure_action = menu.addAction(action_text)
            if not is_exposed and self.is_connected():
                exposure_action.setEnabled(False)
                exposure_action.setToolTip("Only unlinked internal ports can be exposed.")

        action = menu.exec(event.screenPos())

        if remove_port_action is not None and action == remove_port_action:
            node.remove_variable_port(
                variable_base_name,
                port_name=self.name,
                confirm=True,
            )
            if scene is not None and hasattr(scene, "cancel_pending_connection"):
                scene.cancel_pending_connection()

        elif exposure_action is not None and action == exposure_action:
            callback = getattr(scene, "composite_port_exposure_requested_callback", None)
            if callback is not None:
                callback(self, not is_exposed)
            if scene is not None and hasattr(scene, "cancel_pending_connection"):
                scene.cancel_pending_connection()

        event.accept()

    def mousePressEvent(self, event):
        scene = self.scene()
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return

        if (
            scene is not None
            and bool(getattr(scene, "composite_port_exposure_mode", False))
            and hasattr(scene, "composite_port_exposure_requested_callback")
        ):
            state_callback = getattr(scene, "composite_port_exposure_state_callback", None)
            is_exposed = bool(state_callback(self)) if state_callback is not None else False
            callback = getattr(scene, "composite_port_exposure_requested_callback", None)
            if callback is not None:
                callback(self, not is_exposed)
            event.accept()
            return

        if scene is not None and hasattr(scene, "port_clicked"):
            scene.port_clicked(self)
        event.accept()

    def set_compatibility_highlight(self, state: str = ""):
        if self.is_connected():
            self.update_connection_state()
            return

        if state == "compatible":
            self.setBrush(QBrush(QColor("#22c55e")))
            self.setPen(QPen(QColor("#15803d"), 2))
        elif state == "warning":
            self.setBrush(QBrush(QColor("#f59e0b")))
            self.setPen(QPen(QColor("#b45309"), 2))
        elif state == "incompatible":
            self.setBrush(QBrush(QColor("#ef4444")))
            self.setPen(QPen(QColor("#b91c1c"), 2))
        else:
            self.setPen(QPen(QColor("#1f4e79"), 1))
            self.update_connection_state()


class ConnectionItem(QGraphicsPathItem):
    """
    Visual rendering of one SST ModelLink.

    This class handles Qt graphics behavior(s):
    - color / highlighting
    - tooltip
    - selecting the link
    - asking routing.py for a path
    - converting route points into a QPainterPath

    The actual link pathfinding/routing logic is in routing.py.
    """

    ROUTE_CLEARANCE = 24
    EXIT_MARGIN = 12
    LANE_SPACING = 12
    SELECTION_TOLERANCE = 10.0

    # Keep routed links behind component bodies. Long routed paths often cross
    # through a component while the async router is still catching up; if links
    # sit above nodes, Qt hit testing can spend a long time checking stroked
    # link shapes before the node receives the click.
    NORMAL_Z = -10.0
    VALIDATION_Z = -8.0
    HIGHLIGHT_Z = 8.0

    def __init__(
        self,
        link: ModelLink,
        source_port: PortItem,
        target_port: PortItem,
        *,
        update_immediately: bool = True,
    ):
        super().__init__()
        self.link = link
        self.source_port = source_port
        self.target_port = target_port
        self.route_points: list[QPointF] = []
        self._shape_cache: QPainterPath | None = None
        self._highlighted = False

        self.base_color = QColor("#38bdf8")
        self.highlight_color = QColor("#2563eb")
        self.warning_color = QColor("#f59e0b")
        self.error_color = QColor("#ef4444")
        self.validation_messages: list[str] = []

        self.setPen(QPen(self.base_color, 2))
        self.setZValue(self.NORMAL_Z)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        self.update_tooltip()

        source_port.connections.append(self)
        target_port.connections.append(self)
        source_port.update_connection_state()
        target_port.update_connection_state()

        if update_immediately:
            self.update_position()

    def invalidate_shape_cache(self) -> None:
        self._shape_cache = None

    def setPath(self, path):  # noqa: N802 - Qt override name
        self.invalidate_shape_cache()
        super().setPath(path)

    def setPen(self, pen):  # noqa: N802 - Qt override name
        self.invalidate_shape_cache()
        super().setPen(pen)

    def contextMenuEvent(self, event):
        scene = self.scene()

        menu = QMenu()
        composite_action = None
        if scene is not None:
            from fuse.core.ui.selection_helpers import is_internal_selected_connection

            if is_internal_selected_connection(scene, self):
                composite_action = menu.addAction("Create Composite Component from Selection")
                menu.addSeparator()
        remove_action = menu.addAction("Remove Link")

        action = menu.exec(event.screenPos())

        if composite_action is not None and action == composite_action:
            if scene is not None:
                from fuse.core.ui.selection_helpers import request_composite_from_selection

                request_composite_from_selection(
                    scene,
                    getattr(scene, "composite_creation_requested_callback", None),
                )

        elif action == remove_action:
            if scene is not None and hasattr(scene, "delete_link"):
                scene.delete_link(self)

        event.accept()

    def update_tooltip(self):
        tooltip = (
            f"{self.link.name}\n"
            f"{self.link.source_component_name}.{self.link.source_port} -> "
            f"{self.link.target_component_name}.{self.link.target_port}\n"
            f"source latency: {self.link.source_latency}\n"
            f"target latency: {self.link.target_latency}"
        )

        if getattr(self.link, "compatibility_severity", "ok") != "ok":
            tooltip += f"\n\n⚠ {self.link.compatibility_message}"

        if self.validation_messages:
            tooltip += "\n\nValidation:\n" + "\n".join(self.validation_messages)

        self.setToolTip(tooltip)

    def mousePressEvent(self, event):
        scene = self.scene()

        if scene is not None and hasattr(scene, "select_link"):
            scene.select_link(self)

        super().mousePressEvent(event)

    def node_body_rect(self, node: "ComponentNodeItem"):
        """
        Return only the actual drawn component rectangle in scene coordinates.

        Do not use sceneBoundingRect(), because that includes ports, labels,
        and selection decorations.
        """
        return node.mapRectToScene(node.rect())

    def route_obstacle_rects(self):
        """
        Return padded component rectangles that links should avoid.
        """
        scene = self.scene()

        if scene is None:
            return []

        rects = []
        pad = self.ROUTE_CLEARANCE

        for item in scene.items():
            if isinstance(item, ComponentNodeItem):
                rects.append(
                    self.node_body_rect(item).adjusted(
                        -pad,
                        -pad,
                        pad,
                        pad,
                    )
                )

        return rects

    def port_side(self, port: PortItem) -> str:
        explicit_side = getattr(port, "side", "")
        if explicit_side in VALID_PORT_SIDES:
            return explicit_side

        center = port.scene_center()
        rect = self.node_body_rect(port.node)

        distances = {
            "left": abs(center.x() - rect.left()),
            "right": abs(center.x() - rect.right()),
            "top": abs(center.y() - rect.top()),
            "bottom": abs(center.y() - rect.bottom()),
        }

        return min(distances, key=distances.get)

    def lane_index(self) -> int:
        """
        Deterministic per-link lane ordering.

        This keeps links from all choosing exactly the same initial offset.
        """
        lanes = [0, 1, -1, 2, -2, 3, -3, 4, -4]
        return lanes[(self.link.link_id - 1) % len(lanes)]

    def outward_lane_distance(self) -> float:
        return abs(self.lane_index()) * self.LANE_SPACING

    def routing_config(self) -> RoutingConfig:
        return RoutingConfig(
            route_clearance=self.ROUTE_CLEARANCE,
            exit_margin=self.EXIT_MARGIN,
            lane_spacing=self.LANE_SPACING,
        )

    def exit_point_for_port(self, port: PortItem) -> QPointF:
        """
        Return a route endpoint safely outside the padded component box.

        The visual path goes:

            port dot -> exit point -> routed path -> exit point -> port dot
        """
        center = port.scene_center()
        side = self.port_side(port)
        body = self.node_body_rect(port.node)

        padded = body.adjusted(
            -self.ROUTE_CLEARANCE,
            -self.ROUTE_CLEARANCE,
            self.ROUTE_CLEARANCE,
            self.ROUTE_CLEARANCE,
        )

        margin = self.EXIT_MARGIN + self.outward_lane_distance()

        if side == "left":
            return QPointF(padded.left() - margin, center.y())

        if side == "right":
            return QPointF(padded.right() + margin, center.y())

        if side == "top":
            return QPointF(center.x(), padded.top() - margin)

        return QPointF(center.x(), padded.bottom() + margin)

    def routed_points(self) -> list[QPointF]:
        source_center = self.source_port.scene_center()
        target_center = self.target_port.scene_center()

        source_exit = self.exit_point_for_port(self.source_port)
        target_exit = self.exit_point_for_port(self.target_port)

        obstacle_rects = self.route_obstacle_rects()

        route = route_orthogonal_path(
            start=source_exit,
            end=target_exit,
            obstacle_rects=obstacle_rects,
            config=self.routing_config(),
            lane_distance=self.outward_lane_distance(),
        )

        return simplify_points([source_center, *route, target_center])

    def build_path_from_points(self, points: list[QPointF]) -> QPainterPath:
        if not points:
            return QPainterPath()

        path = QPainterPath(points[0])

        for point in points[1:]:
            path.lineTo(point)

        return path

    def shape(self) -> QPainterPath:
        """
        Return the actual clickable/selectable shape for this link.

        QGraphicsPathItem can otherwise behave as if a large path area is
        selectable, especially for orthogonal multi-segment routes. Use a stroked
        version of the visible path so the link is only selectable when the pointer
        is on or near the line.
        """
        scene = self.scene()
        if scene is not None and getattr(scene, "_suppress_link_hit_tests", False):
            return QPainterPath()

        if self._shape_cache is None:
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF(), self.SELECTION_TOLERANCE))
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            self._shape_cache = stroker.createStroke(self.path())

        return self._shape_cache

    def contains(self, point) -> bool:
        return self.shape().contains(point)

    def set_route_points_from_tuples(self, points: list[tuple[float, float]]):
        """Apply worker-computed route points on the GUI thread."""
        route_points = [QPointF(float(x), float(y)) for x, y in points]
        self.route_points = route_points
        self.setPath(self.build_path_from_points(route_points))

    def update_position(self):
        points = self.routed_points()
        self.route_points = points
        self.setPath(self.build_path_from_points(points))

    def update_position_fast(self):
        """
        Cheap drag-preview route.

        This is intentionally simpler than the full route. It keeps dragging
        responsive while still leaving each component through the correct side.
        """
        source = self.source_port.scene_center()
        target = self.target_port.scene_center()

        source_exit = self.exit_point_for_port(self.source_port)
        target_exit = self.exit_point_for_port(self.target_port)

        route_a = simplify_points(
            [
                source,
                source_exit,
                QPointF(source_exit.x(), target_exit.y()),
                target_exit,
                target,
            ]
        )

        route_b = simplify_points(
            [
                source,
                source_exit,
                QPointF(target_exit.x(), source_exit.y()),
                target_exit,
                target,
            ]
        )

        points = route_a if route_length(route_a) <= route_length(route_b) else route_b
        self.route_points = points
        self.setPath(self.build_path_from_points(points))

    def clear_route_points(self):
        self.route_points = []

    def is_connected_to_node(self, node: "ComponentNodeItem") -> bool:
        return self.source_port.node is node or self.target_port.node is node

    def link_base_color(self) -> QColor:
        if self.validation_messages:
            return self.error_color
        if getattr(self.link, "compatibility_severity", "ok") == "error":
            return self.error_color
        if getattr(self.link, "compatibility_severity", "ok") == "warning":
            return self.warning_color
        return self.base_color

    def set_validation_warnings(self, messages: list[str]):
        self.validation_messages = list(messages)
        self.update_tooltip()

        if self._highlighted:
            self.setPen(QPen(self.highlight_color, 4))
            self.setZValue(self.HIGHLIGHT_Z)
        elif messages:
            self.setPen(QPen(self.error_color, 3))
            self.setZValue(self.VALIDATION_Z)
        else:
            self.setPen(QPen(self.link_base_color(), 2))
            self.setZValue(self.NORMAL_Z)

    def set_highlighted(self, highlighted: bool):
        highlighted = bool(highlighted)
        if self._highlighted == highlighted:
            return

        self._highlighted = highlighted
        if highlighted:
            self.setPen(QPen(self.highlight_color, 4))
            self.setZValue(self.HIGHLIGHT_Z)
        else:
            self.setPen(QPen(self.link_base_color(), 2))
            self.setZValue(self.VALIDATION_Z if self.validation_messages else self.NORMAL_Z)

    def segment_intersects_rect(self, a: QPointF, b: QPointF, rect) -> bool:
        """
        Compatibility wrapper.

        ModelScene currently calls connection.segment_intersects_rect(...).
        Keep this wrapper so you do not have to change model_scene.py yet.
        """
        return segment_intersects_rect(a, b, rect)



class SubcompConnectorItem(QGraphicsPolygonItem):
    """
    Visual endpoint used to attach SST SubComponents to parent slots.

    This is not a normal Link.connect() port. A subcomp_connector creates a
    ModelSubcompAttachment and exports as a native SST subcomponent assignment.
    """

    SIZE = 12.0
    EDGE_GAP = 12.0
    LABEL_GAP = 8.0
    LABEL_SCALE = 0.78

    def __init__(
        self,
        node: "ComponentNodeItem",
        name: str,
        role: str,
        metadata: dict | None = None,
    ):
        half = self.SIZE / 2.0
        polygon = QPolygonF(
            [
                QPointF(0.0, -half),
                QPointF(half, 0.0),
                QPointF(0.0, half),
                QPointF(-half, 0.0),
            ]
        )
        super().__init__(polygon, node)

        self.node = node
        self.name = name
        self.role = role
        self.metadata = metadata or {}

        interface = (
            self.metadata.get("required_interface", "")
            or self.metadata.get("provided_interface", "")
            or self.metadata.get("iface", "")
            or self.metadata.get("interface", "")
            or ""
        )
        self.interface = interface

        self.default_normal_brush = QBrush(QColor("#8b5cf6"))
        self.default_normal_pen = QPen(QColor("#5b21b6"), 1.5)
        self.deprecated_normal_brush = QBrush(QColor("#f97316"))
        self.deprecated_normal_pen = QPen(QColor("#9a3412"), 2.0)
        self.normal_brush = self.default_normal_brush
        self.normal_pen = self.default_normal_pen
        self.is_deprecated_connector = False

        self.compatible_brush = QBrush(QColor("#22c55e"))
        self.compatible_pen = QPen(QColor("#15803d"), 2.0)

        self.warning_brush = QBrush(QColor("#f59e0b"))
        self.warning_pen = QPen(QColor("#b45309"), 2.0)

        self.incompatible_brush = QBrush(QColor("#ef4444"))
        self.incompatible_pen = QPen(QColor("#b91c1c"), 2.0)

        self.setBrush(self.normal_brush)
        self.setPen(self.normal_pen)

        if role == "slot":
            tooltip_title = "SubComponent slot"
        else:
            tooltip_title = "SubComponent connector"

        tooltip = f"{tooltip_title}: {name}"
        if interface:
            tooltip += f"\nInterface: {interface}"
        self.setToolTip(tooltip)
        self.setAcceptHoverEvents(True)
        self.setZValue(12)

        label_text = name if role == "slot" else (interface or name)
        self.label = QGraphicsTextItem(label_text, node)
        self.default_label_color = QColor("#4c1d95")
        self.deprecated_label_color = QColor("#9a3412")
        self.label.setDefaultTextColor(self.default_label_color)
        self.label.setScale(self.LABEL_SCALE)
        self.label.setZValue(13)

        self.side = "bottom" if role == "slot" else "top"
        self.update_label_position()

    def set_layout_position(self, x: float, y: float, side: str):
        self.side = side if side in VALID_PORT_SIDES else self.side
        self.setPos(x, y)
        self.update_label_position()

    def set_deprecated_visual_state(self, deprecated: bool):
        """Style a visible connector as deprecated without changing its name."""
        self.is_deprecated_connector = bool(deprecated)
        if self.is_deprecated_connector:
            self.normal_brush = self.deprecated_normal_brush
            self.normal_pen = self.deprecated_normal_pen
            self.label.setDefaultTextColor(self.deprecated_label_color)
        else:
            self.normal_brush = self.default_normal_brush
            self.normal_pen = self.default_normal_pen
            self.label.setDefaultTextColor(self.default_label_color)

        self.set_compatibility_highlight("")

    def update_label_position(self):
        x = self.pos().x()
        y = self.pos().y()
        rect = self.label.boundingRect()
        text_width = rect.width() * self.LABEL_SCALE
        text_height = rect.height() * self.LABEL_SCALE
        gap = self.SIZE / 2.0 + self.LABEL_GAP

        self.label.setRotation(0)

        if self.side == "top":
            self.label.setRotation(-90)
            self.label.setPos(x - text_height / 2.0, y - gap)
        elif self.side == "bottom":
            self.label.setRotation(90)
            self.label.setPos(x + text_height / 2.0, y + gap)
        elif self.side == "left":
            self.label.setPos(x - gap - text_width, y - text_height / 2.0)
        else:
            self.label.setPos(x + gap, y - text_height / 2.0)

    def set_compatibility_highlight(self, state: str = ""):
        if state == "compatible":
            self.setBrush(self.compatible_brush)
            self.setPen(self.compatible_pen)
        elif state == "warning":
            self.setBrush(self.warning_brush)
            self.setPen(self.warning_pen)
        elif state == "incompatible":
            self.setBrush(self.incompatible_brush)
            self.setPen(self.incompatible_pen)
        else:
            self.setBrush(self.normal_brush)
            self.setPen(self.normal_pen)

    def scene_center(self) -> QPointF:
        return self.mapToScene(self.boundingRect().center())

    def mousePressEvent(self, event):
        scene = self.scene()
        if scene is not None and hasattr(scene, "subcomp_connector_clicked"):
            scene.subcomp_connector_clicked(self)
        event.accept()


class SubcompAttachmentItem(QGraphicsPathItem):
    """Dashed visual edge representing a SubComponent assignment."""

    NORMAL_Z = -9.0
    VALIDATION_Z = -7.0
    HIGHLIGHT_Z = 8.0
    SELECTION_TOLERANCE = 10.0

    def __init__(
        self,
        attachment: ModelSubcompAttachment,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
        *,
        update_immediately: bool = True,
    ):
        super().__init__()
        self.attachment = attachment
        self.source_connector = slot_connector
        self.target_connector = interface_connector
        self.base_color = QColor("#8b5cf6")
        self.highlight_color = QColor("#f59e0b")
        self.error_color = QColor("#ef4444")
        self.validation_messages: list[str] = []
        self._shape_cache: QPainterPath | None = None
        self._highlighted = False
        self.setPen(QPen(self.base_color, 2, Qt.DashLine))
        self.setZValue(self.NORMAL_Z)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.update_tooltip()
        if update_immediately:
            self.update_position()

    def invalidate_shape_cache(self) -> None:
        self._shape_cache = None

    def setPath(self, path):  # noqa: N802 - Qt override name
        self.invalidate_shape_cache()
        super().setPath(path)

    def setPen(self, pen):  # noqa: N802 - Qt override name
        self.invalidate_shape_cache()
        super().setPen(pen)

    def shape(self) -> QPainterPath:
        scene = self.scene()
        if scene is not None and getattr(scene, "_suppress_link_hit_tests", False):
            return QPainterPath()

        if self._shape_cache is None:
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF(), self.SELECTION_TOLERANCE))
            stroker.setCapStyle(Qt.RoundCap)
            stroker.setJoinStyle(Qt.RoundJoin)
            self._shape_cache = stroker.createStroke(self.path())

        return self._shape_cache

    def contains(self, point) -> bool:
        return self.shape().contains(point)

    def update_tooltip(self):
        tooltip = (
            f"{self.attachment.name}\n"
            f"{self.attachment.parent_component_name}.{self.attachment.slot_name} -> "
            f"{self.attachment.child_component_name}\n"
            f"required: {self.attachment.required_interface or '(unspecified)'}\n"
            f"provided: {self.attachment.provided_interface or '(unspecified)'}"
        )
        if self.attachment.compatibility_severity != "ok":
            tooltip += f"\n\n⚠ {self.attachment.compatibility_message}"
        if self.validation_messages:
            tooltip += "\n\nValidation:\n" + "\n".join(self.validation_messages)
        self.setToolTip(tooltip)

    def update_position(self):
        source = self.source_connector.scene_center()
        target = self.target_connector.scene_center()
        mid_x = (source.x() + target.x()) / 2.0
        path = QPainterPath(source)
        path.cubicTo(
            QPointF(mid_x, source.y()),
            QPointF(mid_x, target.y()),
            target,
        )
        self.setPath(path)

    def mousePressEvent(self, event):
        scene = self.scene()
        if scene is not None and hasattr(scene, "select_subcomp_attachment"):
            scene.select_subcomp_attachment(self)
        super().mousePressEvent(event)

    def is_connected_to_node(self, node: "ComponentNodeItem") -> bool:
        return self.source_connector.node is node or self.target_connector.node is node

    def contextMenuEvent(self, event):
        scene = self.scene()

        menu = QMenu()
        remove_action = menu.addAction("Remove SubComponent Attachment")

        action = menu.exec(event.screenPos())

        if action == remove_action:
            if scene is not None and hasattr(scene, "delete_subcomp_attachment"):
                scene.delete_subcomp_attachment(self)

        event.accept()

    def set_validation_warnings(self, messages: list[str]):
        self.validation_messages = list(messages)
        self.update_tooltip()

        if self._highlighted:
            self.setPen(QPen(self.highlight_color, 4, Qt.DashLine))
            self.setZValue(self.HIGHLIGHT_Z)
        elif messages:
            self.setPen(QPen(self.error_color, 3, Qt.DashLine))
            self.setZValue(self.VALIDATION_Z)
        else:
            self.setPen(QPen(self.base_color, 2, Qt.DashLine))
            self.setZValue(self.NORMAL_Z)

    def set_highlighted(self, highlighted: bool):
        highlighted = bool(highlighted)
        if self._highlighted == highlighted:
            return

        self._highlighted = highlighted
        if highlighted:
            self.setPen(QPen(self.highlight_color, 4, Qt.DashLine))
            self.setZValue(self.HIGHLIGHT_Z)
        else:
            if self.validation_messages:
                self.setPen(QPen(self.error_color, 3, Qt.DashLine))
                self.setZValue(self.VALIDATION_Z)
            else:
                self.setPen(QPen(self.base_color, 2, Qt.DashLine))
                self.setZValue(self.NORMAL_Z)


class AddPortsButtonItem(QGraphicsTextItem):
    """Small canvas control for variable ports and advanced/raw port visibility.

    The button is shown next to components that expose expandable port groups or
    SST ports hidden by the guided view.  Clicking it delegates to the owning
    ``ComponentNodeItem`` so the node can update its visible port list.
    """
    def __init__(self, node: "ComponentNodeItem"):
        super().__init__("+", node)
        self.node = node
        self.setDefaultTextColor(QColor("#2563eb"))
        self.setScale(1.35)
        self.setPos(node.WIDTH - 24, node.HEIGHT - 30)
        self.setZValue(30)
        self.setAcceptHoverEvents(True)
        self.setToolTip("Add Ports / Show Advanced Ports")

    def mousePressEvent(self, event):
        templates = self.node.variable_port_templates
        has_advanced_ports = self.node.has_advanced_or_hidden_ports()

        if not templates and not has_advanced_ports:
            event.accept()
            return

        menu = QMenu()

        for template in templates:
            base_name = template.get("base_name", "") or template.get("name", "")
            add_action = menu.addAction(f"Add {base_name}")
            add_action.triggered.connect(
                lambda checked=False, name=base_name: self.node.increment_variable_port(
                    name
                )
            )

            remove_action = menu.addAction(f"Remove {base_name}")
            remove_action.triggered.connect(
                lambda checked=False, name=base_name: self.node.decrement_variable_port(
                    name
                )
            )

        if has_advanced_ports:
            if templates:
                menu.addSeparator()

            advanced_action = menu.addAction(self.node.advanced_ports_menu_label())
            advanced_action.setToolTip(self.node.advanced_ports_tooltip())
            advanced_action.triggered.connect(
                lambda checked=False: self.node.toggle_advanced_ports()
            )

        menu.exec(QCursor.pos())
        event.accept()


class ComponentNodeItem(QGraphicsRectItem):
    """Canvas representation of a placed model component.

    A node item owns the visible component body, icon, port items,
    subcomponent-connector items, validation styling, and drag behavior for one
    component instance. It mirrors a ``ComponentDefinition`` plus instance state
    such as node id, instance name, position, parameter values, composite
    mappings, and variable port counts.
    """
    WIDTH = 180
    HEIGHT = 170

    TITLE_Y = 8
    TITLE_HEIGHT = 28
    ICON_SIZE = 175
    ICON_Y = 15

    MAX_VERTICAL_PORTS_PER_SIDE = 8
    MAX_HORIZONTAL_PORTS_PER_SIDE = 6
    MIN_PORT_SPACING = 18.0

    _next_node_id = 1

    def __init__(
        self,
        component: ComponentDefinition,
        node_id: Optional[int] = None,
        parameters: Optional[dict] = None,
        instance_name: Optional[str] = None,
        variable_port_counts: Optional[dict[str, int]] = None,
        instance_name_template: Optional[str] = None,
        metadata_cache: Optional[dict[tuple[str, str, str, str], list[dict]]] = None,
    ):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.setZValue(10.0)

        if node_id is None:
            self.node_id = ComponentNodeItem._next_node_id
            ComponentNodeItem._next_node_id += 1
        else:
            self.node_id = node_id
            ComponentNodeItem._next_node_id = max(
                ComponentNodeItem._next_node_id,
                node_id + 1,
            )

        self.component = component
        self._metadata_cache = metadata_cache
        requested_instance_name = instance_name or f"{component.name}_{self.node_id}"
        if instance_name_template:
            self.instance_name_template = str(instance_name_template)
            if instance_name is None or has_name_index_token(str(instance_name)):
                requested_instance_name = render_name_template(self.instance_name_template, 0)
        elif has_name_index_token(str(requested_instance_name)):
            self.instance_name_template = str(requested_instance_name)
            requested_instance_name = render_name_template(self.instance_name_template, 0)
        else:
            self.instance_name_template = template_for_source_name(str(requested_instance_name))
        self.instance_name_value = str(requested_instance_name)
        self.parameters = parameters or {}
        self.variable_port_counts = {
            str(key): max(0, _safe_int(value, 1))
            for key, value in (variable_port_counts or {}).items()
        }
        self.show_advanced_ports = False
        self.show_deprecated_connectors = False
        self.port_templates: list[dict] = []
        self.variable_port_templates: list[dict] = []
        self.subcomp_connector_templates: list[dict] = []
        self.ports: list[PortItem] = []
        self.subcomp_connectors: list[SubcompConnectorItem] = []
        self.add_ports_button: AddPortsButtonItem | None = None
        self.icon_path = component.icon_path or ""
        self.composite_instance_model: dict = {}
        self.composite_port_mappings: list = []

        self.normal_brush = QBrush(QColor("#ffffff"))
        self.selected_brush = QBrush(QColor("#eff6ff"))
        self.normal_pen = QPen(QColor("#cbd5e1"), 1.25)
        self.selected_pen = QPen(QColor("#2563eb"), 2.5)
        self.validation_pen = QPen(QColor("#dc2626"), 2.5)
        self.setBrush(self.normal_brush)
        self.setPen(self.normal_pen)
        self.validation_messages: list[str] = []
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        self.title_item = QGraphicsTextItem(self.instance_name, self)
        self.title_item.setDefaultTextColor(QColor("#111111"))
        self.title_item.setTextWidth(self.WIDTH)
        self.title_item.setDefaultTextColor(QColor("#111111"))
        self.title_item.setPos(0, self.TITLE_Y)

        title_document = self.title_item.document()
        title_document.setDefaultTextOption(title_document.defaultTextOption())
        self.title_item.setHtml(
            f"<div align='center'><b>{self.instance_name}</b></div>"
        )

        self.validation_warning_item = QGraphicsTextItem("⚠", self)
        self.validation_warning_item.setDefaultTextColor(QColor("#f59e0b"))
        self.validation_warning_item.setScale(1.25)
        self.validation_warning_item.setPos(self.WIDTH - 28, 4)
        self.validation_warning_item.setVisible(False)
        self.validation_warning_item.setZValue(20)

        if component.iface:
            iface = QGraphicsTextItem(component.iface, self)
            iface.setDefaultTextColor(QColor("#666666"))
            iface.setTextWidth(self.WIDTH - 20)
            iface.setScale(0.75)
            iface.setPos(10, 54)

        self.add_ports_from_database_or_defaults()
        self.add_subcomp_connectors_from_metadata()

        self.icon_item = None
        self.add_icon()

    @property
    def instance_name(self) -> str:
        return self.instance_name_value

    def set_instance_name(self, new_name: str, name_template: str | None = None):
        if name_template is not None:
            self.instance_name_template = str(name_template)
        self.instance_name_value = new_name
        self.title_item.setHtml(
            f"<div align='center'><b>{new_name}</b></div>"
        )

        for port in self.ports:
            for connection in port.connections:
                if connection.source_port.node is self:
                    connection.link.source_component_name = new_name
                if connection.target_port.node is self:
                    connection.link.target_component_name = new_name
                connection.update_tooltip()

        for connector in self.subcomp_connectors:
            scene = connector.scene()
            if scene is None or not hasattr(scene, "subcomp_attachment_items"):
                continue
            for attachment_item in scene.subcomp_attachment_items():
                attachment = attachment_item.attachment
                if attachment_item.source_connector.node is self:
                    attachment.parent_component_name = new_name
                if attachment_item.target_connector.node is self:
                    attachment.child_component_name = new_name
                attachment_item.update_tooltip()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        paint_option = QStyleOptionGraphicsItem(option)
        paint_option.state &= ~QStyle.State_Selected
        super().paint(painter, paint_option, widget)

    def mouseDoubleClickEvent(self, event):
        component_is_composite = bool(int(getattr(self.component, "is_composite", 0) or 0))
        scene = self.scene()
        if (
            component_is_composite
            and event.button() == Qt.LeftButton
            and scene is not None
            and getattr(scene, "composite_instance_edit_requested_callback", None) is not None
        ):
            scene.composite_instance_edit_requested_callback(self)
            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def update_selection_style(self):
        if self.isSelected():
            self.setBrush(self.selected_brush)
            self.setPen(self.selected_pen)
        elif self.validation_messages:
            self.setBrush(self.normal_brush)
            self.setPen(self.validation_pen)
        else:
            self.setBrush(self.normal_brush)
            self.setPen(self.normal_pen)

    def contextMenuEvent(self, event):
        scene = self.scene()

        if scene is not None and not self.isSelected():
            scene.clearSelection()
            self.setSelected(True)

        menu = QMenu()
        add_action = menu.addAction("Add to Frequently Used")

        copy_action = None
        paste_action = None
        group_action = None
        ungroup_action = None
        composite_action = None
        advanced_ports_action = None
        deprecated_connectors_action = None

        if scene is not None:
            menu.addSeparator()
            copy_action = menu.addAction("Copy")
            paste_action = menu.addAction("Paste")
            paste_action.setEnabled(bool(getattr(scene.__class__, "_entity_clipboard", None)))
            group_action = menu.addAction("Group")
            group_action.setEnabled(len(scene.selected_component_nodes(expand_groups=False)) >= 2)
            ungroup_action = menu.addAction("Ungroup")
            ungroup_action.setEnabled(any(
                node.node_id in getattr(scene, "node_group_ids", {})
                for node in scene.selected_component_nodes(expand_groups=True)
            ))

            from fuse.core.ui.selection_helpers import can_create_composite_from_selection

            if can_create_composite_from_selection(scene):
                menu.addSeparator()
                composite_action = menu.addAction("Create Composite Component from Selection")

        if self.has_advanced_or_hidden_ports():
            menu.addSeparator()
            advanced_ports_action = menu.addAction(self.advanced_ports_menu_label())
            advanced_ports_action.setToolTip(self.advanced_ports_tooltip())

        if self.has_deprecated_connectors():
            menu.addSeparator()
            deprecated_connectors_action = menu.addAction(
                self.deprecated_connectors_menu_label()
            )
            deprecated_connectors_action.setToolTip(
                self.deprecated_connectors_tooltip()
            )

        menu.addSeparator()

        remove_text = (
            "Remove SubComponent"
            if int(getattr(self.component, "is_subcomp", 0) or 0)
            else "Remove Component"
        )
        remove_action = menu.addAction(remove_text)

        action = menu.exec(event.screenPos())

        if action == add_action:
            if scene is not None and hasattr(scene, "component_favorite_requested_callback"):
                scene.component_favorite_requested_callback(self.component)

        elif copy_action is not None and action == copy_action:
            if scene is not None:
                scene.copy_selection_to_clipboard()

        elif paste_action is not None and action == paste_action:
            if scene is not None:
                scene.paste_clipboard(event.scenePos())

        elif group_action is not None and action == group_action:
            if scene is not None:
                scene.group_selection()

        elif ungroup_action is not None and action == ungroup_action:
            if scene is not None:
                scene.ungroup_selection()

        elif composite_action is not None and action == composite_action:
            if scene is not None:
                from fuse.core.ui.selection_helpers import request_composite_from_selection

                request_composite_from_selection(
                    scene,
                    getattr(scene, "composite_creation_requested_callback", None),
                )

        elif advanced_ports_action is not None and action == advanced_ports_action:
            self.toggle_advanced_ports()

        elif (
            deprecated_connectors_action is not None
            and action == deprecated_connectors_action
        ):
            self.toggle_deprecated_connectors()

        elif action == remove_action:
            if scene is not None:
                if hasattr(scene, "delete_selection"):
                    scene.delete_selection()
                elif hasattr(scene, "delete_component_node"):
                    scene.delete_component_node(self)

        event.accept()

    def should_add_fallback_ports(self) -> bool:
        # Composite components use their explicit exposed-port mapping as the
        # authoritative source of visible ports. If no ports are exposed, the
        # composite should render with no ports rather than generic in/out
        # fallback ports.
        if bool(int(getattr(self.component, "is_composite", 0) or 0)):
            return False

        plugin_id = getattr(self.component, "plugin_id", "") or ""

        # SST metadata is authoritative. If sst-info says a component/subcomponent
        # has zero ports, FUSE should not invent generic in/out ports.
        if plugin_id == "sst":
            return False

        return True

    def metadata_cache_key(self, kind: str) -> tuple[str, str, str, str]:
        return (
            str(kind or ""),
            str(getattr(self.component, "plugin_id", "") or ""),
            str(getattr(self.component, "component_id", "") or ""),
            str(getattr(self.component, "target_id", "") or ""),
        )

    def cached_metadata_list(self, kind: str, loader) -> list[dict]:
        """
        Return copied component metadata, using a caller-provided cache when one
        is available.

        Project load constructs many repeated SST component types. Without a
        cache, every node construction can re-query the catalog for the same port
        and subcomponent-slot metadata. The returned dictionaries are copied so
        node-local UI code can safely annotate them.
        """
        cache = getattr(self, "_metadata_cache", None)
        if cache is None:
            return [dict(item) for item in loader()]

        key = self.metadata_cache_key(kind)
        if key not in cache:
            cache[key] = [dict(item) for item in loader()]

        return [dict(item) for item in cache.get(key, [])]

    def load_subcomp_connector_templates(self) -> list[dict]:
        def loader() -> list[dict]:
            try:
                return load_subcomp_connector_metadata_for_component(
                    self.component.plugin_id,
                    self.component.component_id,
                    self.component.target_id,
                )
            except Exception:
                return []

        return self.cached_metadata_list("subcomp_connectors", loader)

    def add_subcomp_connectors_from_metadata(self):
        self.subcomp_connector_templates = self.load_subcomp_connector_templates()

        for connector in list(self.subcomp_connectors):
            self.remove_subcomp_connector_item(connector)

        self.subcomp_connectors = []

        for template in self.subcomp_connector_templates:
            name = template.get("name", "")
            role = template.get("role", "")
            if not name or role not in {"slot", "interface"}:
                continue
            self.subcomp_connectors.append(
                SubcompConnectorItem(
                    self,
                    name=name,
                    role=role,
                    metadata=dict(template),
                )
            )

        self.apply_subcomp_connector_visibility()

    def remove_subcomp_connector_item(self, connector: SubcompConnectorItem):
        if connector in self.subcomp_connectors:
            self.subcomp_connectors.remove(connector)

        scene = self.scene()
        if scene is not None:
            if connector.label.scene() is not None:
                scene.removeItem(connector.label)
            if connector.scene() is not None:
                scene.removeItem(connector)
        else:
            connector.label.setParentItem(None)
            connector.setParentItem(None)

    def layout_subcomp_connectors(self):
        slots = [
            item
            for item in self.subcomp_connectors
            if item.role == "slot" and item.isVisible()
        ]
        interfaces = [
            item
            for item in self.subcomp_connectors
            if item.role == "interface" and item.isVisible()
        ]
        self.layout_subcomp_connector_side(slots, "bottom")
        self.layout_subcomp_connector_side(interfaces, "top")

    def layout_subcomp_connector_side(self, connectors: list[SubcompConnectorItem], side: str):
        if not connectors:
            return

        if side in {"top", "bottom"}:
            spacing = self.WIDTH / (len(connectors) + 1)
            y = -SubcompConnectorItem.EDGE_GAP if side == "top" else self.HEIGHT + SubcompConnectorItem.EDGE_GAP
            for index, connector in enumerate(connectors, start=1):
                connector.set_layout_position(spacing * index, y, side)
            return

        spacing = self.HEIGHT / (len(connectors) + 1)
        x = -SubcompConnectorItem.EDGE_GAP if side == "left" else self.WIDTH + SubcompConnectorItem.EDGE_GAP
        for index, connector in enumerate(connectors, start=1):
            connector.set_layout_position(x, spacing * index, side)

    def add_ports_from_database_or_defaults(self):
        self.port_templates = self.load_port_templates()

        if not self.port_templates:
            if self.should_add_fallback_ports():
                self.port_templates = [
                    {
                        "name": "in",
                        "description": "",
                        "iface": "",
                        "is_variable": False,
                        "base_name": "in",
                        "count_parameter": "",
                        "default_count": 1,
                    },
                    {
                        "name": "out",
                        "description": "",
                        "iface": "",
                        "is_variable": False,
                        "base_name": "out",
                        "count_parameter": "",
                        "default_count": 1,
                    },
                ]
            else:
                self.port_templates = []

        self.variable_port_templates = [
            template
            for template in self.port_templates
            if bool(template.get("is_variable"))
        ]

        for template in self.variable_port_templates:
            base_name = template.get("base_name", "") or template.get("name", "")
            self.variable_port_counts.setdefault(
                base_name,
                max(0, _safe_int(template.get("default_count"), 1)),
            )

        self.sync_ports_to_templates()
        self.update_add_ports_button_visibility()

    def sync_composite_ports_from_mappings(self) -> tuple[bool, str]:
        if not bool(int(getattr(self.component, "is_composite", 0) or 0)):
            return True, ""

        self.port_templates = [
            {
                "name": str(getattr(mapping, "external_port_name", "") or ""),
                "description": str(getattr(mapping, "description", "") or ""),
                "iface": str(getattr(mapping, "iface", "") or ""),
                "is_variable": False,
                "base_name": str(getattr(mapping, "external_port_name", "") or ""),
                "count_parameter": "",
                "default_count": 1,
            }
            for mapping in getattr(self, "composite_port_mappings", []) or []
            if bool(getattr(mapping, "exposed", True))
            and str(getattr(mapping, "external_port_name", "") or "")
        ]
        self.variable_port_templates = []
        result = self.sync_ports_to_templates()
        self.update_add_ports_button_visibility()
        return result

    def load_port_templates(self) -> list[dict]:
        def loader() -> list[dict]:
            try:
                return load_port_metadata_for_component(
                    self.component.plugin_id,
                    self.component.component_id,
                    self.component.target_id,
                )
            except Exception:
                try:
                    port_names = load_port_names_for_component(
                        self.component.plugin_id,
                        self.component.component_id,
                        self.component.target_id,
                    )
                except TypeError:
                    port_names = load_port_names_for_component(
                        self.component.plugin_id,
                        self.component.component_id,
                    )
                except Exception:
                    port_names = []

                return [
                    {
                        "name": port_name,
                        "description": "",
                        "iface": "",
                        "is_variable": False,
                        "base_name": port_name,
                        "count_parameter": "",
                        "default_count": 1,
                    }
                    for port_name in port_names
                ]

        return self.cached_metadata_list("ports", loader)

    def port_visibility_rules(self) -> dict[str, object]:
        """Return SST UI visibility rules for this node's raw/catalog ports."""
        if getattr(self.component, "plugin_id", "") != "sst":
            return {}

        try:
            from fuse.plugins.community.sst.port_visibility import rules_for_node

            return dict(rules_for_node(self))
        except Exception:
            return {}

    def port_visibility_rule_for_name(self, port_name: str):
        """Return the SST visibility rule for an expanded port name, if any."""
        requested = str(port_name or "").strip()
        if not requested:
            return None

        rules = self.port_visibility_rules()
        if requested in rules:
            return rules[requested]

        for template in self.port_templates:
            template_name = str(template.get("name", "") or "")
            base_name = str(template.get("base_name", "") or template_name)
            if requested in self.expanded_names_for_port_template(template):
                return rules.get(template_name) or rules.get(base_name)

        return None


    def deprecated_connector_rule_for_name(self, connector_kind: str, connector_name: str):
        """Return a version-aware deprecation rule for an SST connector."""
        if getattr(self.component, "plugin_id", "") != "sst":
            return None

        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_rule_for_node,
            )

            return deprecated_connector_rule_for_node(
                self,
                str(connector_name or "").strip(),
                str(connector_kind or "").strip(),
            )
        except Exception:
            return None

    def deprecated_port_rule_for_name(self, port_name: str):
        """Return a deprecation rule for a possibly-expanded port name.

        SST's memHierarchy catalog can carry legacy alias information in the
        template ``base_name`` even when the rendered port name is the modern
        replacement.  A concrete port such as ``highlink`` must not inherit the
        deprecation rule for an older alias such as ``high_network_0`` merely
        because it came from that template metadata.  Only apply the template or
        base-name rule when the requested name is directly deprecated, or when a
        variable/printf template expands into the concrete name.
        """
        requested = str(port_name or "").strip()
        if not requested:
            return None

        direct = self.deprecated_connector_rule_for_name("port", requested)
        if direct is not None:
            return direct

        for template in self.port_templates:
            template_name = str(template.get("name", "") or "")
            base_name = str(template.get("base_name", "") or template_name)
            if requested not in self.expanded_names_for_port_template(template):
                continue

            template_rule = self.deprecated_connector_rule_for_name("port", template_name)
            if template_rule is not None and requested == template_name:
                return template_rule

            is_variable_value = template.get("is_variable", 0)
            is_variable = str(is_variable_value).strip().lower() not in {"", "0", "false", "no"}
            is_parametric = "%(" in template_name or "%d" in template_name
            if not (is_variable or is_parametric):
                continue

            return (
                template_rule
                or self.deprecated_connector_rule_for_name("port", base_name)
            )

        return None

    def deprecated_slot_rule_for_connector(self, connector: SubcompConnectorItem):
        """Return a deprecation rule for a SubComponent slot connector."""
        if connector is None or getattr(connector, "role", "") != "slot":
            return None
        return self.deprecated_connector_rule_for_name("slot", connector.name)

    def deprecated_connector_stage(self, rule) -> str:
        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_stage_for_node,
            )

            return deprecated_connector_stage_for_node(self, rule)
        except Exception:
            return "deprecated"

    def deprecated_connector_default_visible(self, rule) -> bool:
        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_default_visible_for_node,
            )

            return deprecated_connector_default_visible_for_node(self, rule)
        except Exception:
            return True

    def deprecated_connector_tooltip_for_rule(self, rule) -> str:
        if rule is None:
            return ""

        try:
            from fuse.plugins.community.sst.port_visibility import (
                deprecated_connector_tooltip,
            )

            return deprecated_connector_tooltip(
                rule,
                stage=self.deprecated_connector_stage(rule),
            )
        except Exception:
            return "Deprecated SST connector."

    def deprecated_port_tooltip(self, port_name: str) -> str:
        return self.deprecated_connector_tooltip_for_rule(
            self.deprecated_port_rule_for_name(port_name)
        )

    def deprecated_slot_tooltip(self, connector: SubcompConnectorItem) -> str:
        return self.deprecated_connector_tooltip_for_rule(
            self.deprecated_slot_rule_for_connector(connector)
        )

    def deprecated_port_default_visible(self, port_name: str) -> bool:
        rule = self.deprecated_port_rule_for_name(port_name)
        if rule is None:
            return True
        return self.deprecated_connector_default_visible(rule)

    def deprecated_slot_default_visible(self, connector: SubcompConnectorItem) -> bool:
        rule = self.deprecated_slot_rule_for_connector(connector)
        if rule is None:
            return True
        return self.deprecated_connector_default_visible(rule)

    def subcomp_connector_is_attached(self, connector: SubcompConnectorItem) -> bool:
        scene = self.scene()
        if scene is not None and hasattr(scene, "subcomp_connector_is_connected"):
            try:
                return bool(scene.subcomp_connector_is_connected(connector))
            except Exception:
                return False
        return False

    def deprecated_connector_hidden_names(self) -> list[str]:
        names: list[str] = []

        for name in self.expanded_port_names():
            rule = self.deprecated_port_rule_for_name(name)
            if rule is None:
                continue
            if self.deprecated_connector_default_visible(rule):
                continue
            if self.show_deprecated_connectors or self.show_advanced_ports:
                continue
            if any(port.name == name and port.is_connected() for port in self.ports):
                continue
            names.append(f"port {name}")

        for connector in self.subcomp_connectors:
            rule = self.deprecated_slot_rule_for_connector(connector)
            if rule is None:
                continue
            if self.deprecated_connector_default_visible(rule):
                continue
            if self.show_deprecated_connectors:
                continue
            if self.subcomp_connector_is_attached(connector):
                continue
            names.append(f"slot {connector.name}")

        return names

    def has_deprecated_connectors(self) -> bool:
        if any(
            self.deprecated_port_rule_for_name(name) is not None
            for name in self.expanded_port_names()
        ):
            return True

        return any(
            self.deprecated_slot_rule_for_connector(connector) is not None
            for connector in self.subcomp_connectors
        )

    def deprecated_connectors_menu_label(self) -> str:
        if self.show_deprecated_connectors:
            return "Hide deprecated/legacy connectors"
        hidden_count = len(self.deprecated_connector_hidden_names())
        suffix = f" ({hidden_count})" if hidden_count else ""
        return f"Show deprecated/legacy connectors{suffix}"

    def deprecated_connectors_tooltip(self) -> str:
        hidden = self.deprecated_connector_hidden_names()
        if self.show_deprecated_connectors:
            return "Hide deprecated SST ports and SubComponent slots that are not currently used."

        if hidden:
            return (
                "Show deprecated SST ports and SubComponent slots hidden by the guided view:\n  "
                + "\n  ".join(hidden)
            )

        return (
            "Deprecated SST connectors are visible in this target but marked with "
            "warning styling. New models should use their replacements."
        )

    def port_is_advanced_or_hidden(self, port_name: str) -> bool:
        deprecated_rule = self.deprecated_port_rule_for_name(port_name)
        if (
            deprecated_rule is not None
            and self.deprecated_connector_default_visible(deprecated_rule)
        ):
            return False

        rule = self.port_visibility_rule_for_name(port_name)
        return bool(rule is not None and not bool(getattr(rule, "default_visible", True)))

    def has_advanced_or_hidden_ports(self) -> bool:
        return any(
            self.port_is_advanced_or_hidden(name)
            for name in self.expanded_port_names()
        )

    def hidden_advanced_port_names(self) -> list[str]:
        return [
            name
            for name in self.expanded_port_names()
            if self.port_is_advanced_or_hidden(name)
            and not self.show_advanced_ports
            and not self.show_deprecated_connectors
            and not any(port.name == name and port.is_connected() for port in self.ports)
        ]

    def advanced_ports_menu_label(self) -> str:
        if self.show_advanced_ports:
            return "Hide advanced/raw ports"
        hidden_count = len(self.hidden_advanced_port_names())
        suffix = f" ({hidden_count})" if hidden_count else ""
        return f"Show advanced/raw ports{suffix}"

    def advanced_ports_tooltip(self) -> str:
        hidden = self.hidden_advanced_port_names()
        if self.show_advanced_ports:
            return (
                "Hide raw SST catalog ports that are shadowed by runtime "
                "SubComponent slots or marked as advanced."
            )

        if hidden:
            return (
                "Show raw SST catalog ports hidden by the guided view:\\n  "
                + "\\n  ".join(hidden)
            )

        return "Show raw SST catalog ports hidden by the guided view."

    def port_should_be_visible(self, port: PortItem) -> bool:
        deprecated_rule = self.deprecated_port_rule_for_name(port.name)
        if deprecated_rule is not None:
            if self.deprecated_connector_default_visible(deprecated_rule):
                return True

            # Never hide a deprecated connector that is already used; this keeps
            # legacy/imported models visible and editable.
            if port.is_connected():
                return True

            if self.show_deprecated_connectors or self.show_advanced_ports:
                return True

            return False

        rule = self.port_visibility_rule_for_name(port.name)
        if rule is None:
            return True

        if bool(getattr(rule, "default_visible", True)):
            return True

        # Never hide a port that already owns a link; this keeps legacy/imported
        # models visible and editable while still hiding unused misleading ports.
        if port.is_connected():
            return True

        return bool(self.show_advanced_ports)

    def advanced_port_tooltip(self, port: PortItem) -> str:
        rule = self.port_visibility_rule_for_name(port.name)
        if rule is None:
            return ""

        try:
            from fuse.plugins.community.sst.port_visibility import port_rule_tooltip

            return port_rule_tooltip(rule)
        except Exception:
            return "Advanced/raw SST port. Use the component '+' menu to show or hide it."

    def apply_port_visibility(self):
        """Apply guided/advanced/deprecated port visibility and relayout ports."""
        visible_names: list[str] = []

        for port in self.ports:
            visible = self.port_should_be_visible(port)
            port.setVisible(visible)
            port.label.setVisible(visible)

            if visible:
                visible_names.append(port.name)

            base_tooltip = f"Port: {port.name}"
            if port.interface:
                base_tooltip += f"\nInterface: {port.interface}"
            if port.is_connected():
                base_tooltip = f"⚠ Port Occupied\n{port.name}"

            tooltip_parts = [base_tooltip]
            advanced_tooltip = self.advanced_port_tooltip(port)
            if advanced_tooltip:
                tooltip_parts.append(advanced_tooltip)

            deprecated_tooltip = self.deprecated_port_tooltip(port.name)
            if deprecated_tooltip:
                tooltip_parts.append(deprecated_tooltip)

            if hasattr(port, "set_deprecated_visual_state"):
                port.set_deprecated_visual_state(bool(deprecated_tooltip))
            else:
                port.label.setDefaultTextColor(
                    QColor("#9a3412") if deprecated_tooltip else QColor("#333333")
                )
                if not port.is_connected():
                    if deprecated_tooltip:
                        port.setBrush(QBrush(QColor("#f97316")))
                        port.setPen(QPen(QColor("#9a3412"), 2.2))
                    else:
                        port.setBrush(QBrush(QColor("#2f80ed")))
                        port.setPen(QPen(QColor("#1f4e79"), 1.0))

            port.setToolTip("\n\n".join(tooltip_parts))

        self.layout_ports(visible_names)
        self.update_add_ports_button_visibility()


    def subcomp_connector_should_be_visible(self, connector: SubcompConnectorItem) -> bool:
        rule = self.deprecated_slot_rule_for_connector(connector)
        if rule is None:
            return True

        if self.deprecated_connector_default_visible(rule):
            return True

        if self.subcomp_connector_is_attached(connector):
            return True

        return bool(self.show_deprecated_connectors)

    def apply_subcomp_connector_visibility(self):
        """Apply deprecated SubComponent-slot visibility and relayout connectors."""
        for connector in self.subcomp_connectors:
            visible = self.subcomp_connector_should_be_visible(connector)
            connector.setVisible(visible)
            connector.label.setVisible(visible)

            deprecated_tooltip = self.deprecated_slot_tooltip(connector)
            if deprecated_tooltip:
                base_tooltip = (
                    f"SubComponent slot: {connector.name}"
                    if connector.role == "slot"
                    else f"SubComponent connector: {connector.name}"
                )
                if connector.interface:
                    base_tooltip += f"\nInterface: {connector.interface}"
                connector.setToolTip(f"{base_tooltip}\n\n{deprecated_tooltip}")
                if hasattr(connector, "set_deprecated_visual_state"):
                    connector.set_deprecated_visual_state(True)
            else:
                base_tooltip = (
                    f"SubComponent slot: {connector.name}"
                    if connector.role == "slot"
                    else f"SubComponent connector: {connector.name}"
                )
                if connector.interface:
                    base_tooltip += f"\nInterface: {connector.interface}"
                connector.setToolTip(base_tooltip)
                if hasattr(connector, "set_deprecated_visual_state"):
                    connector.set_deprecated_visual_state(False)

        self.layout_subcomp_connectors()

    def set_show_advanced_ports(self, enabled: bool):
        self.show_advanced_ports = bool(enabled)
        self.apply_port_visibility()

        scene = self.scene()
        if scene is not None:
            if hasattr(scene, "reroute_links_for_node"):
                scene.reroute_links_for_node(self, force_full=True)
            if hasattr(scene, "properties_panel") and scene.properties_panel is not None:
                scene.properties_panel.show_component(self)

    def toggle_advanced_ports(self):
        self.set_show_advanced_ports(not self.show_advanced_ports)

    def set_show_deprecated_connectors(self, enabled: bool):
        self.show_deprecated_connectors = bool(enabled)
        self.apply_port_visibility()
        self.apply_subcomp_connector_visibility()

        scene = self.scene()
        if scene is not None:
            if hasattr(scene, "reroute_links_for_node"):
                scene.reroute_links_for_node(self, force_full=True)
            if hasattr(scene, "properties_panel") and scene.properties_panel is not None:
                scene.properties_panel.show_component(self)

    def toggle_deprecated_connectors(self):
        self.set_show_deprecated_connectors(not self.show_deprecated_connectors)

    def expanded_names_for_port_template(self, template: dict) -> list[str]:
        """Return the concrete port names represented by a catalog template."""

        template_name = str(template.get("name", "") or "")
        base_name = str(template.get("base_name", "") or template_name)

        if bool(template.get("is_variable")):
            # Variable FUSE/SST port families are controlled by
            # ``variable_port_counts``. Some SST catalogs store the original
            # port pattern as ``port%(num_ports)d``; using the parameter
            # expression first creates a one-click lag because the plugin hook
            # mirrors the count back into ``num_ports`` after the scene has
            # already re-expanded the visible ports.
            count = max(0, _safe_int(self.variable_port_counts.get(base_name), 1))
            return [f"{base_name}{index}" for index in range(count)]

        # SST ``sst-info`` may report printf-style port templates such as
        # ``nic%(nicsPerNode)dcore%(num_vNics/nicsPerNode)d``. These are count
        # expressions, not literal port names, and must be expanded before the
        # scene can restore links against them.
        if "%(" in template_name:
            expanded = expand_parametric_port_template(
                template_name,
                parameters=self.parameters,
                variable_port_counts=self.variable_port_counts,
            )
            return expanded or [template_name]

        expanded = expand_parametric_port_template(
            template_name,
            parameters=self.parameters,
            variable_port_counts=self.variable_port_counts,
        )
        return expanded or ([template_name] if template_name else [])

    def expanded_port_names(self) -> list[str]:
        names: list[str] = []

        for template in self.port_templates:
            names.extend(self.expanded_names_for_port_template(template))

        return [name for name in names if name]

    def resolve_restored_port_name(self, port_name: str) -> str:
        """
        Resolve a serialized link endpoint to a currently-visible port name.

        Older projects may contain SST printf-style port templates as endpoint
        names. Newer projects may already contain the concrete expanded name
        even though a stale scene still has the template literal visible. This
        helper accepts either form, synchronizes the node's port list to current
        template expansion, and returns the concrete visible port name to use.
        """

        requested = str(port_name or "")
        if not requested:
            return requested

        if any(port.name == requested for port in self.ports):
            return requested

        # The serialized endpoint may itself be a template literal. Expand it
        # and use the first concrete member that exists on the node.
        for candidate in expand_parametric_port_template(
            requested,
            parameters=self.parameters,
            variable_port_counts=self.variable_port_counts,
        ):
            if candidate != requested and any(port.name == candidate for port in self.ports):
                return candidate

        # Re-sync ports to the current catalog expansion. This handles nodes
        # loaded from projects saved before parametric port support existed.
        self.sync_ports_to_templates()

        if any(port.name == requested for port in self.ports):
            return requested

        for candidate in expand_parametric_port_template(
            requested,
            parameters=self.parameters,
            variable_port_counts=self.variable_port_counts,
        ):
            if any(port.name == candidate for port in self.ports):
                return candidate

        # Inverse case: the serialized endpoint is already concrete, but the
        # live node still has a stale template-literal port. If the template
        # expands to the requested name, rename the stale port in place so link
        # restoration can continue without dropping the connection.
        for template in self.port_templates:
            expanded = self.expanded_names_for_port_template(template)
            if requested not in expanded:
                continue

            for port in self.ports:
                if port.name in expanded:
                    return port.name
                if "%(" in port.name:
                    literal_expanded = expand_parametric_port_template(
                        port.name,
                        parameters=self.parameters,
                        variable_port_counts=self.variable_port_counts,
                    )
                    if requested in literal_expanded:
                        port.set_name(requested)
                        self.layout_ports(self.expanded_port_names())
                        return requested

        return requested

    def sync_ports_to_templates(self) -> tuple[bool, str]:
        desired_names = self.expanded_port_names()
        desired_set = set(desired_names)
        existing_by_name = {port.name: port for port in self.ports}

        for port in list(self.ports):
            if port.name in desired_set:
                continue

            if port.is_connected():
                return False, f"Cannot remove connected port '{port.name}'."

            self.remove_port_item(port)

        existing_by_name = {port.name: port for port in self.ports}

        for port_name in desired_names:
            if port_name not in existing_by_name:
                side = self.preferred_side_for_port(port_name)
                self.ports.append(
                    PortItem(
                        self,
                        port_name,
                        0,
                        0,
                        side=side,
                        metadata=self.metadata_for_expanded_port(port_name),
                    )
                )

        self.apply_port_visibility()
        return True, ""

    def remove_port_item(self, port: PortItem):
        if port in self.ports:
            self.ports.remove(port)

        scene = self.scene()

        if scene is not None:
            if port.label.scene() is not None:
                scene.removeItem(port.label)
            if port.scene() is not None:
                scene.removeItem(port)
        else:
            port.label.setParentItem(None)
            port.setParentItem(None)

    def preferred_side_for_port(self, port_name: str) -> str:
        """
        Return the preferred semantic side for a port.

        This is only the preference. The final layout may move ports to another
        side when a preferred side is full.
        """
        name = port_name.lower()

        if any(
            token in name
            for token in (
                "lowlink",
                "low_network",
                "low",
                "lower",
                "downstream",
            )
        ):
            return "left"

        if any(
            token in name
            for token in (
                "highlink",
                "high_network",
                "high",
                "upper",
                "upstream",
            )
        ):
            return "right"

        if (
            name in {"in", "input", "request", "req"}
            or name.startswith(("in", "input", "req", "src", "source", "west", "left"))
            or name.endswith(("in", "input", "req", "src"))
        ):
            return "left"

        if (
            name in {"out", "output", "response", "resp"}
            or name.startswith(("out", "output", "resp", "dst", "dest", "east", "right"))
            or name.endswith(("out", "output", "resp", "dst", "dest"))
        ):
            return "right"

        return "right"

    def port_family_name(self, port_name: str) -> str:
        """
        Return a stable family name for ports such as lowlink0, lowlink1, etc.

        This helps keep variable ports from the same family together.
        """
        index = len(port_name)

        while index > 0 and port_name[index - 1].isdigit():
            index -= 1

        return port_name[:index] or port_name

    def side_capacity(self, side: str) -> int:
        if side in {"left", "right"}:
            return self.MAX_VERTICAL_PORTS_PER_SIDE

        return self.MAX_HORIZONTAL_PORTS_PER_SIDE

    def overflow_sides_for_preference(self, preferred_side: str) -> list[str]:
        """
        Return fallback side order.

        Left/right sides are preferred first. Top/bottom are used as overflow
        only when the vertical sides are crowded.
        """
        if preferred_side == "left":
            return ["left", "right", "bottom", "top"]

        if preferred_side == "right":
            return ["right", "left", "top", "bottom"]

        if preferred_side == "top":
            return ["right", "left", "top", "bottom"]

        if preferred_side == "bottom":
            return ["left", "right", "bottom", "top"]

        return ["right", "left", "top", "bottom"]

    def assign_ports_to_sides(self, ordered_ports: list[PortItem]) -> dict[str, list[PortItem]]:
        """
        Assign ports to sides while balancing readability.

        Goals:
        - Prefer left/right.
        - Keep semantic families together when possible.
        - Avoid more than MAX_* ports on any one side.
        - Overflow to top/bottom only when needed.
        """
        side_groups: dict[str, list[PortItem]] = {
            "left": [],
            "right": [],
            "top": [],
            "bottom": [],
        }

        family_to_side: dict[str, str] = {}

        for port in ordered_ports:
            family = self.port_family_name(port.name)
            preferred = self.preferred_side_for_port(port.name)

            assigned_side = family_to_side.get(family)

            if assigned_side is not None:
                if len(side_groups[assigned_side]) < self.side_capacity(assigned_side):
                    side_groups[assigned_side].append(port)
                    port.side = assigned_side
                    continue

            for candidate_side in self.overflow_sides_for_preference(preferred):
                if len(side_groups[candidate_side]) < self.side_capacity(candidate_side):
                    assigned_side = candidate_side
                    break
            else:
                assigned_side = min(
                    side_groups,
                    key=lambda side: len(side_groups[side]),
                )

            family_to_side.setdefault(family, assigned_side)
            side_groups[assigned_side].append(port)
            port.side = assigned_side

        return side_groups

    def layout_ports(self, ordered_names: list[str]):
        port_by_name = {port.name: port for port in self.ports}
        ordered_ports = [
            port_by_name[name] for name in ordered_names if name in port_by_name
        ]

        side_groups = self.assign_ports_to_sides(ordered_ports)

        self.layout_side_ports(side_groups["left"], "left")
        self.layout_side_ports(side_groups["right"], "right")
        self.layout_side_ports(side_groups["top"], "top")
        self.layout_side_ports(side_groups["bottom"], "bottom")

        self.update_connected_links()

    def layout_side_ports(self, ports: list[PortItem], side: str):
        if not ports:
            return

        edge_gap = PortItem.EDGE_GAP

        if side in {"left", "right"}:
            available = self.HEIGHT
            spacing = max(
                self.MIN_PORT_SPACING,
                available / (len(ports) + 1),
            )

            total_span = spacing * (len(ports) - 1)
            start_y = (self.HEIGHT - total_span) / 2.0

            for index, port in enumerate(ports):
                y = start_y + spacing * index
                x = -edge_gap if side == "left" else self.WIDTH + edge_gap
                port.set_layout_position(x, y, side)

            return

        available = self.WIDTH
        spacing = max(
            self.MIN_PORT_SPACING,
            available / (len(ports) + 1),
        )

        total_span = spacing * (len(ports) - 1)
        start_x = (self.WIDTH - total_span) / 2.0

        for index, port in enumerate(ports):
            x = start_x + spacing * index
            y = -edge_gap if side == "top" else self.HEIGHT + edge_gap
            port.set_layout_position(x, y, side)

    def update_connected_links(self):
        seen: set[int] = set()

        for port in self.ports:
            for connection in port.connections:
                identity = id(connection)
                if identity in seen:
                    continue
                seen.add(identity)
                connection.update_position()

    def variable_port_bases_for_count_parameter(self, parameter_name: str) -> list[str]:
        """Return variable-port base names controlled by a component parameter."""

        requested = str(parameter_name or "").strip().lower()
        if not requested:
            return []

        base_names: list[str] = []
        for template in self.variable_port_templates:
            count_parameter = str(template.get("count_parameter", "") or "").strip()
            if count_parameter.lower() != requested:
                continue

            base_name = str(template.get("base_name", "") or template.get("name", "") or "")
            if base_name:
                base_names.append(base_name)

        return base_names

    def sync_variable_port_count_from_parameter(self, parameter_name: str, value) -> tuple[bool, str]:
        """Mirror manual edits to a count parameter into visible variable ports."""

        base_names = self.variable_port_bases_for_count_parameter(parameter_name)
        if not base_names:
            return True, ""

        try:
            count = int(value)
        except (TypeError, ValueError):
            return False, f"Port count parameter '{parameter_name}' must be an integer."

        for base_name in base_names:
            ok, message = self.set_variable_port_count(base_name, count)
            if not ok:
                return ok, message

        return True, ""

    def variable_port_family_for_port(self, port_name: str) -> str | None:
        """Return the variable-port family base name for a concrete port."""

        name = str(port_name or "")

        for template in self.variable_port_templates:
            base_name = str(template.get("base_name", "") or template.get("name", "") or "")
            if not base_name or not name.startswith(base_name):
                continue

            suffix = name[len(base_name):]
            if suffix.isdigit():
                return base_name

        return None

    def variable_port_index(self, base_name: str, port_name: str) -> int | None:
        name = str(port_name or "")
        base = str(base_name or "")

        if not base or not name.startswith(base):
            return None

        suffix = name[len(base):]
        if not suffix.isdigit():
            return None

        return int(suffix)

    def variable_port_current_count(self, base_name: str) -> int:
        count = max(0, _safe_int(self.variable_port_counts.get(base_name), 0))

        for port in self.ports:
            index = self.variable_port_index(base_name, port.name)
            if index is not None:
                count = max(count, index + 1)

        return count

    def variable_ports_for_family(self, base_name: str) -> list[PortItem]:
        ports = [
            port
            for port in self.ports
            if self.variable_port_index(base_name, port.name) is not None
        ]
        return sorted(
            ports,
            key=lambda port: self.variable_port_index(base_name, port.name) or 0,
        )

    def choose_variable_port_to_remove(
        self,
        base_name: str,
        port_name: str | None = None,
    ) -> PortItem | None:
        ports = self.variable_ports_for_family(base_name)
        if not ports:
            return None

        if port_name:
            for port in ports:
                if port.name == port_name:
                    return port
            return None

        # Prefer an unconnected port so the common Add/Remove menu operation
        # does not disturb existing links. Use the highest-numbered available
        # port to preserve the names of lower ports whenever possible.
        for port in reversed(ports):
            if not port.is_connected():
                return port

        # All ports are connected. Let the confirmation path decide whether to
        # remove the highest-numbered port and its link.
        return ports[-1]

    def confirm_remove_connected_variable_port(self, base_name: str, port_names: list[str]) -> bool:
        if len(port_names) == 1:
            detail = f"Port '{port_names[0]}' is linked."
        else:
            detail = "All ports in this family are linked."

        response = QMessageBox.warning(
            None,
            "Remove Connected Port",
            (
                f"{detail}\n\n"
                "Removing the port will also remove its connected link and may "
                "break model validation. Continue?"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return response == QMessageBox.Yes

    def rename_variable_port_and_link_endpoints(self, port: PortItem, new_name: str):
        old_name = port.name
        if old_name == new_name:
            return

        for connection in list(port.connections):
            if connection.source_port is port:
                connection.link.source_port = new_name
            if connection.target_port is port:
                connection.link.target_port = new_name
            connection.update_tooltip()

        port.set_name(new_name)
        port.metadata = self.metadata_for_expanded_port(new_name)

    def remove_variable_port(
        self,
        base_name: str,
        *,
        port_name: str | None = None,
        confirm: bool = True,
    ) -> tuple[bool, str]:
        """Remove one concrete member of a variable port family.

        Removing a lower-numbered member compacts later port names so the visible
        family remains sequential from zero. Any links attached to renamed ports
        have their saved endpoint names updated to match.
        """

        if self.variable_port_template(base_name) is None:
            return False, f"'{base_name}' is not a variable port family for this component."

        count = self.variable_port_current_count(base_name)
        if count <= 0:
            return False, f"No '{base_name}' ports are available to remove."

        target_port = self.choose_variable_port_to_remove(base_name, port_name)
        if target_port is None:
            return False, f"No '{base_name}' port was found to remove."

        target_index = self.variable_port_index(base_name, target_port.name)
        if target_index is None:
            return False, f"'{target_port.name}' is not in the '{base_name}' variable port family."

        all_family_ports = self.variable_ports_for_family(base_name)
        if target_port.is_connected() and confirm:
            connected_names = [
                port.name for port in all_family_ports if port.is_connected()
            ]
            if not self.confirm_remove_connected_variable_port(base_name, connected_names):
                return False, "Port removal cancelled."

        scene = self.scene()

        for connection in list(target_port.connections):
            if scene is not None and hasattr(scene, "delete_link"):
                scene.delete_link(connection)
            else:
                for port in (connection.source_port, connection.target_port):
                    if connection in port.connections:
                        port.connections.remove(connection)
                    port.update_connection_state()

        self.remove_port_item(target_port)

        indexed_ports = {
            self.variable_port_index(base_name, port.name): port
            for port in self.variable_ports_for_family(base_name)
        }

        for index in range(target_index + 1, count):
            port = indexed_ports.get(index)
            if port is None:
                continue
            self.rename_variable_port_and_link_endpoints(
                port,
                f"{base_name}{index - 1}",
            )

        ok, message = self.set_variable_port_count(base_name, count - 1)
        if not ok:
            return ok, message

        return True, ""

    def decrement_variable_port(self, base_name: str):
        self.remove_variable_port(base_name, confirm=True)

    def variable_port_template(self, base_name: str) -> dict | None:
        for template in self.variable_port_templates:
            if (template.get("base_name", "") or template.get("name", "")) == base_name:
                return template

        return None

    def connected_ports_removed_by_count(self, base_name: str, new_count: int) -> list[str]:
        removed_connected = []

        for port in self.ports:
            if not port.name.startswith(base_name):
                continue

            suffix = port.name[len(base_name):]
            if not suffix.isdigit():
                continue

            if int(suffix) >= new_count and port.is_connected():
                removed_connected.append(port.name)

        return removed_connected

    def set_variable_port_count(self, base_name: str, count: int) -> tuple[bool, str]:
        if self.variable_port_template(base_name) is None:
            return False, f"'{base_name}' is not a variable port family for this component."

        count = max(0, int(count))
        removed_connected = self.connected_ports_removed_by_count(base_name, count)

        if removed_connected:
            return (
                False,
                "Cannot reduce port count because these ports are connected: "
                + ", ".join(sorted(removed_connected)),
            )

        old_count = self.variable_port_counts.get(base_name)
        self.variable_port_counts[base_name] = count
        ok, message = self.sync_ports_to_templates()

        if not ok:
            if old_count is None:
                self.variable_port_counts.pop(base_name, None)
            else:
                self.variable_port_counts[base_name] = old_count
            self.sync_ports_to_templates()
            return ok, message

        scene = self.scene()
        if scene is not None:
            if hasattr(scene, "notify_plugin_variable_port_count_changed"):
                scene.notify_plugin_variable_port_count_changed(
                    self,
                    base_name,
                    count,
                    self.variable_port_template(base_name) or {},
                )
            if hasattr(scene, "reroute_links_for_node"):
                scene.reroute_links_for_node(self, force_full=True)
            if hasattr(scene, "notify_model_changed"):
                scene.notify_model_changed()
            if hasattr(scene, "properties_panel") and scene.properties_panel is not None:
                scene.properties_panel.show_component(self)

        return True, ""

    def increment_variable_port(self, base_name: str):
        current = max(0, _safe_int(self.variable_port_counts.get(base_name), 1))
        self.set_variable_port_count(base_name, current + 1)

    def update_add_ports_button_visibility(self):
        should_show_button = bool(self.variable_port_templates) or self.has_advanced_or_hidden_ports()

        if should_show_button and self.add_ports_button is None:
            self.add_ports_button = AddPortsButtonItem(self)
        elif not should_show_button and self.add_ports_button is not None:
            self.add_ports_button.setParentItem(None)
            self.add_ports_button = None

    def mousePressEvent(self, event):
        scene = self.scene()

        if scene is not None:
            if hasattr(scene, "begin_node_drag"):
                scene.begin_node_drag(self)

            if self.isSelected() and hasattr(scene, "defer_component_selection_until_drag_end"):
                # Pressing an already-selected node is usually the start of a
                # drag. Do not refresh properties/link highlights until release
                # proves it was a click; that work can dominate drag latency on
                # components with long links or many subcomponent attachments.
                scene.defer_component_selection_until_drag_end(self)
            elif hasattr(scene, "select_component"):
                scene.select_component(self)

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        scene = self.scene()

        if scene is not None and hasattr(scene, "end_node_drag"):
            scene.end_node_drag(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self.update_selection_style()

        if change == QGraphicsItem.ItemPositionChange:
            scene = self.scene()
            if (
                scene is not None
                and bool(getattr(scene, "snap_to_grid_enabled", False))
                and not bool(getattr(scene, "_dragging_node", False))
                and isinstance(value, QPointF)
                and hasattr(scene, "snap_position_to_grid")
            ):
                return scene.snap_position_to_grid(value)

        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()

            if scene is not None and getattr(scene, "_model_loading_depth", 0) > 0:
                return super().itemChange(change, value)

            if scene is not None and getattr(scene, "_bulk_drag_fast_path_active", False):
                if hasattr(scene, "note_bulk_drag_node_moved"):
                    scene.note_bulk_drag_node_moved(self)
                return super().itemChange(change, value)

            if scene is not None and hasattr(scene, "apply_group_drag"):
                scene.apply_group_drag(self)

            if scene is not None and getattr(scene, "_dragging_node", False):
                scene._drag_changed = True
                if hasattr(scene, "request_drag_preview_for_node"):
                    scene.request_drag_preview_for_node(self)
            elif scene is not None and hasattr(scene, "reroute_links_for_node"):
                scene.reroute_links_for_node(self)
                if hasattr(scene, "notify_model_changed"):
                    scene.notify_model_changed()
            else:
                for port in self.ports:
                    for connection in port.connections:
                        connection.update_position()

        return super().itemChange(change, value)

    def set_validation_warnings(self, messages: list[str]):
        self.validation_messages = messages

        if messages:
            self.setPen(self.validation_pen)
            self.validation_warning_item.setVisible(True)
            self.validation_warning_item.setToolTip("\n".join(messages))
            self.setToolTip("\n".join(messages))
        else:
            self.setPen(self.normal_pen)
            self.validation_warning_item.setVisible(False)
            self.validation_warning_item.setToolTip("")
            self.setToolTip("")

    def add_icon(self):
        if not self.icon_path:
            return

        path = resolve_icon_path(self.icon_path)
        if not path.exists():
            return

        cache_key = (str(path), int(self.ICON_SIZE), int(self.ICON_SIZE))
        pixmap = _SCALED_ICON_CACHE.get(cache_key)
        if pixmap is None:
            pixmap = QPixmap(str(path))
            if pixmap.isNull():
                return

            pixmap = pixmap.scaled(
                self.ICON_SIZE,
                self.ICON_SIZE,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            _SCALED_ICON_CACHE[cache_key] = pixmap

        self.icon_item = QGraphicsPixmapItem(pixmap, self)

        icon_x = (self.WIDTH - pixmap.width()) / 2.0
        icon_y = self.ICON_Y

        self.icon_item.setPos(icon_x, icon_y)
        self.icon_item.setZValue(2)

    def set_icon_path(self, icon_path: str):
        self.icon_path = icon_path

        if hasattr(self, "icon_item") and self.icon_item is not None:
            self.icon_item.setParentItem(None)
            if self.scene() is not None:
                self.scene().removeItem(self.icon_item)
            self.icon_item = None

        self.add_icon()

    def metadata_for_expanded_port(self, port_name: str) -> dict:
        for template in self.port_templates:
            if port_name in self.expanded_names_for_port_template(template):
                metadata = dict(template)
                metadata["expanded_name"] = port_name
                rule = self.port_visibility_rule_for_name(port_name)
                if rule is not None:
                    metadata["sst_port_visibility"] = {
                        "mode": getattr(rule, "mode", ""),
                        "use_slot": getattr(rule, "use_slot", ""),
                        "child_type": getattr(rule, "child_type", ""),
                        "child_port": getattr(rule, "child_port", ""),
                        "default_visible": bool(getattr(rule, "default_visible", True)),
                    }
                return metadata

        return {}
