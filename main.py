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
    ROUTE_MARGIN = 35

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
        self.update_position()

        source_port.connections.append(self)
        target_port.connections.append(self)

    def node_body_rect(self, node: "ComponentNodeItem"):
        """
        Return only the component box rectangle in scene coordinates.

        Do not use sceneBoundingRect() here. sceneBoundingRect() includes child
        items such as port dots, text labels, and selection outlines. That can
        make the router think a side port is closer to the top/bottom than the
        actual left/right side of the component box, which causes routes to run
        through boxes.
        """
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

    def link_lane_offset(self) -> float:
        """
        Give each link a small deterministic lane offset so multiple links do
        not collapse onto the exact same route channel.

        Keep this smaller than ROUTE_MARGIN. If the offset is larger than the
        box-avoidance margin, an "outside" route channel can accidentally move
        back inside a component box.
        """
        lane_spacing = min(8, max(4, self.ROUTE_MARGIN / 4))
        lanes = [-2, -1, 1, 2, -3, 3]
        lane = lanes[(self.link.link_id - 1) % len(lanes)]
        return lane * lane_spacing

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
        Return an escape point in a per-link lane. The segment from the port to
        the regular escape point stays attached to the exact port, then the line
        shifts into its own nearby lane outside the box.
        """
        base = self.port_escape_point(port)
        side = self.port_side(port)
        offset = self.link_lane_offset()

        if side in {"left", "right"}:
            return QPointF(base.x(), base.y() + offset)

        return QPointF(base.x() + offset, base.y())

    def obstacle_rects(self):
        scene = self.scene()
        if scene is None:
            return []

        pad = 6
        rects = []

        for item in scene.items():
            if isinstance(item, ComponentNodeItem):
                rects.append(self.node_body_rect(item).adjusted(-pad, -pad, pad, pad))

        return rects

    @staticmethod
    def is_vertical(a: QPointF, b: QPointF) -> bool:
        return abs(a.x() - b.x()) < 0.001

    @staticmethod
    def is_horizontal(a: QPointF, b: QPointF) -> bool:
        return abs(a.y() - b.y()) < 0.001

    def segment_intersects_rect(self, a: QPointF, b: QPointF, rect) -> bool:
        # Only Manhattan segments are generated by this router.
        if self.is_vertical(a, b):
            x = a.x()
            y1 = min(a.y(), b.y())
            y2 = max(a.y(), b.y())

            # Touching the outside edge is okay; crossing the interior is not.
            return rect.left() < x < rect.right() and not (y2 <= rect.top() or y1 >= rect.bottom())

        if self.is_horizontal(a, b):
            y = a.y()
            x1 = min(a.x(), b.x())
            x2 = max(a.x(), b.x())

            return rect.top() < y < rect.bottom() and not (x2 <= rect.left() or x1 >= rect.right())

        return False

    def route_is_clear(self, points: list[QPointF], rects) -> bool:
        for a, b in zip(points, points[1:]):
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

    def dedupe_points(self, points: list[QPointF]) -> list[QPointF]:
        deduped: list[QPointF] = []

        for point in points:
            if not deduped:
                deduped.append(point)
                continue

            previous = deduped[-1]
            if abs(previous.x() - point.x()) > 0.001 or abs(previous.y() - point.y()) > 0.001:
                deduped.append(point)

        return deduped

    def grid_route(self, start: QPointF, end: QPointF, rects) -> list[QPointF] | None:
        """
        Find an obstacle-avoiding Manhattan route between two already-outside
        lane escape points.

        The important detail is that we do NOT allow the final segment to come
        from the wrong side of a component box. For example, if the target port
        is on the left side of a box, the route must reach the left-side escape
        point without crossing through the box.
        """
        import heapq
        from itertools import count

        margin = self.ROUTE_MARGIN

        lane_offset = self.link_lane_offset()

        xs = {start.x(), end.x()}
        ys = {start.y(), end.y()}

        for rect in rects:
            # Use channels outside boxes only. Do not add rect.left/right/top/bottom
            # themselves as route coordinates, because that can make paths ride
            # along or visually clip through component edges.
            lane_distance = abs(lane_offset)
            xs.add(rect.left() - margin - lane_distance)
            xs.add(rect.right() + margin + lane_distance)
            ys.add(rect.top() - margin - lane_distance)
            ys.add(rect.bottom() + margin + lane_distance)

        x_values = sorted(xs)
        y_values = sorted(ys)

        def key(point: QPointF) -> tuple[float, float]:
            return (round(point.x(), 3), round(point.y(), 3))

        def manhattan(a: QPointF, b: QPointF) -> float:
            return abs(a.x() - b.x()) + abs(a.y() - b.y())

        point_by_key: dict[tuple[float, float], QPointF] = {}

        for x in x_values:
            for y in y_values:
                point = QPointF(x, y)
                if not any(rect.contains(point) for rect in rects):
                    point_by_key[key(point)] = point

        start_key = key(start)
        end_key = key(end)
        point_by_key[start_key] = start
        point_by_key[end_key] = end

        row_points: dict[float, list[QPointF]] = {}
        col_points: dict[float, list[QPointF]] = {}

        for point in point_by_key.values():
            row_points.setdefault(round(point.y(), 3), []).append(point)
            col_points.setdefault(round(point.x(), 3), []).append(point)

        neighbors: dict[tuple[float, float], list[tuple[float, float]]] = {
            item_key: [] for item_key in point_by_key
        }

        for row in row_points.values():
            row.sort(key=lambda p: p.x())
            for a, b in zip(row, row[1:]):
                if self.route_is_clear([a, b], rects):
                    neighbors[key(a)].append(key(b))
                    neighbors[key(b)].append(key(a))

        for col in col_points.values():
            col.sort(key=lambda p: p.y())
            for a, b in zip(col, col[1:]):
                if self.route_is_clear([a, b], rects):
                    neighbors[key(a)].append(key(b))
                    neighbors[key(b)].append(key(a))

        sequence = count()
        frontier = [(0.0, next(sequence), start_key)]
        came_from: dict[tuple[float, float], tuple[float, float] | None] = {start_key: None}
        cost_so_far = {start_key: 0.0}

        while frontier:
            _, _, current = heapq.heappop(frontier)

            if current == end_key:
                break

            current_point = point_by_key[current]

            for next_key in neighbors.get(current, []):
                next_point = point_by_key[next_key]
                new_cost = cost_so_far[current] + manhattan(current_point, next_point)

                if next_key not in cost_so_far or new_cost < cost_so_far[next_key]:
                    cost_so_far[next_key] = new_cost
                    priority = new_cost + manhattan(next_point, end)
                    heapq.heappush(frontier, (priority, next(sequence), next_key))
                    came_from[next_key] = current

        if end_key not in came_from:
            return None

        route_keys = []
        current = end_key
        while current is not None:
            route_keys.append(current)
            current = came_from[current]

        route_keys.reverse()
        return [point_by_key[item] for item in route_keys]

    def routed_points(self) -> list[QPointF]:
        source_center = self.source_port.scene_center()
        target_center = self.target_port.scene_center()

        source_escape = self.port_escape_point(self.source_port)
        target_escape = self.port_escape_point(self.target_port)
        source_lane_escape = self.lane_escape_point(self.source_port)
        target_lane_escape = self.lane_escape_point(self.target_port)

        rects = self.obstacle_rects()
        route = self.grid_route(source_lane_escape, target_lane_escape, rects)

        if route is not None:
            return self.dedupe_points(
                [
                    source_center,
                    source_escape,
                    source_lane_escape,
                    *route[1:-1],
                    target_lane_escape,
                    target_escape,
                    target_center,
                ]
            )

        # Last-resort route: choose the global channel that matches the side of
        # the target port, so we still approach the target from outside its box
        # instead of crossing through it.
        if rects:
            lane_distance = abs(self.link_lane_offset())
            left_channel = min(rect.left() for rect in rects) - self.ROUTE_MARGIN - lane_distance
            right_channel = max(rect.right() for rect in rects) + self.ROUTE_MARGIN + lane_distance
            top_channel = min(rect.top() for rect in rects) - self.ROUTE_MARGIN - lane_distance
            bottom_channel = max(rect.bottom() for rect in rects) + self.ROUTE_MARGIN + lane_distance
        else:
            lane_distance = abs(self.link_lane_offset())
            left_channel = min(source_lane_escape.x(), target_lane_escape.x()) - self.ROUTE_MARGIN - lane_distance
            right_channel = max(source_lane_escape.x(), target_lane_escape.x()) + self.ROUTE_MARGIN + lane_distance
            top_channel = min(source_lane_escape.y(), target_lane_escape.y()) - self.ROUTE_MARGIN - lane_distance
            bottom_channel = max(source_lane_escape.y(), target_lane_escape.y()) + self.ROUTE_MARGIN + lane_distance

        target_side = self.port_side(self.target_port)
        source_side = self.port_side(self.source_port)

        if target_side in {"left", "right"}:
            channel_x = left_channel if target_side == "left" else right_channel
            fallback = [
                source_center,
                source_escape,
                source_lane_escape,
                QPointF(channel_x, source_lane_escape.y()),
                QPointF(channel_x, target_lane_escape.y()),
                target_lane_escape,
                target_escape,
                target_center,
            ]
        else:
            channel_y = top_channel if target_side == "top" else bottom_channel
            fallback = [
                source_center,
                source_escape,
                source_lane_escape,
                QPointF(source_lane_escape.x(), channel_y),
                QPointF(target_lane_escape.x(), channel_y),
                target_lane_escape,
                target_escape,
                target_center,
            ]

        # If that still crosses something due to unusual overlap, try approaching
        # from the source side's global channel instead.
        if not self.route_is_clear(fallback, rects):
            if source_side in {"left", "right"}:
                channel_x = left_channel if source_side == "left" else right_channel
                fallback = [
                    source_center,
                    source_escape,
                    source_lane_escape,
                    QPointF(channel_x, source_lane_escape.y()),
                    QPointF(channel_x, target_lane_escape.y()),
                    target_lane_escape,
                    target_escape,
                    target_center,
                ]
            else:
                channel_y = top_channel if source_side == "top" else bottom_channel
                fallback = [
                    source_center,
                    source_escape,
                    source_lane_escape,
                    QPointF(source_lane_escape.x(), channel_y),
                    QPointF(target_lane_escape.x(), channel_y),
                    target_lane_escape,
                    target_escape,
                    target_center,
                ]

        return self.dedupe_points(fallback)

    def build_path_from_points(self, points: list[QPointF]) -> QPainterPath:
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


def load_component_definitions() -> list[ComponentDefinition]:
    if get_all_elements is None or get_all_components_for_element is None:
        return demo_components()

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
        return demo_components()


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
