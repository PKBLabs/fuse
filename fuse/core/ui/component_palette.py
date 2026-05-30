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
import json
from collections import defaultdict
from PySide6.QtCore import (
    Qt,
    QMimeData,
    QSize,
    QSettings,
)
from PySide6.QtGui import QDrag, QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from fuse.core.resource_paths import resolve_icon_path
from fuse.core.model.models import ComponentDefinition, MIME_COMPONENT
from fuse.core.persistence.db_access import (
    load_component_definitions,
    load_subcomp_connector_metadata_for_component,
)


ROLE_COMPONENT = Qt.UserRole
ROLE_IS_DRAGGABLE = Qt.UserRole + 1
MAX_RECENT_COMPONENTS = 15
MAX_FREQUENT_COMPONENTS = 9


class ComponentTree(QTreeWidget):
    def __init__(self, palette: "ComponentPalette"):
        super().__init__()
        self.palette = palette
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setDragEnabled(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.SingleSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

        self.setStyleSheet(
            """
            QTreeWidget::item {
                min-height: 24px;
                padding-top: 2px;
                padding-bottom: 2px;
            }
            """
        )

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

    def show_context_menu(self, position):
        item = self.itemAt(position)
        if item is None or not item.data(0, ROLE_IS_DRAGGABLE):
            return

        component = item.data(0, ROLE_COMPONENT)
        if component is None:
            return

        menu = QMenu(self)
        add_action = menu.addAction("Add to Frequently Used")
        remove_action = menu.addAction("Remove from Frequently Used")

        action = menu.exec(self.viewport().mapToGlobal(position))

        if action == add_action:
            self.palette.add_to_frequently_used(component)
        elif action == remove_action:
            self.palette.remove_from_frequently_used(component)


class ComponentTileButton(QToolButton):
    def __init__(self, palette: "ComponentPalette", component: ComponentDefinition):
        super().__init__()
        self.palette = palette
        self.component = component

        self.setText(component.name)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(42, 42))
        self.setFixedSize(QSize(92, 76))
        self.setToolTip(palette.tooltip_for_component(component))

        if component.icon_path:
            path = resolve_icon_path(component.icon_path)
            if path.exists():
                self.setIcon(QIcon(str(path)))

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_context_menu)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            mime = QMimeData()
            mime.setData(MIME_COMPONENT, self.component.to_drag_text().encode("utf-8"))
            mime.setText(self.component.display_name)

            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.CopyAction)
            return

        super().mouseMoveEvent(event)

    def show_context_menu(self, position):
        menu = QMenu(self)

        add_action = menu.addAction("Add to Frequently Used")
        remove_action = menu.addAction("Remove from Frequently Used")

        action = menu.exec(self.mapToGlobal(position))

        if action == add_action:
            self.palette.add_to_frequently_used(self.component)
        elif action == remove_action:
            self.palette.remove_from_frequently_used(self.component)


