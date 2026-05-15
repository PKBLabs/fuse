from routing import (
    RoutingConfig,
    route_orthogonal_path,
    route_length,
    simplify_points,
    segment_intersects_rect,
)

from typing import Optional

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsTextItem,
)

from db_access import load_port_names_for_component
from models import ComponentDefinition, ModelLink


class PortItem(QGraphicsEllipseItem):
    def __init__(self, node: "ComponentNodeItem", name: str, x: float, y: float):
        super().__init__(-5, -5, 10, 10, node)
        self.node = node
        self.name = name
        self.connections: list[ConnectionItem] = []
        self.setPos(x, y)
        self.setBrush(QBrush(QColor("#2f80ed")))
        self.setPen(QPen(QColor("#1f4e79"), 1))
        self.setFlag(QGraphicsItem.ItemSendsScenePositionChanges, True)
        self.setAcceptHoverEvents(True)
        self.setToolTip(f"Port: {name}")
        self.setZValue(10)

        label = QGraphicsTextItem(name, node)
        label.setDefaultTextColor(QColor("#333333"))
        label.setScale(0.75)

        if x <= 0:
            label.setPos(x + 8, y - 10)
        else:
            label.setPos(x - 45, y - 10)

    def scene_center(self) -> QPointF:
        return self.mapToScene(self.boundingRect().center())

    def is_connected(self) -> bool:
        """Each SST port may participate in at most one link."""
        return len(self.connections) > 0

    def update_connection_state(self):
        if self.is_connected():
            self.setBrush(QBrush(QColor("#6b7280")))
            self.setToolTip(f"Port: {self.name}\nConnected")
        else:
            self.setBrush(QBrush(QColor("#2f80ed")))
            self.setToolTip(f"Port: {self.name}")

    def mousePressEvent(self, event):
        scene = self.scene()
        if scene is not None and hasattr(scene, "port_clicked"):
            scene.port_clicked(self)
        event.accept()


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

    def __init__(self, link: ModelLink, source_port: PortItem, target_port: PortItem):
        super().__init__()
        self.link = link
        self.source_port = source_port
        self.target_port = target_port
        self.route_points: list[QPointF] = []

        self.base_color = QColor("#38bdf8")
        self.highlight_color = QColor("#f59e0b")

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
            f"latency: {self.link.latency}"
        )
        self.setToolTip(tooltip)

    def mousePressEvent(self, event):
        scene = self.scene()

        # Avoid importing ModelScene here. That would create a circular import
        # once ConnectionItem lives in graphics_items.py.
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

    def set_highlighted(self, highlighted: bool):
        if highlighted:
            self.setPen(QPen(self.highlight_color, 4))
            self.setZValue(20)
        else:
            self.setPen(QPen(self.base_color, 2))
            self.setZValue(5)

    def segment_intersects_rect(self, a: QPointF, b: QPointF, rect) -> bool:
        """
        Compatibility wrapper.

        ModelScene currently calls connection.segment_intersects_rect(...).
        Keep this wrapper so you do not have to change model_scene.py yet.
        """
        return segment_intersects_rect(a, b, rect)


class ComponentNodeItem(QGraphicsRectItem):
    WIDTH = 210
    HEIGHT = 110

    _next_node_id = 1

    def __init__(
        self,
        component: ComponentDefinition,
        node_id: Optional[int] = None,
        parameters: Optional[dict] = None,
        instance_name: Optional[str] = None,
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
        self.ports: list[PortItem] = []

        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#333333"), 1.5))
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        self.title_item = QGraphicsTextItem(self.instance_name, self)
        self.title_item.setDefaultTextColor(QColor("#111111"))
        self.title_item.setPos(10, 8)

        subtitle_text = "SubComponent" if component.is_subcomp else "Component"
        subtitle = QGraphicsTextItem(f"{component.element} · {subtitle_text}", self)
        subtitle.setDefaultTextColor(QColor("#555555"))
        subtitle.setScale(0.85)
        subtitle.setPos(10, 32)

        if component.iface:
            iface = QGraphicsTextItem(component.iface, self)
            iface.setDefaultTextColor(QColor("#666666"))
            iface.setTextWidth(self.WIDTH - 20)
            iface.setScale(0.75)
            iface.setPos(10, 54)

        self.add_ports_from_database_or_defaults()

    @property
    def instance_name(self) -> str:
        return self.instance_name_value

    def set_instance_name(self, new_name: str):
        self.instance_name_value = new_name
        self.title_item.setPlainText(new_name)

        for port in self.ports:
            for connection in port.connections:
                if connection.source_port.node is self:
                    connection.link.source_component_name = new_name
                if connection.target_port.node is self:
                    connection.link.target_component_name = new_name
                connection.update_tooltip()

    def add_ports_from_database_or_defaults(self):
        port_names = load_port_names_for_component(self.component.component_id)

        if not port_names:
            port_names = ["in", "out"]

        # Split ports across left and right sides so they are easy to connect visually.
        left_ports = port_names[::2]
        right_ports = port_names[1::2]

        if len(port_names) == 1:
            left_ports = []
            right_ports = port_names

        for index, port_name in enumerate(left_ports):
            y = self.HEIGHT * (index + 1) / (len(left_ports) + 1)
            self.ports.append(PortItem(self, port_name, 0, y))

        for index, port_name in enumerate(right_ports):
            y = self.HEIGHT * (index + 1) / (len(right_ports) + 1)
            self.ports.append(PortItem(self, port_name, self.WIDTH, y))

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

        return super().itemChange(change, value)