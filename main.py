import sys
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QPointF, QTimer
from PySide6.QtGui import QAction, QDrag, QPainter, QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QFileDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    from db_utils import (
        get_all_components_for_element,
        get_all_elements,
        get_ports_for_component,
        get_component_details,
    )
except ImportError:
    get_all_components_for_element = None
    get_all_elements = None
    get_ports_for_component = None
    get_component_details = None

try:
    from initialize_db import initialize_database
except ImportError:
    initialize_database = None


MIME_COMPONENT = "application/x-fuse-component"
SCHEMA_VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ComponentDefinition:
    element: str
    name: str
    component_id: Optional[int] = None
    is_subcomp: int = 0
    category: str = ""
    iface: str = ""

    @property
    def display_name(self) -> str:
        kind = "SubComponent" if self.is_subcomp else "Component"
        return f"{self.element}.{self.name} ({kind})"

    def to_drag_text(self) -> str:
        return "|".join(
            [
                str(self.component_id or ""),
                self.element,
                self.name,
                str(self.is_subcomp),
                self.category or "",
                self.iface or "",
            ]
        )

    @staticmethod
    def from_drag_text(text: str) -> "ComponentDefinition":
        parts = text.split("|", 5)
        while len(parts) < 6:
            parts.append("")

        component_id_text, element, name, is_subcomp, category, iface = parts

        return ComponentDefinition(
            component_id=int(component_id_text) if component_id_text else None,
            element=element,
            name=name,
            is_subcomp=int(is_subcomp or 0),
            category=category,
            iface=iface,
        )


@dataclass
class ModelLink:
    """
    One SST-style link in the model.

    This is separate from the visual line. Later this should be saved to SQLite
    and eventually exported into an SST Python config.
    """

    link_id: int
    name: str
    latency: str
    source_node_id: int
    source_component_name: str
    source_port: str
    target_node_id: int
    target_component_name: str
    target_port: str
    link_type: str = "point_to_point"


class ComponentPalette(QListWidget):
    def __init__(self):
        super().__init__()
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setDragEnabled(True)
        self.setAlternatingRowColors(True)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return

        component = item.data(Qt.UserRole)
        if component is None:
            return

        mime = QMimeData()
        mime.setData(MIME_COMPONENT, component.to_drag_text().encode("utf-8"))
        mime.setText(component.display_name)

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)

    def load_components(self):
        self.clear()

        components = load_component_definitions()

        for component in components:
            item = QListWidgetItem(component.display_name)
            item.setData(Qt.UserRole, component)
            self.addItem(item)


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
        if isinstance(scene, ModelScene):
            scene.port_clicked(self)
        event.accept()


