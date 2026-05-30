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

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPen, QColor
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

        self.model_changed_callback = None
        self.component_added_callback = None

        self.active_plugin_id: str | None = None
        self.selected_connection: Optional[ConnectionItem] = None
        self.selected_subcomp_attachment: Optional[SubcompAttachmentItem] = None
        self.suppress_mixed_endpoint_warning = False
        self.suppress_port_occupied_warning = False

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
        self.selected_connection = None
        self.selected_subcomp_attachment = None
        self.highlight_links_for_node(node)

        if self.properties_panel is not None:
            self.properties_panel.show_component(node)

    def select_link(self, connection: ConnectionItem):
        self.clear_all_selection_highlights()
        self.selected_connection = connection
        connection.set_highlighted(True)

        if self.properties_panel is not None:
            self.properties_panel.show_link(connection)

    def select_subcomp_attachment(self, attachment: SubcompAttachmentItem):
        self.clear_all_selection_highlights()
        self.selected_subcomp_attachment = attachment
        attachment.set_highlighted(True)

        if self.properties_panel is not None:
            self.properties_panel.show_subcomp_attachment(attachment)

    def begin_node_drag(self):
        self._dragging_node = True
        self._reroute_timer.stop()

    def end_node_drag(self, node: Optional["ComponentNodeItem"] = None):
        """
        End an interactive drag.

        Scalability rule: do NOT reroute the entire model automatically here.
        Instead, reroute:
          1. links attached to the moved node,
          2. subcomponent attachment edges attached to the moved node, and
          3. existing links whose current route now intersects the moved node box.
        """
        self._dragging_node = False

        if node is not None:
            self.reroute_links_affected_by_node(node)
            self.update_subcomp_attachments_for_node(node)

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
        plugin_id = self.active_plugin_id or getattr(source_port.node.component, "plugin_id", "")

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
            plugin_id=self.active_plugin_id or getattr(source_port.node.component, "plugin_id", ""),
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
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            if self.selected_connection is not None:
                self.delete_link(self.selected_connection)
                event.accept()
                return

            if self.selected_subcomp_attachment is not None:
                self.delete_subcomp_attachment(self.selected_subcomp_attachment)
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
            self.clear_all_selection_highlights()

            if self.properties_panel is not None:
                self.properties_panel.show_empty()

        super().mousePressEvent(event)