from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from db_access import get_component_details
from graphics_items import ComponentNodeItem, ConnectionItem


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