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
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
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
    QMenu,
)

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
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


def _safe_int(value, default: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class PortItem(QGraphicsEllipseItem):
    RADIUS = 5.0
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

        self.setPos(x, y)
        self.setBrush(QBrush(QColor("#2f80ed")))
        self.setPen(QPen(QColor("#1f4e79"), 1))
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        tooltip = f"Port: {name}"
        if self.interface:
            tooltip += f"\nInterface: {self.interface}"
        self.setToolTip(tooltip)
        self.setZValue(10)

        self.label = QGraphicsTextItem(name, node)
        self.label.setDefaultTextColor(QColor("#333333"))
        self.label.setScale(self.LABEL_SCALE)
        self.label.setZValue(11)

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

    def is_connected(self) -> bool:
        """Each SST port may participate in at most one link."""
        return len(self.connections) > 0

    def update_connection_state(self):
        if self.is_connected():
            self.setBrush(QBrush(QColor("#6b7280")))
            self.setToolTip(f"⚠ Port Occupied\n{self.name}")
        else:
            self.setBrush(QBrush(QColor("#2f80ed")))
            tooltip = f"Port: {self.name}"
            if self.interface:
                tooltip += f"\nInterface: {self.interface}"
            self.setToolTip(tooltip)

    def mousePressEvent(self, event):
        scene = self.scene()
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

    def __init__(self, link: ModelLink, source_port: PortItem, target_port: PortItem):
        super().__init__()
        self.link = link
        self.source_port = source_port
        self.target_port = target_port
        self.route_points: list[QPointF] = []

        self.base_color = QColor("#38bdf8")
        self.highlight_color = QColor("#f59e0b")
        self.warning_color = QColor("#f59e0b")
        self.error_color = QColor("#ef4444")

        self.setPen(QPen(self.base_color, 2))
        self.setZValue(5)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        self.update_tooltip()

        source_port.connections.append(self)
        target_port.connections.append(self)
        source_port.update_connection_state()
        target_port.update_connection_state()

        self.update_position()

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
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), self.SELECTION_TOLERANCE))
        stroker.setCapStyle(Qt.RoundCap)
        stroker.setJoinStyle(Qt.RoundJoin)
        return stroker.createStroke(self.path())

    def contains(self, point) -> bool:
        return self.shape().contains(point)

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
        self.setPath(self.build_path_from_points(points))

    def clear_route_points(self):
        self.route_points = []

    def is_connected_to_node(self, node: "ComponentNodeItem") -> bool:
        return self.source_port.node is node or self.target_port.node is node

    def link_base_color(self) -> QColor:
        if getattr(self.link, "compatibility_severity", "ok") == "error":
            return self.error_color
        if getattr(self.link, "compatibility_severity", "ok") == "warning":
            return self.warning_color
        return self.base_color

    def set_highlighted(self, highlighted: bool):
        if highlighted:
            self.setPen(QPen(self.highlight_color, 4))
            self.setZValue(20)
        else:
            self.setPen(QPen(self.link_base_color(), 2))
            self.setZValue(5)

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

        self.normal_brush = QBrush(QColor("#8b5cf6"))
        self.normal_pen = QPen(QColor("#5b21b6"), 1.5)

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
        self.label.setDefaultTextColor(QColor("#4c1d95"))
        self.label.setScale(self.LABEL_SCALE)
        self.label.setZValue(13)

        self.side = "bottom" if role == "slot" else "top"
        self.update_label_position()

    def set_layout_position(self, x: float, y: float, side: str):
        self.side = side if side in VALID_PORT_SIDES else self.side
        self.setPos(x, y)
        self.update_label_position()

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

    def __init__(
        self,
        attachment: ModelSubcompAttachment,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
    ):
        super().__init__()
        self.attachment = attachment
        self.source_connector = slot_connector
        self.target_connector = interface_connector
        self.base_color = QColor("#8b5cf6")
        self.highlight_color = QColor("#f59e0b")
        self.setPen(QPen(self.base_color, 2, Qt.DashLine))
        self.setZValue(4)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.update_tooltip()
        self.update_position()

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

    def set_highlighted(self, highlighted: bool):
        if highlighted:
            self.setPen(QPen(self.highlight_color, 4, Qt.DashLine))
            self.setZValue(20)
        else:
            self.setPen(QPen(self.base_color, 2, Qt.DashLine))
            self.setZValue(4)


