# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from fuse.core.app_info import (
    APP_EDITION,
    APP_FULL_NAME,
    APP_NAME,
    APP_VERSION,
    COPYRIGHT_TEXT,
)
from fuse.core.resource_paths import FUSE_LOGO_PATH


class FuseSplashScreen(QWidget):
    def __init__(self):
        super().__init__(
            None,
            Qt.SplashScreen
            | Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint,
        )

        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(32, 32, 32, 32)

        self.card = QFrame(self)
        self.card.setObjectName("splashCard")
        self.card.setStyleSheet(
            """
            QFrame#splashCard {
                background: white;
                border-radius: 0px;
            }
            """
        )

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(6, 27, 52, 95))
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        self.image_label = QLabel(self.card)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setPixmap(build_splash_pixmap())
        card_layout.addWidget(self.image_label)

        self.message_label = QLabel("Initializing FUSE...", self.card)
        self.message_label.setAlignment(Qt.AlignCenter)
        self.message_label.setStyleSheet(
            """
            QLabel {
                color: #061b34;
                font-size: 13px;
                padding: 0 0 18px 0;
                background: white;
                border-radius: 0px;
            }
            """
        )
        card_layout.addWidget(self.message_label)

        outer_layout.addWidget(self.card)

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def center_on_screen(self) -> None:
        """
        Center the splash on the primary screen.

        This uses the final widget size and moves the top-left corner manually,
        which is more reliable than relying on the window manager's placement.
        """
        screen = QGuiApplication.primaryScreen()

        if screen is None:
            return

        available = screen.availableGeometry()

        self.adjustSize()
        self.setFixedSize(self.sizeHint())

        x = available.x() + int((available.width() - self.width()) / 2)
        y = available.y() + int((available.height() - self.height()) / 2)

        self.move(x, y)

    def show_centered(self) -> None:
        # Center before show.
        self.center_on_screen()

        self.show()

        # Let Qt/window manager realize the native window.
        QGuiApplication.processEvents()

        # Center again after show, because some Linux/WSL window managers
        # adjust frameless/tool/splash window geometry during show().
        self.center_on_screen()

        self.raise_()

    def finish(self, window: QWidget) -> None:
        self.close()

        if window is not None:
            window.raise_()
            window.activateWindow()


def build_splash_pixmap() -> QPixmap:
    width = 960
    height = 455

    pixmap = QPixmap(width, height)
    pixmap.fill(QColor("#ffffff"))

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.TextAntialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    navy = QColor("#061b34")
    gray = QColor("#53606d")

    if FUSE_LOGO_PATH.exists():
        logo = QPixmap(str(FUSE_LOGO_PATH))

        if not logo.isNull():
            # Logo placement area.
            # These control where the logo block lives in the splash.
            logo_area_x = 40
            logo_area_y = 32
            logo_area_width = width - 80
            logo_area_height = 300

            # These control how large the logo may become.
            # Increase these to make the logo larger without changing the splash size.
            logo = logo.scaled(
                1150,
                400,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

            # Center the scaled logo inside the fixed logo area.
            x = logo_area_x + int((logo_area_width - logo.width()) / 2)
            y = logo_area_y + int((logo_area_height - logo.height()) / 2)

            painter.drawPixmap(x, y, logo)
        else:
            _draw_text_logo(painter, width, navy)
    else:
        _draw_text_logo(painter, width, navy)

    painter.setPen(navy)
    version_font = QFont("Arial", 18)
    version_font.setBold(True)
    painter.setFont(version_font)

    painter.drawText(
        0,
        335,
        width,
        35,
        Qt.AlignCenter,
        f"{APP_EDITION}  •  Version {APP_VERSION}",
    )

    painter.setPen(gray)
    small_font = QFont("Arial", 13)
    painter.setFont(small_font)

    painter.drawText(
        0,
        375,
        width,
        30,
        Qt.AlignCenter,
        APP_FULL_NAME,
    )

    painter.drawText(
        0,
        407,
        width,
        30,
        Qt.AlignCenter,
        COPYRIGHT_TEXT,
    )

    painter.end()

    return pixmap


def _draw_text_logo(painter: QPainter, width: int, color: QColor) -> None:
    painter.setPen(color)

    logo_font = QFont("Arial", 64)
    logo_font.setBold(True)
    painter.setFont(logo_font)

    painter.drawText(
        0,
        120,
        width,
        90,
        Qt.AlignCenter,
        APP_NAME,
    )


def create_splash_screen() -> FuseSplashScreen:
    return FuseSplashScreen()