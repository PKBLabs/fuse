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
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPen, QColor
from PySide6.QtWidgets import (
    QGraphicsLineItem,
    QGraphicsScene,
    QInputDialog,
    QMessageBox,
)

from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, PortItem
from fuse.core.model.models import ModelLink


class ModelScene(QGraphicsScene):
    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2000, 1500)
        self.pending_source_port: Optional[PortItem] = None
        self.pending_line: Optional[QGraphicsLineItem] = None
        self.properties_panel: Optional["PropertiesPanel"] = None
        self.links: list[ModelLink] = []
        self._next_link_id = 1
        self.model_changed_callback = None
        self.component_added_callback = None

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
        self.notify_model_changed()

    def notify_model_changed(self):
        if self.model_changed_callback is not None:
            self.model_changed_callback()

    def notify_component_added(self, node: ComponentNodeItem):
        if self.component_added_callback is not None:
            self.component_added_callback(node)
        self.notify_model_changed()

    def existing_component_names(self) -> set[str]:
        return {node.instance_name for node in self.component_items()}

    def generate_unique_component_name(self, component) -> str:
        base_name = component.name or "Component"
        used_names = self.existing_component_names()

        index = 1
        while f"{base_name}_{index}" in used_names:
            index += 1

        return f"{base_name}_{index}"

    def create_component_node(self, component, scene_pos, instance_name: str | None = None):
        node = ComponentNodeItem(
            component,
            instance_name=instance_name or self.generate_unique_component_name(component),
        )
        node.setPos(scene_pos)
        self.addItem(node)
        self.notify_component_added(node)
        return node

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