class AddPortsButtonItem(QGraphicsTextItem):
    def __init__(self, node: "ComponentNodeItem"):
        super().__init__("+", node)
        self.node = node
        self.setDefaultTextColor(QColor("#2563eb"))
        self.setScale(1.35)
        self.setPos(node.WIDTH - 24, node.HEIGHT - 30)
        self.setZValue(30)
        self.setAcceptHoverEvents(True)
        self.setToolTip("Add Ports")

    def mousePressEvent(self, event):
        templates = self.node.variable_port_templates

        if not templates:
            event.accept()
            return

        menu = QMenu()

        for template in templates:
            base_name = template.get("base_name", "") or template.get("name", "")
            action = menu.addAction(f"Add {base_name}")
            action.triggered.connect(
                lambda checked=False, name=base_name: self.node.increment_variable_port(
                    name
                )
            )

        menu.exec(QCursor.pos())
        event.accept()


class ComponentNodeItem(QGraphicsRectItem):
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
    ):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)

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
        self.instance_name_value = instance_name or f"{component.name}_{self.node_id}"
        self.parameters = parameters or {}
        self.variable_port_counts = {
            str(key): max(0, _safe_int(value, 1))
            for key, value in (variable_port_counts or {}).items()
        }
        self.port_templates: list[dict] = []
        self.variable_port_templates: list[dict] = []
        self.subcomp_connector_templates: list[dict] = []
        self.ports: list[PortItem] = []
        self.subcomp_connectors: list[SubcompConnectorItem] = []
        self.add_ports_button: AddPortsButtonItem | None = None
        self.icon_path = component.icon_path or ""

        self.setBrush(QBrush(QColor("#ffffff")))
        self.normal_pen = QPen(QColor("#cbd5e1"), 1.25)
        self.validation_pen = QPen(QColor("#dc2626"), 2.5)
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

    def set_instance_name(self, new_name: str):
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

    def should_add_fallback_ports(self) -> bool:
        plugin_id = getattr(self.component, "plugin_id", "") or ""

        # SST metadata is authoritative. If sst-info says a component/subcomponent
        # has zero ports, FUSE should not invent generic in/out ports.
        if plugin_id == "sst":
            return False

        return True

    def load_subcomp_connector_templates(self) -> list[dict]:
        try:
            return load_subcomp_connector_metadata_for_component(
                self.component.plugin_id,
                self.component.component_id,
                self.component.target_id,
            )
        except Exception:
            return []

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

        self.layout_subcomp_connectors()

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
        slots = [item for item in self.subcomp_connectors if item.role == "slot"]
        interfaces = [item for item in self.subcomp_connectors if item.role == "interface"]
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

    def load_port_templates(self) -> list[dict]:
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

    def expanded_port_names(self) -> list[str]:
        names: list[str] = []

        for template in self.port_templates:
            if bool(template.get("is_variable")):
                base_name = template.get("base_name", "") or template.get("name", "")
                count = max(0, _safe_int(self.variable_port_counts.get(base_name), 1))
                names.extend(f"{base_name}{index}" for index in range(count))
            else:
                names.append(template.get("name", ""))

        return [name for name in names if name]

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

        self.layout_ports(desired_names)
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
        if self.variable_port_templates and self.add_ports_button is None:
            self.add_ports_button = AddPortsButtonItem(self)
        elif not self.variable_port_templates and self.add_ports_button is not None:
            self.add_ports_button.setParentItem(None)
            self.add_ports_button = None

    def mousePressEvent(self, event):
        scene = self.scene()

        if scene is not None:
            if hasattr(scene, "select_component"):
                scene.select_component(self)

            if hasattr(scene, "begin_node_drag"):
                scene.begin_node_drag()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)

        scene = self.scene()

        if scene is not None and hasattr(scene, "end_node_drag"):
            scene.end_node_drag(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()

            if scene is not None and hasattr(scene, "reroute_links_for_node"):
                scene.reroute_links_for_node(self)
            else:
                for port in self.ports:
                    for connection in port.connections:
                        connection.update_position()

            if scene is not None and hasattr(scene, "notify_model_changed"):
                scene.notify_model_changed()

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

        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return

        pixmap = pixmap.scaled(
            self.ICON_SIZE,
            self.ICON_SIZE,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )

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
            if not bool(template.get("is_variable")):
                if template.get("name") == port_name:
                    return dict(template)
                continue

            base_name = template.get("base_name", "") or template.get("name", "")

            if port_name.startswith(base_name):
                suffix = port_name[len(base_name):]
                if suffix.isdigit():
                    metadata = dict(template)
                    metadata["expanded_name"] = port_name
                    return metadata

        return {}