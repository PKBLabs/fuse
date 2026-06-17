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
"""Graphics-scene model editor for FUSE diagrams.

``ModelScene`` is the canvas data owner for one open model. It manages
component nodes, port-to-port links, subcomponent attachments, selection state,
drag rerouting, compatibility feedback, and pending connection gestures. The
scene exposes editor-oriented operations that ``MainWindow`` and ``ModelView``
can call without needing to manipulate individual ``QGraphicsItem`` instances
directly.

The scene stores lightweight Python model records in parallel with Qt graphics
items. Persistence and exporters consume the model records, while the graphics
items provide interaction and rendering.
"""
from __future__ import annotations

from typing import Optional
from copy import deepcopy

from PySide6.QtCore import QPointF, Qt, QTimer
from PySide6.QtGui import QKeySequence, QPen, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QGraphicsLineItem,
    QGraphicsScene,
    QMessageBox,
)

from fuse.core.model.models import ModelLink, ModelSubcompAttachment
from fuse.core.plugin_runtime.manager import get_plugin_by_id
from fuse.core.ui.graphics_items import (
    ComponentNodeItem,
    ConnectionItem,
    PortItem,
    SubcompAttachmentItem,
    SubcompConnectorItem,
)
from fuse.plugin_api.interfaces import LinkCompatibilityResult, LinkEndpoint


