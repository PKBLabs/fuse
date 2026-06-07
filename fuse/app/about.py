# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

"""About dialog and application identity text for the FUSE desktop UI."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

from fuse.core.app_info import (
    APP_EDITION,
    APP_FULL_NAME,
    APP_NAME,
    APP_VERSION,
    COPYRIGHT_TEXT,
    LICENSE_IDENTIFIER,
    LICENSE_SHORT,
    LICENSING_TEXT,
    ORG_NAME,
    PLUGIN_TEXT,
)
from fuse.core.resource_paths import FUSE_ICON_PATH


def build_about_text() -> str:
    """Build the plain-text content shown in the About dialog."""
    return (
        f"{APP_NAME} {APP_EDITION}\n"
        f"{APP_FULL_NAME}\n\n"
        f"Version: {APP_VERSION}\n"
        f"License: {LICENSE_IDENTIFIER} — {LICENSE_SHORT}\n"
        f"{COPYRIGHT_TEXT}\n\n"
        f"Developed by {ORG_NAME}\n\n"
        "Licensing model\n"
        f"{LICENSING_TEXT}\n\n"
        "Plugins\n"
        f"{PLUGIN_TEXT}\n\n"
        "Policy documents\n"
        "PLUGIN-POLICY.md\n"
        "PLUGIN-API-STABILITY.md\n"
    )


class AboutDialog(QDialog):
    """Frameless Qt dialog that displays product, version, license, and plugin policy information."""
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(f"About {APP_NAME}")
        self.setMinimumWidth(820)
        self.setMinimumHeight(670)
        self.setModal(True)

        # Native framed windows cannot reliably draw their own outside shadow.
        # Use a translucent frameless window and put the real content inside a
        # shadowed card.
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        self.setStyleSheet(
            """
            QDialog {
                background-color: transparent;
                color: #000000;
            }

            QFrame#aboutCard {
                background-color: #f8fafc;
                color: #000000;
                border: 1px solid #cbd5e1;
            }

            QLabel {
                color: #000000;
            }

            QLabel#titleBar {
                font-size: 13px;
                font-weight: 600;
                color: #111827;
            }

            QLabel#productTitle {
                font-size: 22px;
                font-weight: 700;
                color: #000000;
            }

            QLabel#subtitle {
                font-size: 13px;
                color: #000000;
            }

            QTextEdit {
                background-color: #f8fafc;
                color: #000000;
                border: none;
                font-size: 13px;
                selection-background-color: #2563eb;
            }

            QPushButton {
                background-color: #1f2937;
                color: #e5e7eb;
                border: 1px solid #4b5563;
                border-radius: 6px;
                padding: 7px 16px;
                min-width: 90px;
            }

            QPushButton:hover {
                background-color: #374151;
            }

            QPushButton#primaryButton {
                background-color: #2563eb;
                border: 1px solid #60a5fa;
                color: white;
            }

            QPushButton#primaryButton:hover {
                background-color: #1d4ed8;
            }

            QPushButton#windowCloseButton {
                background-color: transparent;
                color: #111827;
                border: none;
                border-radius: 0;
                padding: 2px 8px;
                min-width: 28px;
                font-size: 16px;
                font-weight: 700;
            }

            QPushButton#windowCloseButton:hover {
                background-color: #e5e7eb;
            }
            """
        )

        outer_layout = QVBoxLayout(self)

        # Transparent space around the card where the shadow can be painted.
        # If this margin is too small, the shadow is clipped.
        outer_layout.setContentsMargins(48, 48, 48, 48)
        outer_layout.setSpacing(0)

        card = QFrame(self)
        card.setObjectName("aboutCard")
        card.setFrameShape(QFrame.NoFrame)
        card.setAttribute(Qt.WA_StyledBackground, True)

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(56)
        shadow.setOffset(0, 14)
        shadow.setColor(QColor(0, 0, 0, 180))
        card.setGraphicsEffect(shadow)

        outer_layout.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(24, 14, 24, 18)
        root.setSpacing(16)

        title_bar_layout = QHBoxLayout()
        title_bar_layout.setContentsMargins(0, 0, 0, 0)

        title_bar = QLabel(f"About {APP_NAME}", self)
        title_bar.setObjectName("titleBar")
        title_bar.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)

        window_close_button = QPushButton("×", self)
        window_close_button.setObjectName("windowCloseButton")
        window_close_button.setFixedSize(32, 28)
        window_close_button.clicked.connect(self.accept)

        title_bar_layout.addWidget(title_bar, stretch=1)
        title_bar_layout.addWidget(window_close_button)

        root.addLayout(title_bar_layout)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(24)

        icon_label = QLabel(self)
        icon_label.setFixedSize(135, 135)
        icon_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        if FUSE_ICON_PATH.exists():
            pixmap = QPixmap(str(FUSE_ICON_PATH))
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    125,
                    125,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
                icon_label.setPixmap(pixmap)
            else:
                icon_label.setText(APP_NAME)
        else:
            icon_label.setText(APP_NAME)

        content_layout.addWidget(icon_label)

        right_layout = QVBoxLayout()
        right_layout.setSpacing(8)

        title = QLabel(f"{APP_NAME} {APP_VERSION}", self)
        title.setObjectName("productTitle")
        right_layout.addWidget(title)

        subtitle = QLabel(
            f"{APP_EDITION}<br>"
            f"Licensed under {LICENSE_IDENTIFIER}<br>"
            f"{COPYRIGHT_TEXT}",
            self,
        )
        subtitle.setObjectName("subtitle")
        subtitle.setTextFormat(Qt.RichText)
        right_layout.addWidget(subtitle)

        separator = QFrame(self)
        separator.setFrameShape(QFrame.HLine)
        separator.setStyleSheet("color: #c7cdd4; background-color: #c7cdd4;")
        right_layout.addWidget(separator)

        info = QTextEdit(self)
        info.setReadOnly(True)
        info.setPlainText(
            f"{APP_FULL_NAME}\n\n"
            f"Developed by {ORG_NAME}\n\n"
            f"License: {LICENSE_SHORT}\n\n"
            "FUSE uses an open-core licensing model.\n\n"
            "The FUSE Community Edition is free software licensed under the "
            "GNU General Public License, version 3 or later.\n\n"
            "PKB Research Labs, LLC may also offer commercial licenses, paid "
            "plugins, commercial model libraries, enterprise integrations, "
            "support, training, and custom development services.\n\n"
            "FUSE supports a public, versioned plugin API. The Community "
            "Edition currently ships with SST and gem5 community plugin "
            "directories.\n\n"
            "See PLUGIN-POLICY.md and PLUGIN-API-STABILITY.md."
        )
        right_layout.addWidget(info, stretch=1)

        content_layout.addLayout(right_layout, stretch=1)
        root.addLayout(content_layout, stretch=1)

        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        copy_button = QPushButton("Copy and Close", self)
        copy_button.setObjectName("primaryButton")
        copy_button.clicked.connect(self.copy_and_close)

        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.accept)

        button_layout.addWidget(copy_button)
        button_layout.addWidget(close_button)

        root.addLayout(button_layout)

    def copy_and_close(self):
        clipboard = QGuiApplication.clipboard()
        clipboard.setText(build_about_text())
        self.accept()