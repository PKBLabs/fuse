import sys
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QMimeData, QPointF
from PySide6.QtGui import QAction, QDrag, QPainter, QPen, QBrush, QColor, QPainterPath
from PySide6.QtWidgets import (
    QApplication,
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
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

try:
    from db_utils import (
        get_all_components_for_element,
        get_all_elements,
        get_ports_for_component,
    )
except ImportError:
    get_all_components_for_element = None
    get_all_elements = None
    get_ports_for_component = None

try:
    from initialize_db import initialize_database
except ImportError:
    initialize_database = None


MIME_COMPONENT = "application/x-fuse-component"


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

    def mousePressEvent(self, event):
        scene = self.scene()
        if isinstance(scene, ModelScene):
            scene.port_clicked(self)
        event.accept()


class ConnectionItem(QGraphicsPathItem):
    ROUTE_MARGIN = 36
    LANE_SPACING = 10

    def __init__(self, link: ModelLink, source_port: PortItem, target_port: PortItem):
        super().__init__()
        self.link = link
        self.source_port = source_port
        self.target_port = target_port

        self.setPen(QPen(QColor("#444444"), 2))
        self.setZValue(5)
        self.setAcceptedMouseButtons(Qt.NoButton)

        tooltip = (
            f"{link.name}\n"
            f"{link.source_component_name}.{link.source_port} -> "
            f"{link.target_component_name}.{link.target_port}\n"
            f"latency: {link.latency}"
        )
        self.setToolTip(tooltip)

        source_port.connections.append(self)
        target_port.connections.append(self)

        self.update_position()

    def node_body_rect(self, node: "ComponentNodeItem"):
        return node.mapRectToScene(node.rect())

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
        lanes = [-3, -2, -1, 1, 2, 3, -4, 4]
        return lanes[(self.link.link_id - 1) % len(lanes)]

    def parallel_lane_offset(self) -> float:
        return self.lane_index() * self.LANE_SPACING

    def outward_lane_offset(self) -> float:
        return abs(self.lane_index()) * self.LANE_SPACING

    def port_escape_point(self, port: PortItem) -> QPointF:
        center = port.scene_center()
        side = self.port_side(port)
        margin = self.ROUTE_MARGIN

        if side == "left":
            return QPointF(center.x() - margin, center.y())
        if side == "right":
            return QPointF(center.x() + margin, center.y())
        if side == "top":
            return QPointF(center.x(), center.y() - margin)
        return QPointF(center.x(), center.y() + margin)

    def lane_escape_point(self, port: PortItem) -> QPointF:
        """
        Point outside the component box in a lane unique to this link.

        Important: for side ports, the lane moves farther outward in X and also
        shifts up/down. For top/bottom ports, it moves farther outward in Y and
        also shifts left/right.
        """
        base = self.port_escape_point(port)
        side = self.port_side(port)
        parallel_offset = self.parallel_lane_offset()
        outward_offset = self.outward_lane_offset()

        if side == "left":
            return QPointF(base.x() - outward_offset, base.y() + parallel_offset)

        if side == "right":
            return QPointF(base.x() + outward_offset, base.y() + parallel_offset)

        if side == "top":
            return QPointF(base.x() + parallel_offset, base.y() - outward_offset)

        return QPointF(base.x() + parallel_offset, base.y() + outward_offset)

    def lane_transition_points(
        self,
        port: PortItem,
        base_escape: QPointF,
        lane_escape: QPointF,
    ) -> list[QPointF]:
        """
        Move from the normal escape point into the per-link lane using only
        horizontal/vertical segments.

        This avoids the triangular/diagonal-looking cuts that happen if the path
        goes directly from base_escape to lane_escape.
        """
        side = self.port_side(port)

        if side in {"left", "right"}:
            corner = QPointF(lane_escape.x(), base_escape.y())
        else:
            corner = QPointF(base_escape.x(), lane_escape.y())

        return self.simplify_points([base_escape, corner, lane_escape])

    def obstacle_rects(self):
        scene = self.scene()
        if scene is None:
            return []

        pad = 8
        rects = []

        for item in scene.items():
            if isinstance(item, ComponentNodeItem):
                rects.append(self.node_body_rect(item).adjusted(-pad, -pad, pad, pad))

        return rects

    @staticmethod
    def same_x(a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) < 0.001

    @staticmethod
    def same_y(a: QPointF, b: QPointF) -> bool:
        return abs(a.y() - b.y()) < 0.001

    def is_orthogonal_segment(self, a: QPointF, b: QPointF) -> bool:
        return self.same_x(a, b) or self.same_y(a, b)

    def segment_intersects_rect(self, a: QPointF, b: QPointF, rect) -> bool:
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

    def route_is_clear(self, points: list[QPointF], rects) -> bool:
        for a, b in zip(points, points[1:]):
            if not self.is_orthogonal_segment(a, b):
                return False

            for rect in rects:
                if self.segment_intersects_rect(a, b, rect):
                    return False

        return True

    @staticmethod
    def route_length(points: list[QPointF]) -> float:
        total = 0.0
        for a, b in zip(points, points[1:]):
            total += abs(a.x() - b.x()) + abs(a.y() - b.y())
        return total

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

                if self.same_x(a, c) and self.same_y(a, c):
                    simplified.pop(-2)
                    simplified.pop(-1)
                    continue

                if self.same_x(a, b) and self.same_x(b, c):
                    simplified.pop(-2)
                    continue

                if self.same_y(a, b) and self.same_y(b, c):
                    simplified.pop(-2)
                    continue

                break

        return simplified

    def one_bend_routes(self, start: QPointF, end: QPointF) -> list[list[QPointF]]:
        routes = []

        if self.is_orthogonal_segment(start, end):
            routes.append([start, end])

        routes.append([start, QPointF(start.x(), end.y()), end])
        routes.append([start, QPointF(end.x(), start.y()), end])

        return [self.simplify_points(route) for route in routes]

    def escape_segment_is_clear(self, port: PortItem, point: QPointF, rects) -> bool:
        """
        Check whether the tiny segment from a port to a nearby route point is safe.

        We ignore the owning component rectangle because the segment starts on
        that box's edge. We still prevent it from crossing other component boxes.
        """
        center = port.scene_center()
        owner_rect = self.node_body_rect(port.node).adjusted(-8, -8, 8, 8)

        for rect in rects:
            if rect == owner_rect:
                continue

            if self.segment_intersects_rect(center, point, rect):
                return False

        return True

    def full_route_is_clear(self, points: list[QPointF], rects) -> bool:
        """
        Validate the entire route, including the short segments from the port dots.
        """
        if len(points) < 2:
            return True

        for a, b in zip(points, points[1:]):
            if not self.is_orthogonal_segment(a, b):
                return False

            for rect in rects:
                if self.segment_intersects_rect(a, b, rect):
                    return False

        return True

    def local_candidate_routes(self, start: QPointF, end: QPointF) -> list[list[QPointF]]:
        routes = self.one_bend_routes(start, end)

        outward = self.ROUTE_MARGIN + self.outward_lane_offset()
        lane = self.parallel_lane_offset()

        x_channels = [
            min(start.x(), end.x()) - outward,
            max(start.x(), end.x()) + outward,
            start.x() + lane,
            end.x() + lane,
        ]

        for x in x_channels:
            routes.append(
                self.simplify_points(
                    [start, QPointF(x, start.y()), QPointF(x, end.y()), end]
                )
            )

        y_channels = [
            min(start.y(), end.y()) - outward,
            max(start.y(), end.y()) + outward,
            start.y() + lane,
            end.y() + lane,
        ]

        for y in y_channels:
            routes.append(
                self.simplify_points(
                    [start, QPointF(start.x(), y), QPointF(end.x(), y), end]
                )
            )

        return routes

    def best_route(
        self,
        source_center: QPointF,
        source_escape: QPointF,
        source_lane_escape: QPointF,
        target_center: QPointF,
        target_escape: QPointF,
        target_lane_escape: QPointF,
        rects,
    ) -> list[QPointF]:
        candidates = self.local_candidate_routes(source_lane_escape, target_lane_escape)
        candidates.extend(self.global_candidate_routes(source_lane_escape, target_lane_escape, rects))

        best = None
        best_score = None

        for route in candidates:
            route = self.simplify_points(route)

            full_route = self.simplify_points(
                [source_center, source_escape, *route, target_escape, target_center]
            )

            if not self.full_route_is_clear(full_route, rects):
                continue

            score = self.route_length(full_route) + len(full_route) * 20

            if best_score is None or score < best_score:
                best_score = score
                best = route

        if best is not None:
            return best

        # Absolute fallback. It may be ugly, but it will not hang the UI.
        return self.simplify_points(
            [source_lane_escape, QPointF(source_lane_escape.x(), target_lane_escape.y()), target_lane_escape]
        )

    def global_candidate_routes(self, start: QPointF, end: QPointF, rects) -> list[list[QPointF]]:
        margin = self.ROUTE_MARGIN + self.outward_lane_offset()

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

        routes = []

        for x in (left, right):
            routes.append(
                self.simplify_points(
                    [start, QPointF(x, start.y()), QPointF(x, end.y()), end]
                )
            )

        for y in (top, bottom):
            routes.append(
                self.simplify_points(
                    [start, QPointF(start.x(), y), QPointF(end.x(), y), end]
                )
            )

        # Full perimeter routes. Useful when simple global doglegs are blocked.
        routes.extend(
            [
                self.simplify_points(
                    [start, QPointF(left, start.y()), QPointF(left, top), QPointF(end.x(), top), end]
                ),
                self.simplify_points(
                    [start, QPointF(right, start.y()), QPointF(right, top), QPointF(end.x(), top), end]
                ),
                self.simplify_points(
                    [start, QPointF(left, start.y()), QPointF(left, bottom), QPointF(end.x(), bottom), end]
                ),
                self.simplify_points(
                    [start, QPointF(right, start.y()), QPointF(right, bottom), QPointF(end.x(), bottom), end]
                ),
            ]
        )

        return routes

    def routed_points(self) -> list[QPointF]:
        source_center = self.source_port.scene_center()
        target_center = self.target_port.scene_center()

        source_escape = self.port_escape_point(self.source_port)
        target_escape = self.port_escape_point(self.target_port)
        source_lane_escape = self.lane_escape_point(self.source_port)
        target_lane_escape = self.lane_escape_point(self.target_port)

        rects = self.obstacle_rects()
        route = self.best_route(
            source_center=source_center,
            source_escape=source_escape,
            source_lane_escape=source_lane_escape,
            target_center=target_center,
            target_escape=target_escape,
            target_lane_escape=target_lane_escape,
            rects=rects,
        )

        source_transition = self.lane_transition_points(
            self.source_port,
            source_escape,
            source_lane_escape,
        )
        target_transition = self.lane_transition_points(
            self.target_port,
            target_escape,
            target_lane_escape,
        )

        # target_transition goes target_escape -> ... -> target_lane_escape.
        # Reverse it because the final visual path travels from the lane back to
        # the actual target port.
        target_transition = list(reversed(target_transition))

        return self.simplify_points(
            [
                source_center,
                *source_transition,
                *route[1:-1],
                *target_transition,
                target_center,
            ]
        )

    def build_path_from_points(self, points: list[QPointF]) -> QPainterPath:
        if not points:
            return QPainterPath()

        path = QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        return path

    def update_position(self):
        self.setPath(self.build_path_from_points(self.routed_points()))


class ComponentNodeItem(QGraphicsRectItem):
    WIDTH = 210
    HEIGHT = 110

    _next_node_id = 1

    def __init__(self, component: ComponentDefinition):
        super().__init__(0, 0, self.WIDTH, self.HEIGHT)
        self.node_id = ComponentNodeItem._next_node_id
        ComponentNodeItem._next_node_id += 1

        self.component = component
        self.ports: list[PortItem] = []

        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#333333"), 1.5))
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )

        title = QGraphicsTextItem(f"{component.name}_{self.node_id}", self)
        title.setDefaultTextColor(QColor("#111111"))
        title.setPos(10, 8)

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
        return f"{self.component.name}_{self.node_id}"

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

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
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
        self.links: list[ModelLink] = []
        self._next_link_id = 1

    def port_clicked(self, port: PortItem):
        """
        Two-click connection behavior:
        - click source port
        - click target port
        - create a persistent SST-style link entity and a visual line
        """
        if self.pending_source_port is None:
            self.begin_connection(port)
            return

        if port is self.pending_source_port:
            self.cancel_pending_connection()
            return

        self.finish_connection(port)

    def begin_connection(self, source_port: PortItem):
        self.cancel_pending_connection()

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
        # Clicking empty canvas cancels a pending link operation.
        # Use all items under the cursor, not just itemAt(). The temporary dashed
        # line can be above the port visually, so itemAt() may return the line
        # instead of the port and accidentally cancel the connection.
        if self.pending_source_port is not None:
            clicked_items = self.items(event.scenePos())
            clicked_a_port = any(isinstance(item, PortItem) for item in clicked_items)

            if not clicked_a_port:
                self.cancel_pending_connection()

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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FUSE SST Model Builder")
        self.resize(1300, 800)

        self.palette = ComponentPalette()
        self.scene = ModelScene()
        self.model_view = ModelView(self.scene)

        self.setup_menu_bar()
        self.setup_layout()
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
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        refresh_action = QAction("Refresh Component List", self)
        refresh_action.triggered.connect(self.palette.load_components)
        tools_menu.addAction(refresh_action)

        show_links_action = QAction("Show Links", self)
        show_links_action.triggered.connect(self.show_links)
        tools_menu.addAction(show_links_action)

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

    def setup_status_bar(self):
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

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
