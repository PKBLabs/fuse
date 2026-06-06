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
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QBrush
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fuse.core.persistence.db_access import get_component_details
from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, SubcompAttachmentItem


class PropertiesPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.validation_issues_by_node: dict[int, dict[str, list[str]]] = {}
        self.current_node: Optional[ComponentNodeItem] = None
        self.current_link: Optional[ConnectionItem] = None
        self.current_subcomp_attachment: Optional[SubcompAttachmentItem] = None
        self.property_changed_callback = None
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

        self.delete_link_button = QPushButton("Delete Selected Link")
        self.delete_link_button.clicked.connect(self.delete_current_link)
        self.delete_link_button.setText("Delete Selected Link")
        self.delete_link_button.setVisible(False)
        layout.addWidget(self.delete_link_button)

    def show_empty(self):
        self._loading = True
        self.current_node = None
        self.current_link = None
        self.current_subcomp_attachment = None
        self.title.setText("Nothing selected")
        self.tree.clear()
        self._loading = False
        self.delete_link_button.setVisible(False)

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
        self.current_subcomp_attachment = None
        self.title.setText("Component Instance")
        self.tree.clear()
        self.delete_link_button.setVisible(False)

        component = node.component
        component_is_composite = bool(int(getattr(component, "is_composite", 0) or 0))
        if component_is_composite:
            self.title.setText("Composite Component Instance")

        object_group = self.add_category("Object")

        name_item = self.add_property(
            object_group,
            "Name",
            node.instance_name,
            "component.name",
            editable=True,
        )

        name_issues = self.validation_issues_by_node.get(node.node_id, {}).get("name", [])
        if name_issues:
            self.mark_item_invalid(name_item, "\n".join(name_issues))

        if component_is_composite:
            kind_label = "Composite Component"
        else:
            kind_label = "SubComponent" if component.is_subcomp else "Component"

        self.add_property(
            object_group,
            "Kind",
            kind_label,
            "component.kind",
            editable=False,
        )
        self.add_property(object_group, "Element", component.element, "component.element", editable=False)
        self.add_property(object_group, "Component Type", component.name, "component.type", editable=False)
        self.add_property(object_group, "Interface", component.iface or "", "component.iface", editable=False)
        self.add_property(object_group, "Target", component.target_label or component.target_id or "", "component.target", editable=False)
        self.add_property(object_group, "Framework Version", component.framework_version or "", "component.framework_version", editable=False)

        icon_item = self.add_property(
            object_group,
            "Icon Path",
            getattr(node, "icon_path", ""),
            "component.icon_path",
            editable=True,
        )
        icon_item.setToolTip(1, "Path to the icon used for this component instance.")

        if component_is_composite:
            template_group = self.add_category("Composite Template")
            self.add_property(
                template_group,
                "Template Name",
                component.name,
                "component.composite.template_name",
                editable=False,
            )
            self.add_property(
                template_group,
                "Template ID",
                getattr(component, "composite_id", "") or "",
                "component.composite.template_id",
                editable=False,
            )

        if node.variable_port_templates:
            variable_ports_group = self.add_category("Variable Ports")

            for template in node.variable_port_templates:
                base_name = template.get("base_name", "") or template.get("name", "")
                count_parameter = template.get("count_parameter", "") or ""
                value = node.variable_port_counts.get(
                    base_name,
                    int(template.get("default_count", 1) or 1),
                )
                display_name = f"{base_name} count"
                if count_parameter:
                    display_name = f"{display_name} ({count_parameter})"

                item = self.add_property(
                    variable_ports_group,
                    display_name,
                    str(value),
                    f"component.variable_port.{base_name}",
                    editable=True,
                    metadata={
                        "name": base_name,
                        "description": template.get("description", ""),
                        "required": False,
                        "type": "variable_port_count",
                    },
                )
                item.setToolTip(0, template.get("description", ""))
                item.setToolTip(1, "Number of logical ports to expose for this component instance.")

        parameters_group = self.add_category("Parameters")

        for parameter in self.load_component_parameters(node):
            name = parameter.get("name", "")
            default_value = parameter.get("default_val", "")
            required = bool(parameter.get("required"))

            if default_value == "<required>":
                default_value = ""

            value = node.parameters.get(name, default_value)

            display_name = f"{name} *" if required else name

            item = self.add_property(
                parameters_group,
                display_name,
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

            if required:
                item.setToolTip(0, "Required parameter")
                item.setToolTip(1, "Required parameter")

            issues = self.validation_issues_by_node.get(node.node_id, {}).get(name, [])
            if issues:
                self.mark_item_invalid(item, "\n".join(issues))

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._loading = False

    def show_link(self, connection: ConnectionItem):
        self._loading = True
        self.current_node = None
        self.current_link = connection
        self.current_subcomp_attachment = None
        self.title.setText("Point-to-Point Link")
        self.tree.clear()
        self.delete_link_button.setVisible(True)

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

        if getattr(link, "compatibility_severity", "ok") != "ok":
            compatibility_group = self.add_category("Compatibility")
            item = self.add_property(
                compatibility_group,
                "Status",
                link.compatibility_severity,
                "link.compatibility.status",
                editable=False,
            )
            item.setToolTip(1, link.compatibility_message or "")
            self.add_property(
                compatibility_group,
                "Message",
                link.compatibility_message or "",
                "link.compatibility.message",
                editable=False,
            )

        latency_group = self.add_category("Endpoint Latencies")
        self.add_property(
            latency_group,
            "Source latency",
            link.source_latency,
            "link.parameter.source_latency",
            editable=True,
            metadata={
                "name": "source_latency",
                "required": True,
                "type": "latency",
            },
        )
        self.add_property(
            latency_group,
            "Target latency",
            link.target_latency,
            "link.parameter.target_latency",
            editable=True,
            metadata={
                "name": "target_latency",
                "required": True,
                "type": "latency",
            },
        )

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._loading = False

    def show_subcomp_attachment(self, attachment_item: SubcompAttachmentItem):
        self._loading = True
        self.current_node = None
        self.current_link = None
        self.current_subcomp_attachment = attachment_item
        self.title.setText("SubComponent Attachment")
        self.tree.clear()
        self.delete_link_button.setText("Delete Selected Attachment")
        self.delete_link_button.setVisible(True)

        attachment = attachment_item.attachment

        object_group = self.add_category("Object")
        self.add_property(object_group, "Name", attachment.name, "subcomp_attachment.name", editable=False)
        self.add_property(
            object_group,
            "Parent Slot",
            f"{attachment.parent_component_name}.{attachment.slot_name}",
            "subcomp_attachment.parent_slot",
            editable=False,
        )
        self.add_property(
            object_group,
            "SubComponent",
            attachment.child_component_name,
            "subcomp_attachment.child",
            editable=False,
        )

        interface_group = self.add_category("Interfaces")
        self.add_property(
            interface_group,
            "Required Interface",
            attachment.required_interface or "",
            "subcomp_attachment.required_interface",
            editable=False,
        )
        self.add_property(
            interface_group,
            "Provided Interface",
            attachment.provided_interface or "",
            "subcomp_attachment.provided_interface",
            editable=False,
        )

        if attachment.compatibility_severity != "ok":
            compatibility_group = self.add_category("Compatibility")
            self.add_property(
                compatibility_group,
                "Status",
                attachment.compatibility_severity,
                "subcomp_attachment.compatibility.status",
                editable=False,
            )
            self.add_property(
                compatibility_group,
                "Message",
                attachment.compatibility_message or "",
                "subcomp_attachment.compatibility.message",
                editable=False,
            )

        self.tree.expandAll()
        self.tree.resizeColumnToContents(0)
        self._loading = False

    def delete_current_link(self):
        if self.current_link is not None:
            scene = self.current_link.scene()

            if scene is not None and hasattr(scene, "delete_link"):
                scene.delete_link(self.current_link)
            return

        if self.current_subcomp_attachment is not None:
            scene = self.current_subcomp_attachment.scene()

            if scene is not None and hasattr(scene, "delete_subcomp_attachment"):
                scene.delete_subcomp_attachment(self.current_subcomp_attachment)

    def load_component_parameters(self, node: ComponentNodeItem) -> list[dict]:
        component_id = node.component.component_id

        if component_id is None:
            return []

        try:
            details = get_component_details(
                node.component.plugin_id,
                component_id,
                node.component.target_id,
            )
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

        elif key == "component.icon_path" and self.current_node is not None:
            self.current_node.set_icon_path(new_value)

        elif key == "link.name" and self.current_link is not None:
            self.current_link.link.name = new_value
            self.current_link.update_tooltip()

        elif key == "link.parameter.source_latency" and self.current_link is not None:
            self.current_link.link.source_latency = new_value
            self.current_link.update_tooltip()
        elif key == "link.parameter.target_latency" and self.current_link is not None:
            self.current_link.link.target_latency = new_value
            self.current_link.update_tooltip()
        elif key == "link.parameter.latency" and self.current_link is not None:
            # Backward-compatible legacy property key.
            self.current_link.link.latency = new_value
            self.current_link.update_tooltip()

        elif isinstance(key, str) and key.startswith("component.variable_port.") and self.current_node is not None:
            base_name = metadata.get("name") or key.rsplit(".", 1)[-1]
            ok, message = self.current_node.set_variable_port_count(base_name, int(new_value))

            if not ok:
                QMessageBox.warning(self, "Invalid Port Count", message)
                self._loading = True
                item.setText(1, old_value)
                self._loading = False
                return

        elif isinstance(key, str) and key.startswith("component.parameter.") and self.current_node is not None:
            parameter_name = metadata.get("name")
            if parameter_name:
                self.current_node.parameters[parameter_name] = new_value

        item.setData(1, Qt.UserRole + 1, new_value)

        if self.property_changed_callback is not None:
            self.property_changed_callback()

    def validate_value(self, key: str, value: str, metadata: dict) -> tuple[bool, str]:
        if key in {"component.name", "link.name"}:
            if not value:
                return False, "Name cannot be empty."

            if not self.name_is_unique(value):
                return False, f"The name '{value}' is already used. Enter a unique name."

            return True, ""

        if metadata.get("required", False) and not value:
            return False, "This parameter is required."

        if metadata.get("type") == "variable_port_count":
            try:
                count = int(value)
            except ValueError:
                return False, "Port count must be an integer."

            if count < 0:
                return False, "Port count cannot be negative."

            return True, ""

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

        if scene is None or not hasattr(scene, "items"):
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

    def set_validation_issues(self, issues):
        self.validation_issues_by_node = {}

        for issue in issues:
            if issue.node_id is None:
                continue

            parameter_name = issue.parameter_name or "_object"
            self.validation_issues_by_node.setdefault(issue.node_id, {})
            self.validation_issues_by_node[issue.node_id].setdefault(parameter_name, [])
            self.validation_issues_by_node[issue.node_id][parameter_name].append(issue.message)

        if self.current_node is not None:
            self.show_component(self.current_node)

    def mark_item_invalid(self, item: QTreeWidgetItem, message: str):
        background = QBrush(QColor("#fee2e2"))

        item.setBackground(0, background)
        item.setBackground(1, background)
        item.setToolTip(0, message)
        item.setToolTip(1, message)



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