class ComponentPalette(QWidget):
    VIEW_ELEMENT = "Element"
    VIEW_FUNCTION = "Function"
    VIEW_FLAT = "Flat"
    VIEW_RECENT = "Recent"
    VIEW_COMPATIBLE = "Compatible SubComponents"

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
                self.VIEW_RECENT,
                self.VIEW_COMPATIBLE,
                self.VIEW_FLAT,
            ]
        )
        self.view_selector.currentTextChanged.connect(self.populate_tree)

        self.sort_alphabetically = QCheckBox("A-Z")
        self.sort_alphabetically.setChecked(True)
        self.sort_alphabetically.stateChanged.connect(self.populate_tree)
        self.recent_component_ids: list[str] = []
        self.frequent_component_counts: dict[str, int] = {}
        self.pinned_frequent_component_ids: set[str] = set()
        self.hidden_frequent_component_ids: set[str] = set()

        self.settings = QSettings("PKB Research Labs", "FUSE")
        self.load_usage_settings()
        self.quick_section = QWidget()
        self.quick_layout = QVBoxLayout(self.quick_section)
        self.quick_layout.setContentsMargins(0, 0, 0, 0)

        self.frequent_label = QLabel("Frequently Used")
        self.frequent_grid_widget = QWidget()
        self.frequent_grid = QGridLayout(self.frequent_grid_widget)
        self.frequent_grid.setContentsMargins(0, 0, 0, 0)
        self.frequent_grid.setHorizontalSpacing(8)
        self.frequent_grid.setVerticalSpacing(8)
        self.quick_layout.addWidget(self.frequent_label)
        self.quick_layout.addWidget(self.frequent_grid_widget)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(QLabel("View:"))
        controls.addWidget(self.view_selector, 1)
        controls.addWidget(self.sort_alphabetically)

        self.tree = ComponentTree(self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(controls)
        layout.addWidget(self.quick_section)
        layout.addWidget(self.tree, 1)

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
        self.refresh_quick_sections()

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
        elif view == self.VIEW_RECENT:
            self.populate_recent_tree()
        elif view == self.VIEW_COMPATIBLE:
            self.populate_compatible_tree()
        else:
            self.populate_element_tree()

        self.tree.expandToDepth(1)

    def populate_recent_tree(self):
        recent = self.recent_components()

        if not recent:
            self.make_group_item("No recent components or subcomponents")
            return

        for component in recent:
            self.make_component_item(component)

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
        label = f"{prefix}{component.name}"

        item = QTreeWidgetItem([label])
        item.setData(0, ROLE_COMPONENT, component)
        item.setData(0, ROLE_IS_DRAGGABLE, True)
        item.setToolTip(
            0,
            self.tooltip_for_component(component),
        )

        if component.is_subcomp:
            font = item.font(0)
            font.setItalic(True)
            item.setFont(0, font)

        if parent is None:
            self.tree.addTopLevelItem(item)
        else:
            parent.addChild(item)

        return item

    def tooltip_for_component(self, component: ComponentDefinition) -> str:
        lines = [component.display_name or component.name]

        if component.description:
            lines.append("")
            lines.append(component.description)

        if component.functionality:
            lines.append("")
            lines.append(f"Function: {component.functionality}")

        if component.iface:
            lines.append("")
            lines.append(f"Interface: {component.iface}")

        if component.category:
            lines.append("")
            lines.append(f"Category: {component.category}")

        return "\n".join(lines)

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
            self.populate_element_tree()
            return

        context_component = getattr(self.compatibility_context_node, "component", None)

        if context_component is None:
            self.populate_element_tree()
            return

        # Compatible SubComponents view is driven by the selected component's
        # subcomponent slots. If the selected item is itself a subcomponent, fall
        # back to the normal hierarchy for now.
        if int(getattr(context_component, "is_subcomp", 0) or 0):
            self.populate_element_tree()
            return

        required_interfaces = self.required_subcomponent_interfaces_for_component(
            context_component
        )

        if not required_interfaces:
            self.populate_element_tree()
            return

        compatible_subcomponents = [
            component
            for component in self.components
            if int(component.is_subcomp or 0)
               and (component.iface or "").strip() in required_interfaces
        ]

        if not compatible_subcomponents:
            self.make_group_item(
                "No compatible SubComponents found for selected component slots"
            )
            return

        title = self.make_group_item("Compatible SubComponents")

        by_interface: dict[str, list[ComponentDefinition]] = defaultdict(list)
        for component in compatible_subcomponents:
            by_interface[(component.iface or "(Unknown Interface)").strip()].append(component)

        interface_names = list(by_interface)
        if self.sort_alphabetically.isChecked():
            interface_names.sort(key=str.lower)

        for interface_name in interface_names:
            interface_item = self.make_group_item(interface_name, title)

            by_element: dict[str, list[ComponentDefinition]] = defaultdict(list)
            for component in by_interface[interface_name]:
                by_element[component.element or "(No Element)"].append(component)

            element_names = list(by_element)
            if self.sort_alphabetically.isChecked():
                element_names.sort(key=str.lower)

            for element_name in element_names:
                element_item = self.make_group_item(element_name, interface_item)
                for component in self.sorted_components(by_element[element_name]):
                    self.make_component_item(component, element_item, prefix="↳ ")

    def required_subcomponent_interfaces_for_component(
            self,
            component: ComponentDefinition,
    ) -> set[str]:
        try:
            connectors = load_subcomp_connector_metadata_for_component(
                component.plugin_id,
                str(component.component_id or ""),
                target_id=component.target_id,
            )
        except Exception:
            return set()

        required_interfaces: set[str] = set()

        for connector in connectors:
            if connector.get("role") != "slot":
                continue

            required = (
                    connector.get("required_interface", "")
                    or connector.get("iface", "")
                    or connector.get("interface", "")
                    or ""
            ).strip()

            if required:
                required_interfaces.add(required)

        return required_interfaces

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

    def component_key(self, component: ComponentDefinition) -> str:
        return "|".join(
            [
                component.plugin_id or "",
                component.target_id or "",
                str(component.component_id or ""),
                component.name or "",
            ]
        )

    def component_by_key(self, key: str) -> ComponentDefinition | None:
        for component in self.components:
            if self.component_key(component) == key:
                return component

        return None

    def clear_grid(self, grid: QGridLayout):
        while grid.count():
            item = grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def refresh_quick_sections(self):
        self.clear_grid(self.frequent_grid)

        frequent_components = self.frequent_components()

        self.frequent_label.setVisible(bool(frequent_components))
        self.frequent_grid_widget.setVisible(bool(frequent_components))

        for index, component in enumerate(frequent_components):
            self.frequent_grid.addWidget(
                ComponentTileButton(self, component),
                index // 3,
                index % 3,
            )

    def recent_components(self) -> list[ComponentDefinition]:
        result = []

        for key in self.recent_component_ids:
            component = self.component_by_key(key)
            if component is not None:
                result.append(component)

        return result[:MAX_RECENT_COMPONENTS]

    def frequent_components(self) -> list[ComponentDefinition]:
        candidates = []

        for key, count in self.frequent_component_counts.items():
            if key in self.hidden_frequent_component_ids:
                continue

            component = self.component_by_key(key)
            if component is not None:
                candidates.append((component, count))

        for key in self.pinned_frequent_component_ids:
            if key in self.hidden_frequent_component_ids:
                continue

            component = self.component_by_key(key)
            if component is not None and all(self.component_key(item[0]) != key for item in candidates):
                candidates.append((component, 10_000_000))

        candidates.sort(
            key=lambda item: (-item[1], item[0].name.lower())
        )

        return [component for component, _count in candidates[:MAX_FREQUENT_COMPONENTS]]

    def record_component_used(self, component: ComponentDefinition):
        key = self.component_key(component)

        self.recent_component_ids = [
            existing for existing in self.recent_component_ids if existing != key
        ]
        self.recent_component_ids.insert(0, key)
        self.recent_component_ids = self.recent_component_ids[:MAX_RECENT_COMPONENTS]

        self.frequent_component_counts[key] = self.frequent_component_counts.get(key, 0) + 1

        self.refresh_quick_sections()

        if self.view_selector.currentText() == self.VIEW_RECENT:
            self.populate_tree()

        self.save_usage_settings()

    def add_to_frequently_used(self, component: ComponentDefinition):
        key = self.component_key(component)
        self.hidden_frequent_component_ids.discard(key)
        self.pinned_frequent_component_ids.add(key)
        self.frequent_component_counts[key] = max(
            self.frequent_component_counts.get(key, 0),
            1,
        )
        self.refresh_quick_sections()
        self.save_usage_settings()

    def remove_from_frequently_used(self, component: ComponentDefinition):
        key = self.component_key(component)
        self.pinned_frequent_component_ids.discard(key)
        self.hidden_frequent_component_ids.add(key)
        self.refresh_quick_sections()
        self.save_usage_settings()

    def load_usage_settings(self):
        recent = self.settings.value("componentPalette/recent", [], list)
        pinned = self.settings.value("componentPalette/pinnedFrequent", [], list)
        hidden = self.settings.value("componentPalette/hiddenFrequent", [], list)

        counts_text = self.settings.value(
            "componentPalette/frequentCountsJson",
            "{}",
            str,
        )

        self.recent_component_ids = list(recent or [])
        self.pinned_frequent_component_ids = set(pinned or [])
        self.hidden_frequent_component_ids = set(hidden or [])

        try:
            counts = json.loads(counts_text or "{}")
        except (TypeError, json.JSONDecodeError):
            counts = {}

        self.frequent_component_counts = {}

        if isinstance(counts, dict):
            for key, value in counts.items():
                try:
                    self.frequent_component_counts[str(key)] = int(value)
                except (TypeError, ValueError):
                    continue

    def save_usage_settings(self):
        self.settings.setValue("componentPalette/recent", self.recent_component_ids)
        self.settings.setValue(
            "componentPalette/pinnedFrequent",
            list(self.pinned_frequent_component_ids),
        )
        self.settings.setValue(
            "componentPalette/hiddenFrequent",
            list(self.hidden_frequent_component_ids),
        )
        self.settings.setValue(
            "componentPalette/frequentCountsJson",
            json.dumps(self.frequent_component_counts),
        )