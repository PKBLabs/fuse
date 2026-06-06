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

import re
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fuse.core.model.composite import CompositeComponentDefinition
from fuse.core.persistence.composite_component_files import (
    CompositeComponentFileError,
    import_composite_component_file,
    write_composite_component_file,
)
from fuse.core.persistence.composite_components import (
    delete_composite_component_definition,
    get_composite_component_definition,
    list_composite_component_definitions,
)


def safe_composite_file_stem(name: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", name.strip()).strip("._")
    return stem or "composite_component"


class CompositeComponentManagerDialog(QDialog):
    def __init__(self, parent=None, edit_requested_callback=None):
        super().__init__(parent)
        self.edit_requested_callback = edit_requested_callback
        self.setWindowTitle("Manage Composite Components")
        self.setMinimumSize(780, 420)
        self.changed = False
        self.definitions: list[CompositeComponentDefinition] = []

        self.help_label = QLabel(
            "Manage reusable composite component definitions stored in the local FUSE database."
        )
        self.help_label.setWordWrap(True)

        self.table = QTableWidget(0, 4, self)
        self.table.setHorizontalHeaderLabels(["Name", "Description", "Template ID", "Icon Path"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self.update_button_state)
        self.table.doubleClicked.connect(self.edit_selected_definition)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.import_button = QPushButton("Import...", self)
        self.edit_button = QPushButton("Edit...", self)
        self.export_button = QPushButton("Export...", self)
        self.delete_button = QPushButton("Delete", self)
        self.close_button = QPushButton("Close", self)

        self.import_button.clicked.connect(self.import_definition)
        self.edit_button.clicked.connect(self.edit_selected_definition)
        self.export_button.clicked.connect(self.export_selected_definition)
        self.delete_button.clicked.connect(self.delete_selected_definition)
        self.close_button.clicked.connect(self.accept)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.edit_button)
        button_layout.addWidget(self.export_button)
        button_layout.addWidget(self.delete_button)
        button_layout.addStretch(1)
        button_layout.addWidget(self.close_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.help_label)
        layout.addWidget(self.table)
        layout.addLayout(button_layout)

        self.reload_definitions()

    def reload_definitions(self) -> None:
        self.definitions = list_composite_component_definitions()
        self.table.setRowCount(len(self.definitions))

        for row, definition in enumerate(self.definitions):
            self.set_table_item(row, 0, definition.name)
            self.set_table_item(row, 1, definition.description)
            self.set_table_item(row, 2, definition.composite_id)
            self.set_table_item(row, 3, definition.icon_path)

        self.table.resizeColumnsToContents()
        self.update_button_state()

    def set_table_item(self, row: int, column: int, value: str) -> None:
        item = QTableWidgetItem(str(value or ""))
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.table.setItem(row, column, item)

    def selected_definition(self) -> CompositeComponentDefinition | None:
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            return None

        row = selected_rows[0].row()
        if row < 0 or row >= len(self.definitions):
            return None
        return self.definitions[row]

    def update_button_state(self) -> None:
        has_selection = self.selected_definition() is not None
        self.edit_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)

    def edit_selected_definition(self) -> None:
        definition = self.selected_definition()
        if definition is None or self.edit_requested_callback is None:
            return
        self.edit_requested_callback(definition)
        self.accept()

    def import_definition(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Composite Component",
            "",
            "FUSE Composite Component (*.fcc);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            definition = import_composite_component_file(path)
        except CompositeComponentFileError as exc:
            QMessageBox.warning(self, "Import Composite Component", str(exc))
            return

        self.changed = True
        self.reload_definitions()
        self.select_definition(definition.composite_id)
        QMessageBox.information(
            self,
            "Import Composite Component",
            f"Imported composite component '{definition.name}'.",
        )

    def export_selected_definition(self) -> None:
        definition = self.selected_definition()
        if definition is None:
            return

        default_path = str(Path.home() / f"{safe_composite_file_stem(definition.name)}.fcc")
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Composite Component",
            default_path,
            "FUSE Composite Component (*.fcc);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        stored_definition = get_composite_component_definition(definition.composite_id)
        if stored_definition is None:
            QMessageBox.warning(
                self,
                "Export Composite Component",
                "The selected composite component template could not be found.",
            )
            self.reload_definitions()
            return

        try:
            written_path = write_composite_component_file(stored_definition, path)
        except (CompositeComponentFileError, OSError) as exc:
            QMessageBox.warning(self, "Export Composite Component", str(exc))
            return

        QMessageBox.information(
            self,
            "Export Composite Component",
            f"Exported composite component '{stored_definition.name}' to {written_path}.",
        )

    def delete_selected_definition(self) -> None:
        definition = self.selected_definition()
        if definition is None:
            return

        response = QMessageBox.question(
            self,
            "Delete Composite Component",
            (
                f"Delete composite component '{definition.name}' from the local database?\n\n"
                "Existing project instances keep their saved instance data, but this template "
                "will no longer appear in the component catalog."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if response != QMessageBox.Yes:
            return

        delete_composite_component_definition(definition.composite_id)
        self.changed = True
        self.reload_definitions()

    def select_definition(self, composite_id: str) -> None:
        for row, definition in enumerate(self.definitions):
            if definition.composite_id == composite_id:
                self.table.selectRow(row)
                return
