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

from collections import defaultdict

from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fuse.core.model.models import ComponentDefinition, MIME_COMPONENT
from fuse.core.persistence.db_access import (
    load_component_definitions,
    load_subcomp_connector_metadata_for_component,
)


ROLE_COMPONENT = Qt.UserRole
ROLE_IS_DRAGGABLE = Qt.UserRole + 1


class ComponentTree(QTreeWidget):
    def __init__(self, palette: "ComponentPalette"):
        super().__init__()
        self.palette = palette
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if item is None:
            return

        if not item.data(0, ROLE_IS_DRAGGABLE):
            return

        component = item.data(0, ROLE_COMPONENT)
        if component is None:
            return

        mime = QMimeData()
        mime.setData(MIME_COMPONENT, component.to_drag_text().encode("utf-8"))
        mime.setText(component.display_name)

        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)


class ComponentPalette(QWidget):
    VIEW_ELEMENT = "Element"
    VIEW_FUNCTION = "Function"
    VIEW_FLAT = "Flat"
    VIEW_COMPATIBLE = "Compatible"

    def __init__(self):
        super().__init__()

        self.active_plugin_id: str | None = None
        self.active_target_id: str | None = None

        self.components: list[ComponentDefinition] = []
        self.compatibility_context_node = None

        self.view_selector = QComboBox()
        self.view_selector.addItems(
            [
                self.VIEW_ELEMENT,
                self.VIEW_FUNCTION,
                self.VIEW_FLAT,
                self.VIEW_COMPATIBLE,
            ]
        )
        self.view_selector.currentTextChanged.connect(self.populate_tree)

        self.sort_alphabetically = QCheckBox("A-Z")
        self.sort_alphabetically.setChecked(True)
        self.sort_alphabetically.stateChanged.connect(self.populate_tree)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(QLabel("View:"))
        controls.addWidget(self.view_selector, 1)
        controls.addWidget(self.sort_alphabetically)

        self.tree = ComponentTree(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.tree)

    def set_active_target(self, plugin_id: str | None, target_id: str | None):
        self.active_plugin_id = plugin_id
        self.active_target_id = target_id
        self.load_components()

    def set_compatibility_context(self, node):
        self.compatibility_context_node = node

        if node is not None:
            self.view_selector.setCurrentText(self.VIEW_COMPATIBLE)

        self.populate_tree()

    def clear_compatibility_context(self):
        self.compatibility_context_node = None
        self.populate_tree()

    def load_components(self):
        try:
            self.components = load_component_definitions(
                plugin_id=self.active_plugin_id,
                target_id=self.active_target_id,
            )
        except TypeError:
            self.components = load_component_definitions()

        self.populate_tree()

    def sorted_components(self, components: list[ComponentDefinition]) -> list[ComponentDefinition]:
        if not self.sort_alphabetically.isChecked():
            return list(components)

        return sorted(
            components,
            key=lambda component: (
                component.element.lower(),
                int(component.is_subcomp or 0),
                component.name.lower(),
            ),
        )

    def populate_tree(self):
        self.tree.clear()

        view = self.view_selector.currentText()

        if view == self.VIEW_FUNCTION:
            self.populate_function_tree()
        elif view == self.VIEW_FLAT:
            self.populate_flat_tree()
        elif view == self.VIEW_COMPATIBLE:
            self.populate_compatible_tree()
        else:
            self.populate_element_tree()

        self.tree.expandToDepth(1)

    def make_group_item(self, text: str, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
        item = QTreeWidgetItem([text])
        item.setData(0, ROLE_IS_DRAGGABLE, False)
        item.setFlags(item.flags() & ~Qt.ItemIsDragEnabled)

        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)

        return item

    def make_component_item(
        self,
        component: ComponentDefinition,
        parent: QTreeWidgetItem | None = None,
        prefix: str = "",
    ) -> QTreeWidgetItem:
        kind = "SubComponent" if component.is_subcomp else "Component"
        label = f"{prefix}{component.name} ({kind})"

        if component.iface:
            label += f" [{component.iface}]"

        item = QTreeWidgetItem([label])
        item.setData(0, ROLE_COMPONENT, component)
        item.setData(0, ROLE_IS_DRAGGABLE, True)
        item.setToolTip(0, component.description or component.functionality or component.display_name)

        if component.is_subcomp:
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)

        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)

        return item

    def split_by_kind(
        self,
        components: list[ComponentDefinition],
    ) -> tuple[list[ComponentDefinition], list[ComponentDefinition]]:
        normal = [component for component in components if not component.is_subcomp]
        subcomponents = [component for component in components if component.is_subcomp]
        return normal, subcomponents

    def populate_element_tree(self):
        by_element: dict[str, list[ComponentDefinition]] = defaultdict(list)

        for component in self.components:
            by_element[component.element or "(No Element)"].append(component)

        element_names = list(by_element)
        if self.sort_alphabetically.isChecked():
            element_names.sort(key=str.lower)

        for element_name in element_names:
            element_item = self.make_group_item(element_name)
            normal, subcomponents = self.split_by_kind(
                self.sorted_components(by_element[element_name])
            )

            components_group = self.make_group_item("Components", element_item)
            for component in normal:
                self.make_component_item(component, components_group)

            subcomponents_group = self.make_group_item("SubComponents", element_item)
            for component in subcomponents:
                self.make_component_item(component, subcomponents_group, prefix="↳ ")

    def function_group_for_component(self, component: ComponentDefinition) -> str:
        text = " ".join(
            [
                component.category or "",
                component.functionality or "",
                component.description or "",
                component.element or "",
                component.name or "",
                component.iface or "",
            ]
        ).lower()

        rules = [
            ("CPU", ("cpu", "processor", "core", "miranda")),
            ("Memory", ("memory", "mem", "cache", "directory", "dram", "hbm", "ram")),
            ("Network", ("network", "router", "nic", "linkcontrol", "merlin", "mesh", "torus")),
            ("Bus / Interconnect", ("bus", "interconnect", "crossbar", "xbar")),
            ("I/O", ("io", "disk", "file", "trace", "reader", "writer")),
            ("Generator", ("generator", "spmv", "stream", "traffic")),
            ("Statistics / Debug", ("stat", "debug", "monitor", "profiler")),
        ]

        for group_name, tokens in rules:
            if any(token in text for token in tokens):
                return group_name

        return "Other"

    def populate_function_tree(self):
        by_function: dict[str, list[ComponentDefinition]] = defaultdict(list)

        for component in self.components:
            by_function[self.function_group_for_component(component)].append(component)

        function_names = list(by_function)
        if self.sort_alphabetically.isChecked():
            function_names.sort(key=str.lower)

        for function_name in function_names:
            function_item = self.make_group_item(function_name)

            by_element: dict[str, list[ComponentDefinition]] = defaultdict(list)
            for component in by_function[function_name]:
                by_element[component.element or "(No Element)"].append(component)

            element_names = list(by_element)
            if self.sort_alphabetically.isChecked():
                element_names.sort(key=str.lower)

            for element_name in element_names:
                element_item = self.make_group_item(element_name, function_item)
                normal, subcomponents = self.split_by_kind(
                    self.sorted_components(by_element[element_name])
                )

                for component in normal:
                    self.make_component_item(component, element_item)

                if subcomponents:
                    subcomponents_group = self.make_group_item("SubComponents", element_item)
                    for component in subcomponents:
                        self.make_component_item(component, subcomponents_group, prefix="↳ ")

    def populate_flat_tree(self):
        for component in self.sorted_components(self.components):
            prefix = "    ↳ " if component.is_subcomp else ""
            self.make_component_item(component, prefix=prefix)

    def populate_compatible_tree(self):
        if self.compatibility_context_node is None:
            self.make_group_item("No component or subcomponent selected")
            return

        context_component = getattr(self.compatibility_context_node, "component", None)

        if context_component is None:
            self.make_group_item("No component or subcomponent selected")
            return

        if int(getattr(context_component, "is_subcomp", 0) or 0):
            self.populate_components_compatible_with_subcomponent(context_component)
            return

        # For now, component compatibility is intentionally permissive. This
        # keeps the catalog useful until plugins expose richer compatibility
        # metadata for ordinary components.
        self.populate_element_tree()

    def populate_components_compatible_with_subcomponent(
        self,
        subcomponent: ComponentDefinition,
    ):
        iface = (subcomponent.iface or "").strip()

        if not iface:
            self.make_group_item(
                f"Selected subcomponent {subcomponent.name} has no known interface"
            )
            return

        compatible_components = []

        for component in self.components:
            if component.is_subcomp:
                continue

            if self.component_has_slot_for_interface(component, iface):
                compatible_components.append(component)

        if not compatible_components:
            self.make_group_item(f"No compatible parent components for {iface}")
            return

        title = self.make_group_item(f"Compatible parent components for {iface}")

        by_element: dict[str, list[ComponentDefinition]] = defaultdict(list)
        for component in compatible_components:
            by_element[component.element or "(No Element)"].append(component)

        element_names = list(by_element)
        if self.sort_alphabetically.isChecked():
            element_names.sort(key=str.lower)

        for element_name in element_names:
            element_item = self.make_group_item(element_name, title)
            for component in self.sorted_components(by_element[element_name]):
                self.make_component_item(component, element_item)

    def component_has_slot_for_interface(
        self,
        component: ComponentDefinition,
        iface: str,
    ) -> bool:
        try:
            connectors = load_subcomp_connector_metadata_for_component(
                component.plugin_id,
                str(component.component_id or ""),
                target_id=component.target_id,
            )
        except Exception:
            return False

        for connector in connectors:
            if connector.get("role") != "slot":
                continue

            required = (
                connector.get("required_interface", "")
                or connector.get("iface", "")
                or connector.get("interface", "")
                or ""
            ).strip()

            if required == iface:
                return True

        return False