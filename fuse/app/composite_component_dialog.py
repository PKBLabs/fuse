# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)


class CompositeComponentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Composite Component")

        self.name_edit = QLineEdit(self)
        self.name_edit.setPlaceholderText("Composite component name")

        self.description_edit = QTextEdit(self)
        self.description_edit.setPlaceholderText("Optional description")
        self.description_edit.setFixedHeight(80)

        self.icon_path_edit = QLineEdit(self)
        self.icon_path_edit.setPlaceholderText("Optional relative or absolute icon path")

        browse_button = QPushButton("Browse...", self)
        browse_button.clicked.connect(self.browse_for_icon)

        icon_layout = QHBoxLayout()
        icon_layout.addWidget(self.icon_path_edit, 1)
        icon_layout.addWidget(browse_button)

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Description:", self.description_edit)
        form.addRow("Icon path:", icon_layout)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            self,
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        ok_button = self.buttons.button(QDialogButtonBox.Ok)
        ok_button.setEnabled(False)
        self.name_edit.textChanged.connect(
            lambda text: ok_button.setEnabled(bool(text.strip()))
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.buttons)

    def browse_for_icon(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Composite Component Icon",
            "",
            "Images (*.png *.jpg *.jpeg *.svg *.webp);;All Files (*)",
        )

        if path:
            self.icon_path_edit.setText(path)

    def composite_name(self) -> str:
        return self.name_edit.text().strip()

    def composite_description(self) -> str:
        return self.description_edit.toPlainText().strip()

    def icon_path(self) -> str:
        return self.icon_path_edit.text().strip()