class ModelScene(QGraphicsScene):
    """Interactive graphics scene for a single FUSE model document.

    The scene owns component-node items and connection items, coordinates
    connection gestures, and notifies the application when the model changes.
    It is also responsible for local canvas behaviors such as route updates,
    selection highlights, compatibility warnings, and deletion cascades.

    ``ModelScene`` should remain simulator-neutral. Framework-specific rules are
    queried through plugin compatibility helpers and are reflected in generic UI
    warnings/highlights rather than embedded directly in the scene.
    """
    def __init__(self):
        super().__init__()
        self.setSceneRect(0, 0, 2000, 1500)

        self.pending_source_port: Optional[PortItem] = None
        self.pending_subcomp_connector: Optional[SubcompConnectorItem] = None
        self.pending_line: Optional[QGraphicsLineItem] = None

        self.properties_panel: Optional["PropertiesPanel"] = None

        self.links: list[ModelLink] = []
        self.subcomp_attachments: list[ModelSubcompAttachment] = []

        self._next_link_id = 1
        self._next_subcomp_attachment_id = 1

        self._next_group_id = 1
        self.node_group_ids: dict[int, int] = {}
        self._moving_group = False

        self.snap_to_grid_enabled = False
        self.snap_grid_width = float(ComponentNodeItem.WIDTH)
        self.snap_grid_height = float(ComponentNodeItem.HEIGHT)
        self.snap_grid_origin = QPointF(0.0, 0.0)

        self.model_changed_callback = None
        self.component_added_callback = None
        self.component_used_callback = None
        self.component_favorite_requested_callback = None
        self.selection_changed_callback = None

        self.active_plugin_id: str | None = None
        self.selected_connection: Optional[ConnectionItem] = None
        self.selected_subcomp_attachment: Optional[SubcompAttachmentItem] = None
        self.selected_component: Optional[ComponentNodeItem] = None
        self.suppress_mixed_endpoint_warning = False
        self.suppress_port_occupied_warning = False

        # Link routing is relatively expensive. A component drag can generate
        # hundreds of ItemPositionHasChanged events per second. During drag we
        # use cheap preview routing, then do one full reroute on release.
        self._dragging_node = False
        self._drag_changed = False
        self._drag_start_positions: dict[int, tuple[float, float]] = {}
        self._reroute_timer = QTimer()
        self._reroute_timer.setSingleShot(True)
        self._reroute_timer.setInterval(250)
        self._reroute_timer.timeout.connect(self.reroute_all_links)

    def connection_items(self) -> list[ConnectionItem]:
        items = [item for item in self.items() if isinstance(item, ConnectionItem)]
        return sorted(items, key=lambda item: item.link.link_id)

    def subcomp_attachment_items(self) -> list[SubcompAttachmentItem]:
        items = [
            item
            for item in self.items()
            if isinstance(item, SubcompAttachmentItem)
        ]
        return sorted(items, key=lambda item: item.attachment.attachment_id)

    def component_items(self) -> list[ComponentNodeItem]:
        items = [item for item in self.items() if isinstance(item, ComponentNodeItem)]
        return sorted(items, key=lambda item: item.node_id)

    def clear_model(self):
        self.cancel_pending_connection()
        self.cancel_pending_subcomp_attachment()
        self.clear()
        self.links = []
        self.subcomp_attachments = []
        self._next_link_id = 1
        self._next_subcomp_attachment_id = 1
        self._next_group_id = 1
        self.node_group_ids = {}
        ComponentNodeItem._next_node_id = 1
        self.notify_model_changed()

    def set_snap_grid_size(self, width: float, height: float) -> None:
        self.snap_grid_width = max(1.0, float(width))
        self.snap_grid_height = max(1.0, float(height))

    def set_snap_to_grid(self, enabled: bool) -> None:
        self.snap_to_grid_enabled = bool(enabled)

    def snap_position_to_grid(self, position: QPointF) -> QPointF:
        width = max(1.0, float(getattr(self, "snap_grid_width", ComponentNodeItem.WIDTH)))
        height = max(1.0, float(getattr(self, "snap_grid_height", ComponentNodeItem.HEIGHT)))
        origin = getattr(self, "snap_grid_origin", QPointF(0.0, 0.0))

        x_units = (position.x() - origin.x()) / width
        y_units = (position.y() - origin.y()) / height
        x_index = int(x_units + 0.5) if x_units >= 0 else int(x_units - 0.5)
        y_index = int(y_units + 0.5) if y_units >= 0 else int(y_units - 0.5)

        return QPointF(
            origin.x() + x_index * width,
            origin.y() + y_index * height,
        )

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


    def generate_unique_name_from_base(self, base_name: str, used_names: set[str] | None = None) -> str:
        base = (base_name or "Component").strip() or "Component"
        used = set(self.existing_component_names() if used_names is None else used_names)

        index = 1
        while f"{base}_{index}" in used:
            index += 1

        return f"{base}_{index}"

    def existing_link_names(self) -> set[str]:
        return {link.name for link in self.links}

    def generate_unique_link_name_from_base(self, base_name: str) -> str:
        base = (base_name or "link").strip() or "link"
        used = self.existing_link_names()

        if base not in used:
            return base

        index = 1
        while f"{base}_{index}" in used:
            index += 1

        return f"{base}_{index}"

    def selected_component_nodes(self, expand_groups: bool = True) -> list[ComponentNodeItem]:
        selected = [
            item
            for item in self.selectedItems()
            if isinstance(item, ComponentNodeItem)
        ]

        if self.selected_component is not None and self.selected_component not in selected:
            selected.append(self.selected_component)

        if not expand_groups:
            return sorted(set(selected), key=lambda node: node.node_id)

        selected_ids = {node.node_id for node in selected}
        group_ids = {
            self.node_group_ids[node_id]
            for node_id in selected_ids
            if node_id in self.node_group_ids
        }

        if group_ids:
            for node in self.component_items():
                if self.node_group_ids.get(node.node_id) in group_ids:
                    selected_ids.add(node.node_id)

        return [
            node
            for node in self.component_items()
            if node.node_id in selected_ids
        ]

    def copy_selection_to_clipboard(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=True)
        if not nodes:
            return False

        node_ids = {node.node_id for node in nodes}
        node_payloads = []
        for node in nodes:
            node_payloads.append(
                {
                    "old_node_id": node.node_id,
                    "component": deepcopy(node.component),
                    "instance_name": node.instance_name,
                    "parameters": deepcopy(getattr(node, "parameters", {}) or {}),
                    "variable_port_counts": deepcopy(getattr(node, "variable_port_counts", {}) or {}),
                    "icon_path": getattr(node, "icon_path", ""),
                    "composite_instance_model": deepcopy(getattr(node, "composite_instance_model", {}) or {}),
                    "composite_port_mappings": deepcopy(getattr(node, "composite_port_mappings", []) or []),
                    "pos": {"x": node.pos().x(), "y": node.pos().y()},
                    "group_id": self.node_group_ids.get(node.node_id),
                }
            )

        link_payloads = []
        for connection in self.connection_items():
            link = connection.link
            if link.source_node_id in node_ids and link.target_node_id in node_ids:
                link_payloads.append({"link": deepcopy(link)})

        attachment_payloads = []
        for item in self.subcomp_attachment_items():
            attachment = item.attachment
            if attachment.parent_node_id in node_ids and attachment.child_node_id in node_ids:
                attachment_payloads.append(
                    {
                        "attachment": deepcopy(attachment),
                        "target_connector_name": getattr(item.target_connector, "name", ""),
                    }
                )

        ModelScene._entity_clipboard = {
            "nodes": node_payloads,
            "links": link_payloads,
            "subcomp_attachments": attachment_payloads,
        }
        return True

    def paste_clipboard(self, scene_pos: QPointF | None = None) -> list[ComponentNodeItem]:
        payload = getattr(ModelScene, "_entity_clipboard", None)
        if not payload or not payload.get("nodes"):
            return []

        nodes_payload = payload.get("nodes", [])
        if scene_pos is None:
            scene_pos = QPointF(40.0, 40.0)

        min_x = min(float(item["pos"]["x"]) for item in nodes_payload)
        min_y = min(float(item["pos"]["y"]) for item in nodes_payload)

        used_names = self.existing_component_names()
        old_to_new: dict[int, ComponentNodeItem] = {}
        old_group_to_new: dict[int, int] = {}

        self.clearSelection()

        for item in nodes_payload:
            component = deepcopy(item["component"])
            new_name = self.generate_unique_name_from_base(str(item.get("instance_name") or component.name), used_names)
            used_names.add(new_name)

            offset_x = float(item["pos"]["x"]) - min_x
            offset_y = float(item["pos"]["y"]) - min_y
            node = self.create_component_node(
                component,
                QPointF(scene_pos.x() + offset_x, scene_pos.y() + offset_y),
                instance_name=new_name,
            )
            node.parameters = deepcopy(item.get("parameters", {}) or {})
            node.variable_port_counts = deepcopy(item.get("variable_port_counts", {}) or {})
            node.composite_instance_model = deepcopy(item.get("composite_instance_model", {}) or {})
            node.composite_port_mappings = deepcopy(item.get("composite_port_mappings", []) or [])
            if item.get("icon_path") and hasattr(node, "set_icon_path"):
                node.set_icon_path(str(item.get("icon_path") or ""))
            if hasattr(node, "sync_ports_to_templates"):
                node.sync_ports_to_templates()
            if hasattr(node, "sync_composite_ports_from_mappings"):
                node.sync_composite_ports_from_mappings()

            old_to_new[int(item["old_node_id"])] = node
            old_group_id = item.get("group_id")
            if old_group_id is not None:
                old_group_id = int(old_group_id)
                if old_group_id not in old_group_to_new:
                    old_group_to_new[old_group_id] = self._next_group_id
                    self._next_group_id += 1
                self.node_group_ids[node.node_id] = old_group_to_new[old_group_id]

            node.setSelected(True)

        for item in payload.get("links", []):
            old_link = item.get("link")
            source_node = old_to_new.get(int(old_link.source_node_id))
            target_node = old_to_new.get(int(old_link.target_node_id))
            if source_node is None or target_node is None:
                continue

            source_port = self.find_port(source_node.node_id, old_link.source_port)
            target_port = self.find_port(target_node.node_id, old_link.target_port)
            if source_port is None or target_port is None:
                continue

            link = deepcopy(old_link)
            link.link_id = self._next_link_id
            self._next_link_id += 1
            link.name = self.generate_unique_link_name_from_base(link.name)
            link.source_node_id = source_node.node_id
            link.source_component_name = source_node.instance_name
            link.target_node_id = target_node.node_id
            link.target_component_name = target_node.instance_name

            self.links.append(link)
            connection = ConnectionItem(link, source_port, target_port)
            self.addItem(connection)
            connection.update_position()

        for item in payload.get("subcomp_attachments", []):
            old_attachment = item.get("attachment")
            parent_node = old_to_new.get(int(old_attachment.parent_node_id))
            child_node = old_to_new.get(int(old_attachment.child_node_id))
            if parent_node is None or child_node is None:
                continue

            slot_connector = self.find_subcomp_connector(
                parent_node.node_id,
                old_attachment.slot_name,
                role="slot",
            )
            interface_connector = self.find_subcomp_connector(
                child_node.node_id,
                str(item.get("target_connector_name") or ""),
                role="interface",
            )
            if slot_connector is None:
                continue
            if interface_connector is None:
                connectors = [
                    connector
                    for connector in getattr(child_node, "subcomp_connectors", [])
                    if getattr(connector, "role", "") == "interface"
                ]
                interface_connector = connectors[0] if connectors else None
            if interface_connector is None:
                continue

            attachment = deepcopy(old_attachment)
            attachment.attachment_id = self._next_subcomp_attachment_id
            self._next_subcomp_attachment_id += 1
            attachment.parent_node_id = parent_node.node_id
            attachment.parent_component_name = parent_node.instance_name
            attachment.child_node_id = child_node.node_id
            attachment.child_component_name = child_node.instance_name

            self.subcomp_attachments.append(attachment)
            attachment_item = SubcompAttachmentItem(attachment, slot_connector, interface_connector)
            self.addItem(attachment_item)
            attachment_item.update_position()

        self.reroute_all_links()
        self.notify_model_changed()
        return list(old_to_new.values())

    def group_selection(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=False)
        if len(nodes) < 2:
            return False

        group_id = self._next_group_id
        self._next_group_id += 1

        for node in nodes:
            self.node_group_ids[node.node_id] = group_id

        self.notify_model_changed()
        return True

    def ungroup_selection(self) -> bool:
        nodes = self.selected_component_nodes(expand_groups=True)
        if not nodes:
            return False

        group_ids = {
            self.node_group_ids[node.node_id]
            for node in nodes
            if node.node_id in self.node_group_ids
        }
        if not group_ids:
            return False

        self.node_group_ids = {
            node_id: group_id
            for node_id, group_id in self.node_group_ids.items()
            if group_id not in group_ids
        }
        self.notify_model_changed()
        return True

    def group_members_for_node(self, node: ComponentNodeItem) -> list[ComponentNodeItem]:
        group_id = self.node_group_ids.get(node.node_id)
        if group_id is None:
            return []
        return [
            candidate
            for candidate in self.component_items()
            if candidate is not node and self.node_group_ids.get(candidate.node_id) == group_id
        ]

    def apply_group_drag(self, node: ComponentNodeItem) -> None:
        if self._moving_group or not self._dragging_node:
            return

        members = self.group_members_for_node(node)
        if not members:
            return

        start = self._drag_start_positions.get(node.node_id)
        if start is None:
            return

        dx = node.pos().x() - start[0]
        dy = node.pos().y() - start[1]
        if abs(dx) < 0.001 and abs(dy) < 0.001:
            return

        self._moving_group = True
        try:
            for member in members:
                member_start = self._drag_start_positions.get(member.node_id)
                if member_start is None:
                    continue
                member.setPos(member_start[0] + dx, member_start[1] + dy)
        finally:
            self._moving_group = False

    def create_component_node(self, component, scene_pos, instance_name: str | None = None):
        if self.snap_to_grid_enabled:
            scene_pos = self.snap_position_to_grid(scene_pos)

        node = ComponentNodeItem(
            component,
            instance_name=instance_name or self.generate_unique_component_name(component),
        )
        node.setPos(scene_pos)
        self.addItem(node)

        if self.component_used_callback is not None:
            self.component_used_callback(component)

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

    def find_subcomp_connector(
        self,
        node_id: int,
        connector_name: str,
        role: str = "",
    ) -> Optional[SubcompConnectorItem]:
        for node in self.component_items():
            if node.node_id != node_id:
                continue

            for connector in getattr(node, "subcomp_connectors", []):
                if connector.name != connector_name:
                    continue

                if role and getattr(connector, "role", "") != role:
                    continue

                return connector

        return None

    def clear_link_highlights(self):
        self.selected_connection = None

        for connection in self.connection_items():
            connection.set_highlighted(False)

    def clear_subcomp_attachment_highlights(self):
        self.selected_subcomp_attachment = None

        for attachment in self.subcomp_attachment_items():
            attachment.set_highlighted(False)

    def clear_all_selection_highlights(self):
        self.clear_link_highlights()
        self.clear_subcomp_attachment_highlights()

    def highlight_links_for_node(self, node: "ComponentNodeItem"):
        self.clear_subcomp_attachment_highlights()

        for connection in self.connection_items():
            connection.set_highlighted(connection.is_connected_to_node(node))

        for attachment in self.subcomp_attachment_items():
            attachment.set_highlighted(attachment.is_connected_to_node(node))

    def select_component(self, node: "ComponentNodeItem"):
        self.selected_component = node
        self.selected_connection = None
        self.selected_subcomp_attachment = None
        self.highlight_links_for_node(node)

        if self.properties_panel is not None:
            self.properties_panel.show_component(node)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(node)

    def select_link(self, connection: ConnectionItem):
        self.clear_all_selection_highlights()
        self.selected_component = None
        self.selected_connection = connection
        connection.set_highlighted(True)

        if self.properties_panel is not None:
            self.properties_panel.show_link(connection)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(None)

    def select_subcomp_attachment(self, attachment: SubcompAttachmentItem):
        self.clear_all_selection_highlights()
        self.selected_component = None
        self.selected_subcomp_attachment = attachment
        attachment.set_highlighted(True)

        if self.properties_panel is not None:
            self.properties_panel.show_subcomp_attachment(attachment)

        if self.selection_changed_callback is not None:
            self.selection_changed_callback(None)

    def find_node_by_id(self, node_id: int) -> ComponentNodeItem | None:
        for node in self.component_items():
            if node.node_id == node_id:
                return node

        return None

    def begin_node_drag(self):
        self._dragging_node = True
        self._drag_changed = False
        self._drag_start_positions = {
            node.node_id: (node.pos().x(), node.pos().y())
            for node in self.component_items()
        }
        self._reroute_timer.stop()

    def end_node_drag(self, node: Optional["ComponentNodeItem"] = None):
        """
        End an interactive drag.

        Scalability rule: do NOT reroute the entire model automatically here.
        Instead, reroute:
          1. links attached to the moved node,
          2. subcomponent attachment edges attached to the moved node, and
          3. existing links whose current route now intersects the moved node box.

        Snap-to-grid intentionally happens here, not during ItemPositionChange,
        so dragged components move smoothly while the mouse button is held and
        settle onto the grid only when the user drops them.
        """
        changed = self._drag_changed
        if node is not None:
            start = self._drag_start_positions.get(node.node_id)
            if start is not None:
                changed = changed or (node.pos().x(), node.pos().y()) != start

        if changed and node is not None and self.snap_to_grid_enabled:
            snapped_position = self.snap_position_to_grid(node.pos())
            if snapped_position != node.pos():
                node.setPos(snapped_position)
                changed = True

        self._dragging_node = False

        if node is not None:
            self.reroute_links_affected_by_node(node)
            self.update_subcomp_attachments_for_node(node)

        self._drag_changed = False
        self._drag_start_positions = {}

        if changed:
            self.notify_model_changed()

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
        """
        connections = self.connection_items()

        for connection in connections:
            connection.clear_route_points()

        for connection in connections:
            connection.update_position()

        for attachment in self.subcomp_attachment_items():
            attachment.update_position()

    def reroute_links_for_node(self, node: "ComponentNodeItem", force_full: bool = False):
        """
        Update only links and subcomponent attachment edges attached to a node.
        """
        for connection in self.links_attached_to_node(node):
            if self._dragging_node and not force_full:
                connection.update_position_fast()
            else:
                connection.update_position()

        self.update_subcomp_attachments_for_node(node)

    def update_subcomp_attachments_for_node(self, node: "ComponentNodeItem"):
        for attachment in self.subcomp_attachment_items():
            if attachment.is_connected_to_node(node):
                attachment.update_position()

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

    def endpoint_for_port(self, port: PortItem) -> LinkEndpoint:
        return LinkEndpoint(
            component_name=port.node.instance_name,
            port_name=port.name,
            port_metadata=getattr(port, "metadata", {}) or {},
        )

    def default_link_name(self, source_port: PortItem, target_port: PortItem) -> str:
        base = f"lnk_{source_port.node.instance_name}_{target_port.node.instance_name}"
        base = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)

        existing = {link.name for link in self.links}

        if base not in existing:
            return base

        index = 1
        while f"{base}_{index}" in existing:
            index += 1

        return f"{base}_{index}"

    def check_link_compatibility(
        self,
        source_port: PortItem,
        target_port: PortItem,
    ) -> LinkCompatibilityResult:
        source_plugin_id = getattr(source_port.node.component, "plugin_id", "") or ""
        target_plugin_id = getattr(target_port.node.component, "plugin_id", "") or ""
        plugin_id = source_plugin_id if source_plugin_id == target_plugin_id else (self.active_plugin_id or source_plugin_id)

        if not plugin_id:
            return LinkCompatibilityResult()

        try:
            plugin = get_plugin_by_id(plugin_id)
        except Exception:
            return LinkCompatibilityResult()

        if not hasattr(plugin, "check_link_compatibility"):
            return LinkCompatibilityResult()

        return plugin.check_link_compatibility(
            self.endpoint_for_port(source_port),
            self.endpoint_for_port(target_port),
        )

    def confirm_link_compatibility_warning(self, result: LinkCompatibilityResult) -> bool:
        response = QMessageBox.warning(
            None,
            result.title or "Link Compatibility Warning",
            result.message or "The selected ports may not be compatible. Create the link anyway?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        return response == QMessageBox.Yes

    def clear_port_compatibility_highlights(self):
        for node in self.component_items():
            for port in node.ports:
                port.set_compatibility_highlight("")

    def highlight_compatible_ports(self, source_port: PortItem):
        """
        Highlight structurally linkable ports.

        For regular links, FUSE should not try to fully type-check SST event
        compatibility from ordinary port metadata. Plugin compatibility hooks may
        still return warnings/errors for plugins that have reliable link metadata,
        but SST currently treats ordinary declared ports as structurally linkable.
        """
        for node in self.component_items():
            for port in node.ports:
                if port is source_port:
                    continue

                if port.is_connected():
                    continue

                result = self.check_link_compatibility(source_port, port)

                if result.severity == "error" or not result.can_create:
                    port.set_compatibility_highlight("incompatible")
                elif result.severity == "warning":
                    port.set_compatibility_highlight("warning")
                else:
                    port.set_compatibility_highlight("compatible")

    def create_link_between_ports(
        self,
        source_port: PortItem,
        target_port: PortItem,
        compatibility: LinkCompatibilityResult,
    ) -> ConnectionItem:
        link_id = self._next_link_id
        self._next_link_id += 1

        link = ModelLink(
            link_id=link_id,
            name=self.default_link_name(source_port, target_port),
            source_node_id=source_port.node.node_id,
            source_component_name=source_port.node.instance_name,
            source_port=source_port.name,
            target_node_id=target_port.node.node_id,
            target_component_name=target_port.node.instance_name,
            target_port=target_port.name,
            source_latency="1ns",
            target_latency="1ns",
            link_type="point_to_point",
            plugin_id=(
                getattr(source_port.node.component, "plugin_id", "")
                if getattr(source_port.node.component, "plugin_id", "") == getattr(target_port.node.component, "plugin_id", "")
                else (self.active_plugin_id or getattr(source_port.node.component, "plugin_id", ""))
            ),
            compatibility_severity=compatibility.severity,
            compatibility_code=compatibility.code,
            compatibility_message=compatibility.message,
            plugin_metadata={},
        )

        self.links.append(link)

        connection = ConnectionItem(link, source_port, target_port)
        self.addItem(connection)
        connection.update_position()
        self.select_link(connection)
        self.notify_model_changed()

        return connection

    def delete_link(self, connection: ConnectionItem):
        if connection.link in self.links:
            self.links.remove(connection.link)

        for port in (connection.source_port, connection.target_port):
            if connection in port.connections:
                port.connections.remove(connection)
            port.update_connection_state()

        self.removeItem(connection)

        if self.selected_connection is connection:
            self.selected_connection = None

        if self.properties_panel is not None:
            self.properties_panel.show_empty()

        self.notify_model_changed()

    def find_connection_by_link_id(self, link_id: int) -> ConnectionItem | None:
        for connection in self.connection_items():
            if connection.link.link_id == link_id:
                return connection

        return None

    def select_link_by_id(self, link_id: int):
        connection = self.find_connection_by_link_id(link_id)

        if connection is None:
            return

        self.select_link(connection)

    def delete_component_node(self, node: ComponentNodeItem):
        """
        Delete a component or subcomponent instance from the model.

        This also removes:
        - normal links attached to any of the node's ports
        - subcomponent attachment edges where the node is either the parent or child
        - child subcomponents recursively attached underneath this node
        """
        # Recursively delete attached child subcomponents first.
        child_node_ids = [
            attachment.child_node_id
            for attachment in list(getattr(self, "subcomp_attachments", []))
            if attachment.parent_node_id == node.node_id
        ]

        for child_node_id in child_node_ids:
            child_node = self.find_node_by_id(child_node_id)
            if child_node is not None:
                self.delete_component_node(child_node)

        # Delete normal links attached to this node.
        for connection in list(self.connection_items()):
            if connection.is_connected_to_node(node):
                self.delete_link(connection)

        # Delete subcomponent attachment edges involving this node.
        for attachment_item in list(self.subcomp_attachment_items()):
            attachment = attachment_item.attachment
            if (
                    attachment.parent_node_id == node.node_id
                    or attachment.child_node_id == node.node_id
            ):
                self.delete_subcomp_attachment(attachment_item)

        if self.selected_component is node:
            self.selected_component = None

        self.node_group_ids.pop(node.node_id, None)

        if self.properties_panel is not None:
            self.properties_panel.show_empty()

        self.removeItem(node)
        self.notify_model_changed()

    def delete_component_by_id(self, node_id: int):
        node = self.find_node_by_id(node_id)

        if node is None:
            return

        self.delete_component_node(node)

    def delete_link_by_id(self, link_id: int):
        connection = self.find_connection_by_link_id(link_id)

        if connection is None:
            return

        self.delete_link(connection)

    def find_subcomp_attachment_by_id(self, attachment_id: int) -> SubcompAttachmentItem | None:
        for item in self.subcomp_attachment_items():
            if item.attachment.attachment_id == attachment_id:
                return item

        return None

    def delete_subcomp_attachment_by_id(self, attachment_id: int):
        item = self.find_subcomp_attachment_by_id(attachment_id)

        if item is None:
            return

        self.delete_subcomp_attachment(item)

    def port_clicked(self, port: PortItem):
        if self.pending_subcomp_connector is not None:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_subcomp_attachment()
            return

        if port.is_connected():
            self.warn_port_already_connected()
            self.cancel_pending_connection()
            return

        if self.pending_source_port is None:
            self.pending_source_port = port
            self.clear_port_compatibility_highlights()
            self.highlight_compatible_ports(port)

            self.pending_line = QGraphicsLineItem()
            self.pending_line.setPen(QPen(QColor("#2f80ed"), 2, Qt.DashLine))
            self.pending_line.setZValue(4)
            self.pending_line.setAcceptedMouseButtons(Qt.NoButton)
            self.addItem(self.pending_line)
            return

        source_port = self.pending_source_port
        target_port = port

        if source_port is target_port:
            self.cancel_pending_connection()
            return

        if target_port.is_connected():
            self.warn_port_already_connected()
            self.cancel_pending_connection()
            return

        compatibility = self.check_link_compatibility(source_port, target_port)

        if compatibility.severity == "error" or not compatibility.can_create:
            QMessageBox.critical(
                None,
                compatibility.title or "Cannot Create Link",
                compatibility.message or "The selected ports cannot be linked.",
            )
            self.cancel_pending_connection()
            return

        if compatibility.severity == "warning":
            if not self.confirm_link_compatibility_warning(compatibility):
                self.cancel_pending_connection()
                return

        self.cancel_pending_visual_line_only()
        self.clear_port_compatibility_highlights()
        self.create_link_between_ports(source_port, target_port, compatibility)
        self.pending_source_port = None

    def begin_connection(self, source_port: PortItem):
        """
        Backward-compatible wrapper for older callers.

        New link creation is handled through port_clicked(), which creates the link
        immediately after the second port is selected, uses endpoint latencies, and
        shows the new link in the properties panel. Do not prompt for latency here.
        """
        if source_port.is_connected():
            return

        self.cancel_pending_connection()
        self.cancel_pending_subcomp_attachment()
        self.pending_source_port = source_port
        self.clear_port_compatibility_highlights()
        self.highlight_compatible_ports(source_port)

        self.pending_line = QGraphicsLineItem()
        self.pending_line.setPen(QPen(QColor("#2f80ed"), 2, Qt.DashLine))
        self.pending_line.setZValue(4)
        self.pending_line.setAcceptedMouseButtons(Qt.NoButton)

        start = source_port.scene_center()
        self.pending_line.setLine(start.x(), start.y(), start.x(), start.y())
        self.addItem(self.pending_line)

    def finish_connection(self, target_port: PortItem):
        """
        Backward-compatible wrapper for older callers.

        This delegates to the same no-popup behavior used by port_clicked().
        """
        if self.pending_source_port is None:
            return

        self.port_clicked(target_port)

    def subcomp_connectors_for_node(self, node: ComponentNodeItem) -> list[SubcompConnectorItem]:
        return list(getattr(node, "subcomp_connectors", []))

    def subcomp_connector_is_connected(self, connector: SubcompConnectorItem) -> bool:
        for attachment in self.subcomp_attachment_items():
            if attachment.source_connector is connector or attachment.target_connector is connector:
                return True

        return False

    def warn_mixed_endpoint_types(self):
        if self.suppress_mixed_endpoint_warning:
            return

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Warning)
        message_box.setWindowTitle("Invalid Connection Type")
        message_box.setText(
            "SubComponent Slots can only be connected to SubComponent Connectors."
        )
        message_box.setInformativeText(
            "Use normal component ports for SST links. Use purple "
            "subcomp_connector endpoints for SubComponent slot assignments."
        )
        message_box.setStandardButtons(QMessageBox.Ok)

        checkbox = QCheckBox("Do not show this warning again")
        message_box.setCheckBox(checkbox)

        message_box.exec()

        if checkbox.isChecked():
            self.suppress_mixed_endpoint_warning = True

    def warn_port_already_connected(self):
        if self.suppress_port_occupied_warning:
            return

        message_box = QMessageBox()
        message_box.setIcon(QMessageBox.Critical)
        message_box.setWindowTitle("Port Already Connected")
        message_box.setText("Port already connected!")
        message_box.setInformativeText(
            "Each port can only be connected to one link. Delete the existing link "
            "or choose a different unoccupied port."
        )
        message_box.setStandardButtons(QMessageBox.Ok)

        checkbox = QCheckBox("Do not show this warning again")
        message_box.setCheckBox(checkbox)

        message_box.exec()

        if checkbox.isChecked():
            self.suppress_port_occupied_warning = True

    def clear_subcomp_connector_compatibility_highlights(self):
        for node in self.component_items():
            for connector in self.subcomp_connectors_for_node(node):
                connector.set_compatibility_highlight("")

    def highlight_compatible_subcomp_connectors(self, source_connector: SubcompConnectorItem):
        for node in self.component_items():
            for connector in self.subcomp_connectors_for_node(node):
                if connector is source_connector:
                    continue

                if self.subcomp_connector_is_connected(connector):
                    continue

                pair = self.compatible_subcomp_connector_pair(source_connector, connector)
                if pair is None:
                    continue

                slot_connector, interface_connector = pair
                compatibility = self.check_subcomp_connector_compatibility(
                    slot_connector,
                    interface_connector,
                )

                if compatibility.severity == "error" or not compatibility.can_create:
                    continue

                if compatibility.severity == "warning":
                    connector.set_compatibility_highlight("warning")
                else:
                    connector.set_compatibility_highlight("compatible")

    def compatible_subcomp_connector_pair(
        self,
        source: SubcompConnectorItem,
        target: SubcompConnectorItem,
    ) -> tuple[SubcompConnectorItem, SubcompConnectorItem] | None:
        if source is target:
            return None

        source_role = getattr(source, "role", "")
        target_role = getattr(target, "role", "")

        if source_role == "slot" and target_role == "interface":
            return source, target

        if source_role == "interface" and target_role == "slot":
            return target, source

        return None

    def check_subcomp_connector_compatibility(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
    ) -> LinkCompatibilityResult:
        plugin_id = (
            self.active_plugin_id
            or getattr(slot_connector.node.component, "plugin_id", "")
            or getattr(interface_connector.node.component, "plugin_id", "")
        )

        if not plugin_id:
            return LinkCompatibilityResult()

        try:
            plugin = get_plugin_by_id(plugin_id)
        except Exception:
            return LinkCompatibilityResult()

        if not hasattr(plugin, "check_subcomponent_slot_compatibility"):
            return LinkCompatibilityResult()

        return plugin.check_subcomponent_slot_compatibility(
            getattr(slot_connector, "metadata", {}) or {},
            getattr(interface_connector, "metadata", {}) or {},
        )

    def default_subcomp_attachment_name(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
    ) -> str:
        base = (
            f"subcomp_{slot_connector.node.instance_name}_"
            f"{slot_connector.name}_{interface_connector.node.instance_name}"
        )
        return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in base)

    def create_subcomp_attachment(
        self,
        slot_connector: SubcompConnectorItem,
        interface_connector: SubcompConnectorItem,
        compatibility: LinkCompatibilityResult,
    ) -> SubcompAttachmentItem:
        attachment_id = self._next_subcomp_attachment_id
        self._next_subcomp_attachment_id += 1

        slot_metadata = getattr(slot_connector, "metadata", {}) or {}
        interface_metadata = getattr(interface_connector, "metadata", {}) or {}

        attachment = ModelSubcompAttachment(
            attachment_id=attachment_id,
            name=self.default_subcomp_attachment_name(slot_connector, interface_connector),
            parent_node_id=slot_connector.node.node_id,
            parent_component_name=slot_connector.node.instance_name,
            slot_name=slot_connector.name,
            child_node_id=interface_connector.node.node_id,
            child_component_name=interface_connector.node.instance_name,
            required_interface=(
                slot_metadata.get("required_interface", "")
                or slot_metadata.get("iface", "")
                or slot_metadata.get("interface", "")
                or ""
            ),
            provided_interface=(
                interface_metadata.get("provided_interface", "")
                or interface_metadata.get("iface", "")
                or interface_metadata.get("interface", "")
                or ""
            ),
            compatibility_severity=compatibility.severity,
            compatibility_code=compatibility.code,
            compatibility_message=compatibility.message,
            plugin_id=(
                self.active_plugin_id
                or getattr(slot_connector.node.component, "plugin_id", "")
            ),
            plugin_metadata={},
        )

        self.subcomp_attachments.append(attachment)

        item = SubcompAttachmentItem(
            attachment=attachment,
            slot_connector=slot_connector,
            interface_connector=interface_connector,
        )
        self.addItem(item)
        item.update_position()
        self.select_subcomp_attachment(item)
        self.notify_model_changed()

        return item

    def delete_subcomp_attachment(self, item: SubcompAttachmentItem):
        if item.attachment in self.subcomp_attachments:
            self.subcomp_attachments.remove(item.attachment)

        self.removeItem(item)

        if self.selected_subcomp_attachment is item:
            self.selected_subcomp_attachment = None

        if self.properties_panel is not None:
            self.properties_panel.show_empty()

        self.notify_model_changed()

    def subcomp_connector_clicked(self, connector: SubcompConnectorItem):
        if self.pending_source_port is not None:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_connection()
            return

        if self.subcomp_connector_is_connected(connector):
            return

        if self.pending_subcomp_connector is None:
            self.pending_subcomp_connector = connector
            self.clear_subcomp_connector_compatibility_highlights()
            self.highlight_compatible_subcomp_connectors(connector)

            self.pending_line = QGraphicsLineItem()
            self.pending_line.setPen(QPen(QColor("#8b5cf6"), 2, Qt.DashLine))
            self.pending_line.setZValue(4)
            self.pending_line.setAcceptedMouseButtons(Qt.NoButton)

            start = connector.scene_center()
            self.pending_line.setLine(start.x(), start.y(), start.x(), start.y())
            self.addItem(self.pending_line)
            return

        source_connector = self.pending_subcomp_connector
        target_connector = connector

        pair = self.compatible_subcomp_connector_pair(source_connector, target_connector)

        if pair is None:
            QMessageBox.warning(
                None,
                "Cannot Attach SubComponent",
                (
                    "SubComponent attachments must connect a parent "
                    "subcomp_connector slot to a subcomponent interface connector."
                ),
            )
            self.cancel_pending_subcomp_attachment()
            return

        slot_connector, interface_connector = pair

        if self.subcomp_connector_is_connected(slot_connector):
            self.cancel_pending_subcomp_attachment()
            return

        if self.subcomp_connector_is_connected(interface_connector):
            self.cancel_pending_subcomp_attachment()
            return

        compatibility = self.check_subcomp_connector_compatibility(
            slot_connector,
            interface_connector,
        )

        if compatibility.severity == "error" or not compatibility.can_create:
            QMessageBox.critical(
                None,
                compatibility.title or "Cannot Attach SubComponent",
                compatibility.message
                or "The selected subcomponent is not compatible with this slot.",
            )
            self.cancel_pending_subcomp_attachment()
            return

        if compatibility.severity == "warning":
            if not self.confirm_link_compatibility_warning(compatibility):
                self.cancel_pending_subcomp_attachment()
                return

        self.cancel_pending_visual_line_only()
        self.clear_subcomp_connector_compatibility_highlights()
        self.create_subcomp_attachment(
            slot_connector,
            interface_connector,
            compatibility,
        )
        self.pending_subcomp_connector = None

    def begin_subcomp_attachment(self, connector: SubcompConnectorItem):
        self.subcomp_connector_clicked(connector)

    def cancel_pending_visual_line_only(self):
        if self.pending_line is not None:
            self.removeItem(self.pending_line)
            self.pending_line = None

    def cancel_pending_connection(self):
        self.cancel_pending_visual_line_only()
        self.pending_source_port = None
        self.clear_port_compatibility_highlights()

    def cancel_pending_subcomp_attachment(self):
        self.cancel_pending_visual_line_only()
        self.pending_subcomp_connector = None
        self.clear_subcomp_connector_compatibility_highlights()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            if self.copy_selection_to_clipboard():
                event.accept()
                return

        if event.matches(QKeySequence.Paste):
            self.paste_clipboard()
            event.accept()
            return

        if event.key() == Qt.Key_G and event.modifiers() == Qt.ControlModifier:
            if self.group_selection():
                event.accept()
                return

        if event.key() == Qt.Key_G and event.modifiers() == (Qt.ControlModifier | Qt.ShiftModifier):
            if self.ungroup_selection():
                event.accept()
                return

        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected_connection is not None:
                self.delete_link(self.selected_connection)
                event.accept()
                return

            if self.selected_subcomp_attachment is not None:
                self.delete_subcomp_attachment(self.selected_subcomp_attachment)
                event.accept()
                return

            if self.selected_component is not None:
                self.delete_component_node(self.selected_component)
                event.accept()
                return

        super().keyPressEvent(event)

    def mouseMoveEvent(self, event):
        if self.pending_line is not None and self.pending_source_port is not None:
            start = self.pending_source_port.scene_center()
            end = event.scenePos()
            self.pending_line.setLine(start.x(), start.y(), end.x(), end.y())

        if self.pending_line is not None and self.pending_subcomp_connector is not None:
            start = self.pending_subcomp_connector.scene_center()
            end = event.scenePos()
            self.pending_line.setLine(start.x(), start.y(), end.x(), end.y())

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        clicked_items = self.items(event.scenePos())

        clicked_a_port = any(isinstance(item, PortItem) for item in clicked_items)
        clicked_a_subcomp_connector = any(
            isinstance(item, SubcompConnectorItem)
            for item in clicked_items
        )
        clicked_a_component = any(
            isinstance(item, ComponentNodeItem)
            for item in clicked_items
        )
        clicked_a_link = any(
            isinstance(item, ConnectionItem)
            for item in clicked_items
        )
        clicked_a_subcomp_attachment = any(
            isinstance(item, SubcompAttachmentItem)
            for item in clicked_items
        )

        # If the user mixes endpoint kinds, explain why the connection is not allowed.
        # Do this here because the scene may otherwise cancel the pending state before
        # the clicked item receives its own mouse event.
        if self.pending_source_port is not None and clicked_a_subcomp_connector:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_connection()
            event.accept()
            return

        if self.pending_subcomp_connector is not None and clicked_a_port:
            self.warn_mixed_endpoint_types()
            self.cancel_pending_subcomp_attachment()
            event.accept()
            return

        # Clicking empty canvas, or anything unrelated to the pending endpoint kind,
        # cancels pending creation state.
        if (
                self.pending_source_port is not None
                and not clicked_a_port
                and not clicked_a_subcomp_connector
        ):
            self.cancel_pending_connection()

        if (
                self.pending_subcomp_connector is not None
                and not clicked_a_subcomp_connector
                and not clicked_a_port
        ):
            self.cancel_pending_subcomp_attachment()

        if (
            not clicked_a_port
            and not clicked_a_subcomp_connector
            and not clicked_a_component
            and not clicked_a_link
            and not clicked_a_subcomp_attachment
        ):
            self.selected_component = None
            self.clear_all_selection_highlights()

            if self.properties_panel is not None:
                self.properties_panel.show_empty()

            if self.selection_changed_callback is not None:
                self.selection_changed_callback(None)

        super().mousePressEvent(event)