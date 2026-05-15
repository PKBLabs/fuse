from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from db_access import load_component_definitions
from models import MIME_COMPONENT


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