class ConnectionItem(QGraphicsPathItem):
    """
    Visual rendering of one SST ModelLink.

    Links are first-class model entities. The path below is only the visual
    route for that entity. Routing rules:
    - avoid component/subcomponent boxes
    - allow crossing other links at points
    - avoid running on top of, or very close to, other links for long distances
    - keep a small clearance around boxes so links do not hug component edges
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

        # Point-to-point links are first-class model objects. Use a distinct
        # color so they are visually different from future multi-endpoint/bus
        # links.
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

        if isinstance(scene, ModelScene):
            scene.select_link(self)

        super().mousePressEvent(event)

    def node_body_rect(self, node: "ComponentNodeItem"):
        # Only the actual drawn component rectangle. Do not use sceneBoundingRect()
        # because it includes ports/text/selection decoration.
        return node.mapRectToScene(node.rect())

    def route_obstacle_rects(self):
        scene = self.scene()
        if scene is None:
            return []

        rects = []
        pad = self.ROUTE_CLEARANCE

        for item in scene.items():
            if isinstance(item, ComponentNodeItem):
                rects.append(self.node_body_rect(item).adjusted(-pad, -pad, pad, pad))

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
        # Deterministic per-link lane ordering, alternating sides.
        lanes = [0, 1, -1, 2, -2, 3, -3, 4, -4]
        return lanes[(self.link.link_id - 1) % len(lanes)]

    def outward_lane_distance(self) -> float:
        return abs(self.lane_index()) * self.LANE_SPACING

    def exit_point_for_port(self, port: PortItem) -> QPointF:
        """
        Return a route start/end point safely outside the padded obstacle rect.

        The rendered path goes:
            actual port dot -> this exit point -> routed path -> other exit point -> other port dot

        Because this point is outside the padded obstacle, the router does not
        need to pass through component boxes or ride along their edges.
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

    @staticmethod
    def same_x(a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) < 0.001

    @staticmethod
    def same_y(a: QPointF, b: QPointF) -> bool:
        return abs(a.y() - b.y()) < 0.001

    def is_orthogonal_segment(self, a: QPointF, b: QPointF) -> bool:
        return self.same_x(a, b) or self.same_y(a, b)

    def segment_intersects_rect(self, a: QPointF, b: QPointF, rect) -> bool:
        # Only Manhattan segments are valid in this router.
        if self.same_x(a, b):
            x = a.x()
            y1 = min(a.y(), b.y())
            y2 = max(a.y(), b.y())
            return rect.left() < x < rect.right() and not (y2 <= rect.top() or y1 >= rect.bottom())

        if self.same_y(a, b):
            y = a.y()
            x1 = min(a.x(), b.x())
            x2 = max(a.x(), b.x())
            return rect.top() < y < rect.bottom() and not (x2 <= rect.left() or x1 >= rect.right())

        return True

    def segment_is_clear(self, a: QPointF, b: QPointF, rects) -> bool:
        if not self.is_orthogonal_segment(a, b):
            return False

        return not any(self.segment_intersects_rect(a, b, rect) for rect in rects)

    def route_is_clear(self, points: list[QPointF], rects) -> bool:
        for a, b in zip(points, points[1:]):
            if not self.segment_is_clear(a, b, rects):
                return False
        return True

    @staticmethod
    def route_length(points: list[QPointF]) -> float:
        return sum(
            abs(a.x() - b.x()) + abs(a.y() - b.y())
            for a, b in zip(points, points[1:])
        )

    def simplify_points(self, points: list[QPointF]) -> list[QPointF]:
        if not points:
            return []

        simplified: list[QPointF] = []

        for point in points:
            if not simplified:
                simplified.append(point)
                continue

            previous = simplified[-1]
            if self.same_x(previous, point) and self.same_y(previous, point):
                continue

            simplified.append(point)

            while len(simplified) >= 3:
                a = simplified[-3]
                b = simplified[-2]
                c = simplified[-1]

                # A -> B -> A spike.
                if self.same_x(a, c) and self.same_y(a, c):
                    simplified.pop(-2)
                    simplified.pop(-1)
                    continue

                # Collinear middle point.
                if self.same_x(a, b) and self.same_x(b, c):
                    simplified.pop(-2)
                    continue

                if self.same_y(a, b) and self.same_y(b, c):
                    simplified.pop(-2)
                    continue

                break

        return simplified

    @staticmethod
    def segment_near_overlap_penalty(a: QPointF, b: QPointF, c: QPointF, d: QPointF) -> float:
        tolerance = 0.001
        minimum_spacing = 18.0
        minimum_meaningful_overlap = 6.0

        # Horizontal near-overlap.
        if abs(a.y() - b.y()) < tolerance and abs(c.y() - d.y()) < tolerance:
            distance = abs(a.y() - c.y())
            if distance >= minimum_spacing:
                return 0.0

            a1, a2 = sorted([a.x(), b.x()])
            c1, c2 = sorted([c.x(), d.x()])
            overlap = max(0.0, min(a2, c2) - max(a1, c1))

            if overlap <= minimum_meaningful_overlap:
                return 0.0

            return 3000.0 + overlap * 100.0 + (minimum_spacing - distance) * 250.0

        # Vertical near-overlap.
        if abs(a.x() - b.x()) < tolerance and abs(c.x() - d.x()) < tolerance:
            distance = abs(a.x() - c.x())
            if distance >= minimum_spacing:
                return 0.0

            a1, a2 = sorted([a.y(), b.y()])
            c1, c2 = sorted([c.y(), d.y()])
            overlap = max(0.0, min(a2, c2) - max(a1, c1))

            if overlap <= minimum_meaningful_overlap:
                return 0.0

            return 3000.0 + overlap * 100.0 + (minimum_spacing - distance) * 250.0

        return 0.0

    def segment_overlap_penalty(self, a: QPointF, b: QPointF) -> float:
        scene = self.scene()
        if scene is None:
            return 0.0

        penalty = 0.0

        for item in scene.items():
            if not isinstance(item, ConnectionItem) or item is self:
                continue

            other_points = getattr(item, "route_points", [])
            if not other_points:
                continue

            for c, d in zip(other_points, other_points[1:]):
                penalty += self.segment_near_overlap_penalty(a, b, c, d)

        return penalty

    def build_route_grid(self, start: QPointF, end: QPointF, rects) -> tuple[dict, dict]:
        """
        Build a visibility-style Manhattan grid from obstacle edges plus start/end.
        """
        lane_extra = self.outward_lane_distance()
        offsets = [
            self.ROUTE_CLEARANCE,
            self.ROUTE_CLEARANCE + self.LANE_SPACING,
            self.ROUTE_CLEARANCE + lane_extra + self.LANE_SPACING,
            self.ROUTE_CLEARANCE + lane_extra + self.LANE_SPACING * 3,
        ]

        xs = {start.x(), end.x()}
        ys = {start.y(), end.y()}

        for rect in rects:
            for offset in offsets:
                xs.add(rect.left() - offset)
                xs.add(rect.right() + offset)
                ys.add(rect.top() - offset)
                ys.add(rect.bottom() + offset)

        # Give local start/end rows and columns priority too.
        xs.update([start.x() - self.LANE_SPACING, start.x() + self.LANE_SPACING])
        xs.update([end.x() - self.LANE_SPACING, end.x() + self.LANE_SPACING])
        ys.update([start.y() - self.LANE_SPACING, start.y() + self.LANE_SPACING])
        ys.update([end.y() - self.LANE_SPACING, end.y() + self.LANE_SPACING])

        def key(point: QPointF) -> tuple[float, float]:
            return (round(point.x(), 3), round(point.y(), 3))

        point_by_key: dict[tuple[float, float], QPointF] = {}

        for x in sorted(xs):
            for y in sorted(ys):
                point = QPointF(x, y)
                if not any(rect.contains(point) for rect in rects):
                    point_by_key[key(point)] = point

        point_by_key[key(start)] = start
        point_by_key[key(end)] = end

        neighbors: dict[tuple[float, float], list[tuple[float, float]]] = {
            item_key: [] for item_key in point_by_key
        }

        row_points: dict[float, list[QPointF]] = {}
        col_points: dict[float, list[QPointF]] = {}

        for point in point_by_key.values():
            row_points.setdefault(round(point.y(), 3), []).append(point)
            col_points.setdefault(round(point.x(), 3), []).append(point)

        for row in row_points.values():
            row.sort(key=lambda point: point.x())
            for a, b in zip(row, row[1:]):
                if self.segment_is_clear(a, b, rects):
                    neighbors[key(a)].append(key(b))
                    neighbors[key(b)].append(key(a))

        for col in col_points.values():
            col.sort(key=lambda point: point.y())
            for a, b in zip(col, col[1:]):
                if self.segment_is_clear(a, b, rects):
                    neighbors[key(a)].append(key(b))
                    neighbors[key(b)].append(key(a))

        return point_by_key, neighbors

    def find_grid_route(self, start: QPointF, end: QPointF, rects) -> list[QPointF] | None:
        import heapq
        from itertools import count

        def key(point: QPointF) -> tuple[float, float]:
            return (round(point.x(), 3), round(point.y(), 3))

        def manhattan(a: QPointF, b: QPointF) -> float:
            return abs(a.x() - b.x()) + abs(a.y() - b.y())

        point_by_key, neighbors = self.build_route_grid(start, end, rects)
        start_key = key(start)
        end_key = key(end)

        sequence = count()
        frontier = [(0.0, next(sequence), start_key, None)]
        came_from: dict[tuple[float, float], tuple[float, float] | None] = {start_key: None}
        cost_so_far = {start_key: 0.0}
        direction_so_far: dict[tuple[float, float], str | None] = {start_key: None}

        while frontier:
            _, _, current_key, previous_direction = heapq.heappop(frontier)

            if current_key == end_key:
                break

            current_point = point_by_key[current_key]

            for next_key in neighbors.get(current_key, []):
                next_point = point_by_key[next_key]
                direction = "h" if self.same_y(current_point, next_point) else "v"
                bend_penalty = 0.0

                if previous_direction is not None and direction != previous_direction:
                    bend_penalty = 18.0

                segment_cost = manhattan(current_point, next_point)
                # Do not run expensive overlap avoidance during interactive routing.
                # Point-to-point links remain distinct model objects; visual
                # selection/highlighting makes ownership clear without requiring
                # the router to solve global lane packing on every move.
                overlap_penalty = 0.0
                new_cost = cost_so_far[current_key] + segment_cost + bend_penalty + overlap_penalty

                if next_key not in cost_so_far or new_cost < cost_so_far[next_key]:
                    cost_so_far[next_key] = new_cost
                    direction_so_far[next_key] = direction
                    priority = new_cost + manhattan(next_point, end)
                    heapq.heappush(frontier, (priority, next(sequence), next_key, direction))
                    came_from[next_key] = current_key

        if end_key not in came_from:
            return None

        route_keys = []
        current = end_key

        while current is not None:
            route_keys.append(current)
            current = came_from[current]

        route_keys.reverse()
        route = [point_by_key[item] for item in route_keys]
        return self.simplify_points(route)

    def fallback_route(self, start: QPointF, end: QPointF, rects) -> list[QPointF]:
        # Large outside perimeter fallback. This should rarely be used, but it is
        # finite and avoids UI hangs.
        margin = self.ROUTE_CLEARANCE + self.EXIT_MARGIN + self.outward_lane_distance() + 240

        if rects:
            left = min(rect.left() for rect in rects) - margin
            right = max(rect.right() for rect in rects) + margin
            top = min(rect.top() for rect in rects) - margin
            bottom = max(rect.bottom() for rect in rects) + margin
        else:
            left = min(start.x(), end.x()) - margin
            right = max(start.x(), end.x()) + margin
            top = min(start.y(), end.y()) - margin
            bottom = max(start.y(), end.y()) + margin

        candidates = [
            [start, QPointF(left, start.y()), QPointF(left, top), QPointF(end.x(), top), end],
            [start, QPointF(right, start.y()), QPointF(right, top), QPointF(end.x(), top), end],
            [start, QPointF(left, start.y()), QPointF(left, bottom), QPointF(end.x(), bottom), end],
            [start, QPointF(right, start.y()), QPointF(right, bottom), QPointF(end.x(), bottom), end],
        ]

        valid = [self.simplify_points(route) for route in candidates if self.route_is_clear(route, rects)]

        if valid:
            return min(valid, key=lambda route: self.route_length(route) + self.route_overlap_penalty(route))

        return self.simplify_points([start, QPointF(start.x(), end.y()), end])

    def route_overlap_penalty(self, points: list[QPointF]) -> float:
        return sum(
            self.segment_overlap_penalty(a, b)
            for a, b in zip(points, points[1:])
        )

    def routed_points(self) -> list[QPointF]:
        source_center = self.source_port.scene_center()
        target_center = self.target_port.scene_center()
        source_exit = self.exit_point_for_port(self.source_port)
        target_exit = self.exit_point_for_port(self.target_port)
        rects = self.route_obstacle_rects()

        route = self.find_grid_route(source_exit, target_exit, rects)

        if route is None:
            route = self.fallback_route(source_exit, target_exit, rects)

        return self.simplify_points([source_center, *route, target_center])

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

        The full router is intentionally careful and can be expensive for dense
        models. While dragging, use a simple orthogonal preview, but still leave
        each endpoint through its correct side. This prevents the preview line
        from visibly cutting through the component currently being dragged.
        """
        source = self.source_port.scene_center()
        target = self.target_port.scene_center()
        source_exit = self.exit_point_for_port(self.source_port)
        target_exit = self.exit_point_for_port(self.target_port)

        # Choose a simple dogleg between the two safe endpoint exits.
        # Prefer the shorter of the two one-bend options.
        route_a = self.simplify_points(
            [
                source,
                source_exit,
                QPointF(source_exit.x(), target_exit.y()),
                target_exit,
                target,
            ]
        )
        route_b = self.simplify_points(
            [
                source,
                source_exit,
                QPointF(target_exit.x(), source_exit.y()),
                target_exit,
                target,
            ]
        )

        points = route_a if self.route_length(route_a) <= self.route_length(route_b) else route_b
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
        if isinstance(scene, ModelScene):
            scene.select_component(self)
            scene.begin_node_drag()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        scene = self.scene()
        if isinstance(scene, ModelScene):
            scene.end_node_drag(self)

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            scene = self.scene()

            if isinstance(scene, ModelScene):
                scene.reroute_links_for_node(self)
            else:
                for port in self.ports:
                    for connection in port.connections:
                        connection.update_position()

        return super().itemChange(change, value)


class ModelScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2000, 1500)
        self.pending_source_port: Optional[PortItem] = None
        self.pending_line: Optional[QGraphicsLineItem] = None
        self.properties_panel: Optional[PropertiesPanel] = None
        self.links: list[ModelLink] = []
        self._next_link_id = 1

        # Link routing is relatively expensive. A component drag can generate
        # hundreds of ItemPositionHasChanged events per second. During drag we
        # use cheap preview routing, then do one full reroute on release.
        self._dragging_node = False
        self._reroute_timer = QTimer()
        self._reroute_timer.setSingleShot(True)
        self._reroute_timer.setInterval(250)
        self._reroute_timer.timeout.connect(self.reroute_all_links)

    def connection_items(self) -> list[ConnectionItem]:
        items = [item for item in self.items() if isinstance(item, ConnectionItem)]
        return sorted(items, key=lambda item: item.link.link_id)

    def component_items(self) -> list[ComponentNodeItem]:
        items = [item for item in self.items() if isinstance(item, ComponentNodeItem)]
        return sorted(items, key=lambda item: item.node_id)

    def clear_model(self):
        self.cancel_pending_connection()
        self.clear()
        self.links = []
        self._next_link_id = 1
        ComponentNodeItem._next_node_id = 1

    def find_port(self, node_id: int, port_name: str) -> Optional[PortItem]:
        for node in self.component_items():
            if node.node_id != node_id:
                continue

            for port in node.ports:
                if port.name == port_name:
                    return port

        return None

    def clear_link_highlights(self):
        for connection in self.connection_items():
            connection.set_highlighted(False)

    def highlight_links_for_node(self, node: "ComponentNodeItem"):
        for connection in self.connection_items():
            connection.set_highlighted(connection.is_connected_to_node(node))

    def select_component(self, node: "ComponentNodeItem"):
        self.highlight_links_for_node(node)

        if self.properties_panel is not None:
            self.properties_panel.show_component(node)

    def select_link(self, connection: ConnectionItem):
        self.clear_link_highlights()
        connection.set_highlighted(True)

        if self.properties_panel is not None:
            self.properties_panel.show_link(connection)

    def begin_node_drag(self):
        self._dragging_node = True
        self._reroute_timer.stop()

    def end_node_drag(self, node: Optional["ComponentNodeItem"] = None):
        """
        End an interactive drag.

        Scalability rule: do NOT reroute the entire model automatically here.
        Instead, reroute:
          1. links attached to the moved node, and
          2. existing links whose current route now intersects the moved node box.

        This catches the common case where moving a component causes unrelated
        links to pass through it, without paying the cost of rerouting every link
        in a large model.
        """
        self._dragging_node = False

        if node is not None:
            self.reroute_links_affected_by_node(node)

    def request_reroute_all_links(self):
        """
        Schedule a full reroute shortly in the future.

        Do not full-reroute while a node is actively being dragged. That is what
        caused multi-second UI freezes in dense models.
        """
        if self._dragging_node:
            return

        self._reroute_timer.start()

    def reroute_all_links(self):
        """
        Recompute link paths in link-id order.

        This gives later links a chance to avoid the exact segments already
        chosen by earlier links. It also refreshes routes after components move.
        """
        connections = self.connection_items()

        for connection in connections:
            connection.clear_route_points()

        for connection in connections:
            connection.update_position()

    def reroute_links_for_node(self, node: "ComponentNodeItem", force_full: bool = False):
        """
        Update only links attached to a node.

        This is the scalable default during drag.
        """
        for connection in self.links_attached_to_node(node):
            if self._dragging_node and not force_full:
                connection.update_position_fast()
            else:
                connection.update_position()

    def links_attached_to_node(self, node: "ComponentNodeItem") -> set[ConnectionItem]:
        seen: set[ConnectionItem] = set()

        for port in node.ports:
            for connection in port.connections:
                seen.add(connection)

        return seen

    def link_route_intersects_node(self, connection: ConnectionItem, node: "ComponentNodeItem") -> bool:
        """
        Return True if an existing rendered link path crosses the moved node's
        padded box. This lets us reroute only the links that were made invalid
        by the move.
        """
        if not connection.route_points:
            return False

        # Use the same clearance concept as ConnectionItem's router.
        pad = ConnectionItem.ROUTE_CLEARANCE
        rect = connection.node_body_rect(node).adjusted(-pad, -pad, pad, pad)

        for a, b in zip(connection.route_points, connection.route_points[1:]):
            if connection.segment_intersects_rect(a, b, rect):
                return True

        return False

    def reroute_links_affected_by_node(self, node: "ComponentNodeItem"):
        """
        Reroute links attached to the moved node plus unrelated links whose
        current path now crosses the moved node.
        """
        affected = self.links_attached_to_node(node)

        for connection in self.connection_items():
            if connection in affected:
                continue

            if self.link_route_intersects_node(connection, node):
                affected.add(connection)

        # Clear affected route_points first so the overlap-avoidance penalty does
        # not compare a link against its own stale path.
        for connection in affected:
            connection.clear_route_points()

        for connection in sorted(affected, key=lambda item: item.link.link_id):
            connection.update_position()

    def port_clicked(self, port: PortItem):
        """
        Two-click connection behavior:
        - click source port
        - click target port
        - create a persistent SST-style link entity and a visual line

        Important SST modeling rule for this editor:
        one port can be connected to at most one other port. Therefore a link is
        a 1-to-1 relationship between exactly two currently-unconnected ports.
        """
        if self.pending_source_port is None:
            if port.is_connected():
                QMessageBox.information(
                    None,
                    "Port Already Connected",
                    f"Port '{port.name}' is already connected to a link.",
                )
                return

            self.begin_connection(port)
            return

        if port is self.pending_source_port:
            self.cancel_pending_connection()
            return

        if port.is_connected():
            QMessageBox.information(
                None,
                "Port Already Connected",
                f"Port '{port.name}' is already connected to a link.",
            )
            return

        self.finish_connection(port)

    def begin_connection(self, source_port: PortItem):
        self.cancel_pending_connection()

        if source_port.is_connected():
            QMessageBox.information(
                None,
                "Port Already Connected",
                f"Port '{source_port.name}' is already connected to a link.",
            )
            return

        self.pending_source_port = source_port
        self.pending_line = QGraphicsLineItem()
        self.pending_line.setPen(QPen(QColor("#888888"), 2, Qt.DashLine))
        # Keep the temporary line above boxes but below ports.
        self.pending_line.setZValue(4)
        self.pending_line.setAcceptedMouseButtons(Qt.NoButton)
        start = source_port.scene_center()
        self.pending_line.setLine(start.x(), start.y(), start.x(), start.y())
        self.addItem(self.pending_line)

    def finish_connection(self, target_port: PortItem):
        if self.pending_source_port is None:
            return

        source_port = self.pending_source_port

        if source_port.is_connected():
            self.cancel_pending_connection()
            QMessageBox.information(
                None,
                "Port Already Connected",
                f"Source port '{source_port.name}' is already connected to a link.",
            )
            return

        if target_port.is_connected():
            QMessageBox.information(
                None,
                "Port Already Connected",
                f"Target port '{target_port.name}' is already connected to a link.",
            )
            return

        self.cancel_pending_visual_line_only()

        latency, accepted = QInputDialog.getText(
            None,
            "Create SST Link",
            "Latency for this link:",
            text="1ns",
        )

        if not accepted:
            self.pending_source_port = None
            return

        latency = latency.strip() or "1ns"
        link_id = self._next_link_id
        self._next_link_id += 1

        link = ModelLink(
            link_id=link_id,
            name=f"link_{link_id}",
            latency=latency,
            source_node_id=source_port.node.node_id,
            source_component_name=source_port.node.instance_name,
            source_port=source_port.name,
            target_node_id=target_port.node.node_id,
            target_component_name=target_port.node.instance_name,
            target_port=target_port.name,
        )

        self.links.append(link)

        connection = ConnectionItem(link, source_port, target_port)
        self.addItem(connection)
        # Route only the newly-created link. Do not global-reroute the model here;
        # that becomes very expensive as the model grows.
        connection.update_position()

        self.pending_source_port = None

    def cancel_pending_visual_line_only(self):
        if self.pending_line is not None:
            self.removeItem(self.pending_line)
            self.pending_line = None

    def cancel_pending_connection(self):
        self.cancel_pending_visual_line_only()
        self.pending_source_port = None

    def mouseMoveEvent(self, event):
        if self.pending_line is not None and self.pending_source_port is not None:
            start = self.pending_source_port.scene_center()
            end = event.scenePos()
            self.pending_line.setLine(start.x(), start.y(), end.x(), end.y())
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        clicked_items = self.items(event.scenePos())

        clicked_a_port = any(isinstance(item, PortItem) for item in clicked_items)
        clicked_a_component = any(isinstance(item, ComponentNodeItem) for item in clicked_items)
        clicked_a_link = any(isinstance(item, ConnectionItem) for item in clicked_items)

        # Clicking empty canvas cancels pending link creation and clears link
        # highlights.
        if self.pending_source_port is not None and not clicked_a_port:
            self.cancel_pending_connection()

        if not clicked_a_port and not clicked_a_component and not clicked_a_link:
            self.clear_link_highlights()

            if self.properties_panel is not None:
                self.properties_panel.show_empty()

        super().mousePressEvent(event)


class ModelView(QGraphicsView):
    def __init__(self, scene: ModelScene):
        super().__init__(scene)
        self.setAcceptDrops(True)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)

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
        node = ComponentNodeItem(component)
        node.setPos(scene_pos)
        self.scene().addItem(node)

        event.acceptProposedAction()


class PropertiesPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.current_node: Optional[ComponentNodeItem] = None
        self.current_link: Optional[ConnectionItem] = None
        self._loading = False

        layout = QVBoxLayout(self)

        self.title = QLabel("Nothing selected")
        self.title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.title)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Property", "Value"])
        self.tree.itemChanged.connect(self.on_item_changed)
        layout.addWidget(self.tree)

    def show_empty(self):
        self._loading = True
        self.current_node = None
        self.current_link = None
        self.title.setText("Nothing selected")
        self.tree.clear()
        self._loading = False

    def add_category(self, name: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name, ""])
        item.setFirstColumnSpanned(True)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.tree.addTopLevelItem(item)
        item.setExpanded(True)
        return item

    def add_property(
        self,
        parent: QTreeWidgetItem,
        name: str,
        value: str,
        key: str,
        editable: bool = True,
        metadata: Optional[dict] = None,
    ):
        item = QTreeWidgetItem([name, value])
        item.setData(0, Qt.UserRole, key)
        item.setData(1, Qt.UserRole, metadata or {})
        item.setData(1, Qt.UserRole + 1, value)

        flags = item.flags()
        if editable:
            flags |= Qt.ItemIsEditable
        else:
            flags &= ~Qt.ItemIsEditable
        item.setFlags(flags)

        parent.addChild(item)
        return item

    def show_component(self, node: ComponentNodeItem):
        self._loading = True
        self.current_node = node
        self.current_link = None
        self.title.setText("Component Instance")
        self.tree.clear()

        component = node.component

        object_group = self.add_category("Object")
        self.add_property(object_group, "Name", node.instance_name, "component.name", editable=True)
        self.add_property(
            object_group,
            "Kind",
            "SubComponent" if component.is_subcomp else "Component",
            "component.kind",
            editable=False,
        )
        self.add_property(object_group, "Element", component.element, "component.element", editable=False)
        self.add_property(object_group, "Component Type", component.name, "component.type", editable=False)
        self.add_property(object_group, "Interface", component.iface or "", "component.iface", editable=False)

        parameters_group = self.add_category("Parameters")

        for parameter in self.load_component_parameters(component.component_id):
            name = parameter.get("name", "")
            default_value = parameter.get("default_val", "")
            required = bool(parameter.get("required"))

            if default_value == "<required>":
                default_value = ""

            value = node.parameters.get(name, default_value)

            self.add_property(
                parameters_group,
                name,
                str(value),
                f"component.parameter.{name}",
                editable=True,
                metadata={
                    "name": name,
                    "required": required,
                    "default_val": default_value,
                    "description": parameter.get("description", ""),
                },
            )

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._loading = False

    def show_link(self, connection: ConnectionItem):
        self._loading = True
        self.current_node = None
        self.current_link = connection
        self.title.setText("Point-to-Point Link")
        self.tree.clear()

        link = connection.link

        object_group = self.add_category("Object")
        self.add_property(object_group, "Name", link.name, "link.name", editable=True)
        self.add_property(object_group, "Type", link.link_type, "link.type", editable=False)
        self.add_property(
            object_group,
            "Source",
            f"{link.source_component_name}.{link.source_port}",
            "link.source",
            editable=False,
        )
        self.add_property(
            object_group,
            "Target",
            f"{link.target_component_name}.{link.target_port}",
            "link.target",
            editable=False,
        )

        parameters_group = self.add_category("Parameters")
        self.add_property(
            parameters_group,
            "latency",
            link.latency,
            "link.parameter.latency",
            editable=True,
            metadata={
                "name": "latency",
                "required": True,
                "type": "latency",
            },
        )

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._loading = False

    def load_component_parameters(self, component_id: Optional[int]) -> list[dict]:
        if component_id is None or get_component_details is None:
            return []

        try:
            details = get_component_details(component_id)
        except Exception as exc:
            print(f"Failed to load component details for {component_id}: {exc}")
            return []

        if not details:
            return []

        return details.get("parameters", [])

    def on_item_changed(self, item: QTreeWidgetItem, column: int):
        if self._loading or column != 1:
            return

        key = item.data(0, Qt.UserRole)
        metadata = item.data(1, Qt.UserRole) or {}
        old_value = item.data(1, Qt.UserRole + 1)
        new_value = item.text(1).strip()

        valid, message = self.validate_value(key, new_value, metadata)

        if not valid:
            QMessageBox.warning(self, "Invalid Value", message)
            self._loading = True
            item.setText(1, old_value)
            self._loading = False
            return

        if key == "component.name" and self.current_node is not None:
            self.current_node.set_instance_name(new_value)

        elif key == "link.name" and self.current_link is not None:
            self.current_link.link.name = new_value
            self.current_link.update_tooltip()

        elif key == "link.parameter.latency" and self.current_link is not None:
            self.current_link.link.latency = new_value
            self.current_link.update_tooltip()

        elif isinstance(key, str) and key.startswith("component.parameter.") and self.current_node is not None:
            parameter_name = metadata.get("name")
            if parameter_name:
                self.current_node.parameters[parameter_name] = new_value

        item.setData(1, Qt.UserRole + 1, new_value)

    def validate_value(self, key: str, value: str, metadata: dict) -> tuple[bool, str]:
        if key in {"component.name", "link.name"}:
            if not value:
                return False, "Name cannot be empty."

            if not self.name_is_unique(value):
                return False, f"The name '{value}' is already used. Enter a unique name."

            return True, ""

        if metadata.get("required", False) and not value:
            return False, "This parameter is required."

        if metadata.get("type") == "latency":
            valid_suffixes = ("fs", "ps", "ns", "us", "ms", "s")
            if not value.endswith(valid_suffixes):
                return False, "Latency should end with a time unit such as ps, ns, us, ms, or s."
            return True, ""

        default_value = metadata.get("default_val", "")

        if default_value and value:
            if self.looks_like_int(default_value) and not self.looks_like_int(value):
                return False, "This value should be an integer."

            if self.looks_like_float(default_value) and not self.looks_like_float(value):
                return False, "This value should be numeric."

        return True, ""

    def name_is_unique(self, name: str) -> bool:
        scene = None

        if self.current_node is not None:
            scene = self.current_node.scene()

        if self.current_link is not None:
            scene = self.current_link.scene()

        if not isinstance(scene, ModelScene):
            return True

        for item in scene.items():
            if isinstance(item, ComponentNodeItem):
                if item is self.current_node:
                    continue
                if item.instance_name == name:
                    return False

            if isinstance(item, ConnectionItem):
                if item is self.current_link:
                    continue
                if item.link.name == name:
                    return False

        return True

    @staticmethod
    def looks_like_int(value: str) -> bool:
        try:
            int(value)
            return True
        except ValueError:
            return False

    @staticmethod
    def looks_like_float(value: str) -> bool:
        try:
            float(value)
            return True
        except ValueError:
            return False


def component_node_to_save_dict(node: ComponentNodeItem) -> dict:
    position = node.pos()

    return {
        "id": node.node_id,
        "element": node.component.element,
        "name": node.component.name,
        "componentId": node.component.component_id,
        "isSubcomponent": node.component.is_subcomp,
        "category": node.component.category,
        "interface": node.component.iface,
        "instanceName": node.instance_name,
        "parameters": node.parameters,
        "position": {
            "x": position.x(),
            "y": position.y(),
        },
    }


def model_link_to_save_dict(link: ModelLink) -> dict:
    return {
        "id": link.link_id,
        "name": link.name,
        "latency": link.latency,
        "type": link.link_type,
        "source": {
            "nodeId": link.source_node_id,
            "componentName": link.source_component_name,
            "port": link.source_port,
        },
        "target": {
            "nodeId": link.target_node_id,
            "componentName": link.target_component_name,
            "port": link.target_port,
        },
    }


def build_project_dict(scene: ModelScene, model_view: ModelView, project_name: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": {
            "name": project_name or "Untitled SST Model",
            "updatedAt": now_iso(),
        },
        "components": [
            component_node_to_save_dict(node)
            for node in scene.component_items()
        ],
        "links": [
            model_link_to_save_dict(link)
            for link in sorted(scene.links, key=lambda item: item.link_id)
        ],
        "editor": {
            "sceneRect": {
                "x": scene.sceneRect().x(),
                "y": scene.sceneRect().y(),
                "width": scene.sceneRect().width(),
                "height": scene.sceneRect().height(),
            },
            "viewCenter": {
                "x": model_view.mapToScene(model_view.viewport().rect().center()).x(),
                "y": model_view.mapToScene(model_view.viewport().rect().center()).y(),
            },
        },
    }


def validate_project_dict(project: dict) -> None:
    if not isinstance(project, dict):
        raise ValueError("Invalid project file: root must be a JSON object.")

    if project.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schemaVersion: {project.get('schemaVersion')!r}"
        )

    if not isinstance(project.get("components"), list):
        raise ValueError("Invalid project file: missing components list.")

    if not isinstance(project.get("links"), list):
        raise ValueError("Invalid project file: missing links list.")


def load_project_file(file_path: str | Path) -> dict:
    with Path(file_path).open("r", encoding="utf-8") as file:
        project = json.load(file)

    validate_project_dict(project)
    return project


def save_project_file(project: dict, file_path: str | Path) -> None:
    with Path(file_path).open("w", encoding="utf-8") as file:
        json.dump(project, file, indent=2)
        file.write("\n")


def load_project_into_scene(project: dict, scene: ModelScene) -> None:
    validate_project_dict(project)
    scene.clear_model()

    nodes_by_id: dict[int, ComponentNodeItem] = {}

    for component_data in project["components"]:
        component = ComponentDefinition(
            component_id=component_data.get("componentId"),
            element=component_data.get("element", ""),
            name=component_data.get("name", ""),
            is_subcomp=int(component_data.get("isSubcomponent", 0)),
            category=component_data.get("category", ""),
            iface=component_data.get("interface", ""),
        )

        node_id = int(component_data["id"])
        node = ComponentNodeItem(
            component,
            node_id=node_id,
            parameters=component_data.get("parameters", {}),
            instance_name=component_data.get("instanceName"),
        )

        position = component_data.get("position", {})
        node.setPos(float(position.get("x", 0)), float(position.get("y", 0)))

        scene.addItem(node)
        nodes_by_id[node_id] = node

    max_link_id = 0

    for link_data in project["links"]:
        source = link_data.get("source", {})
        target = link_data.get("target", {})

        source_node_id = int(source["nodeId"])
        target_node_id = int(target["nodeId"])
        source_port_name = source["port"]
        target_port_name = target["port"]

        source_port = scene.find_port(source_node_id, source_port_name)
        target_port = scene.find_port(target_node_id, target_port_name)

        if source_port is None:
            raise ValueError(
                f"Could not restore link {link_data.get('name')}: "
                f"missing source port {source_node_id}.{source_port_name}"
            )

        if target_port is None:
            raise ValueError(
                f"Could not restore link {link_data.get('name')}: "
                f"missing target port {target_node_id}.{target_port_name}"
            )

        link_id = int(link_data["id"])
        max_link_id = max(max_link_id, link_id)

        link = ModelLink(
            link_id=link_id,
            name=link_data.get("name", f"link_{link_id}"),
            latency=link_data.get("latency", "1ns"),
            source_node_id=source_node_id,
            source_component_name=source.get(
                "componentName",
                nodes_by_id[source_node_id].instance_name,
            ),
            source_port=source_port_name,
            target_node_id=target_node_id,
            target_component_name=target.get(
                "componentName",
                nodes_by_id[target_node_id].instance_name,
            ),
            target_port=target_port_name,
            link_type=link_data.get("type", "point_to_point"),
        )

        scene.links.append(link)
        connection = ConnectionItem(link, source_port, target_port)
        scene.addItem(connection)
        connection.update_position()

    scene._next_link_id = max_link_id + 1
    scene.reroute_all_links()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FUSE SST Model Builder")
        self.resize(1300, 800)

        self.current_project_path: Optional[Path] = None
        self.project_name = "Untitled SST Model"

        self.palette = ComponentPalette()
        self.scene = ModelScene()
        self.model_view = ModelView(self.scene)
        self.properties_panel = PropertiesPanel()
        self.scene.properties_panel = self.properties_panel

        self.setup_menu_bar()
        self.setup_layout()
        self.setup_properties_panel()
        self.setup_status_bar()

        ensure_database_ready()
        self.palette.load_components()

    def setup_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        tools_menu = menu_bar.addMenu("Tools")
        help_menu = menu_bar.addMenu("Help")

        new_action = QAction("New Model", self)
        open_action = QAction("Open...", self)
        save_action = QAction("Save", self)
        save_as_action = QAction("Save As...", self)
        exit_action = QAction("Exit", self)

        new_action.triggered.connect(self.new_model)
        open_action.triggered.connect(self.open_model)
        save_action.triggered.connect(self.save_model)
        save_as_action.triggered.connect(self.save_model_as)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        refresh_action = QAction("Refresh Component List", self)
        refresh_action.triggered.connect(self.palette.load_components)
        tools_menu.addAction(refresh_action)

        show_links_action = QAction("Show Links", self)
        show_links_action.triggered.connect(self.show_links)
        tools_menu.addAction(show_links_action)

        reroute_all_action = QAction("Reroute All Links", self)
        reroute_all_action.triggered.connect(self.scene.reroute_all_links)
        tools_menu.addAction(reroute_all_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        edit_menu.addAction(QAction("Undo", self))
        edit_menu.addAction(QAction("Redo", self))
        view_menu.addAction(QAction("Zoom In", self))
        view_menu.addAction(QAction("Zoom Out", self))

    def setup_layout(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("Available Components"))
        left_layout.addWidget(self.palette)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.model_view)
        splitter.setSizes([320, 980])

        self.setCentralWidget(splitter)

    def setup_properties_panel(self):
        dock = QDockWidget("Properties", self)
        dock.setWidget(self.properties_panel)
        dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
            | Qt.TopDockWidgetArea
            | Qt.BottomDockWidgetArea
        )
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def setup_status_bar(self):
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def project_dict(self) -> dict:
        return build_project_dict(self.scene, self.model_view, self.project_name)

    def validate_model_before_save(self) -> bool:
        used_names = set()

        for node in self.scene.component_items():
            if not node.instance_name:
                QMessageBox.warning(self, "Invalid Model", "A component has an empty name.")
                return False

            if node.instance_name in used_names:
                QMessageBox.warning(
                    self,
                    "Invalid Model",
                    f"The name '{node.instance_name}' is used more than once.",
                )
                return False

            used_names.add(node.instance_name)

        for link in self.scene.links:
            if not link.name:
                QMessageBox.warning(self, "Invalid Model", "A link has an empty name.")
                return False

            if link.name in used_names:
                QMessageBox.warning(
                    self,
                    "Invalid Model",
                    f"The name '{link.name}' is used more than once.",
                )
                return False

            used_names.add(link.name)

            if not link.latency:
                QMessageBox.warning(
                    self,
                    "Invalid Model",
                    f"Link '{link.name}' is missing required latency.",
                )
                return False

        for node in self.scene.component_items():
            parameters = self.properties_panel.load_component_parameters(node.component.component_id)

            for parameter in parameters:
                name = parameter.get("name", "")
                required = bool(parameter.get("required"))
                default_value = parameter.get("default_val", "")

                if default_value == "<required>":
                    default_value = ""

                value = node.parameters.get(name, default_value)

                if required and not str(value).strip():
                    QMessageBox.warning(
                        self,
                        "Invalid Model",
                        f"Component '{node.instance_name}' is missing required parameter '{name}'.",
                    )
                    return False

        return True

    def set_current_project_path(self, path: Optional[str | Path]) -> None:
        self.current_project_path = Path(path) if path else None

        if self.current_project_path is not None:
            self.project_name = self.current_project_path.stem
            self.setWindowTitle(f"FUSE SST Model Builder - {self.current_project_path.name}")
        else:
            self.project_name = "Untitled SST Model"
            self.setWindowTitle("FUSE SST Model Builder")

    def new_model(self):
        self.scene.clear_model()
        self.properties_panel.show_empty()
        self.set_current_project_path(None)
        self.statusBar().showMessage("New model created", 3000)

    def save_model(self):
        if not self.validate_model_before_save():
            return

        if self.current_project_path is None:
            self.save_model_as()
            return

        project = self.project_dict()
        save_project_file(project, self.current_project_path)
        self.statusBar().showMessage(f"Saved {self.current_project_path}", 3000)

    def save_model_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FUSE Model",
            str(self.current_project_path or ""),
            "FUSE Model (*.fse);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return

        if not file_path.endswith(".fse"):
            file_path += ".fse"

        self.set_current_project_path(file_path)
        self.save_model()

    def open_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FUSE Model",
            "",
            "FUSE Model (*.fse);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return

        try:
            project = load_project_file(file_path)
            load_project_into_scene(project, self.scene)
            self.properties_panel.show_empty()
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        self.set_current_project_path(file_path)
        self.statusBar().showMessage(f"Opened {file_path}", 3000)

    def show_about(self):
        QMessageBox.information(
            self,
            "About FUSE",
            "FUSE SST Model Builder\n\n"
            "Drag components from the left panel into the canvas.\n"
            "Click one port, then another port, to create an SST-style link.",
        )

    def show_links(self):
        if not self.scene.links:
            QMessageBox.information(self, "Links", "No links have been created yet.")
            return

        text = "\n".join(
            f"{link.name}: "
            f"{link.source_component_name}.{link.source_port} -> "
            f"{link.target_component_name}.{link.target_port} "
            f"latency={link.latency}"
            for link in self.scene.links
        )

        QMessageBox.information(self, "Links", text)


def ensure_database_ready() -> None:
    """
    Create app_data/app.db and all schema tables if they do not exist.

    This should run when the GUI starts. It does not populate SST metadata;
    it only guarantees the database file/schema exists. If the database is
    empty, the component palette will simply be empty.
    """
    if initialize_database is None:
        print("Could not import initialize_database; database was not initialized.")
        return

    try:
        initialize_database()
    except Exception as exc:
        print(f"Failed to initialize database: {exc}")


def load_component_definitions() -> list[ComponentDefinition]:
    if get_all_elements is None or get_all_components_for_element is None:
        return []

    try:
        definitions: list[ComponentDefinition] = []
        elements = get_all_elements()

        for element in elements:
            element_name = element["name"]
            components = get_all_components_for_element(element_name)

            for component in components:
                definitions.append(
                    ComponentDefinition(
                        component_id=component.get("id"),
                        element=element_name,
                        name=component.get("name", ""),
                        is_subcomp=int(component.get("is_subcomp", 0)),
                        category=component.get("category", ""),
                        iface=component.get("iface", ""),
                    )
                )

        return definitions

    except Exception as exc:
        print(f"Failed to load components from database: {exc}")
        return []


def load_port_names_for_component(component_id: Optional[int]) -> list[str]:
    if component_id is None or get_ports_for_component is None:
        return []

    try:
        ports = get_ports_for_component(component_id)
        return [port["name"] for port in ports]
    except Exception as exc:
        print(f"Failed to load ports for component {component_id}: {exc}")
        return []


def demo_components() -> list[ComponentDefinition]:
    return [
        ComponentDefinition(element="demo", name="CPU", category="PROCESSOR COMPONENT"),
        ComponentDefinition(element="demo", name="Cache", category="MEMORY COMPONENT"),
        ComponentDefinition(element="demo", name="Memory", category="MEMORY COMPONENT"),
        ComponentDefinition(element="demo", name="Network", category="NETWORK COMPONENT"),
    ]


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
