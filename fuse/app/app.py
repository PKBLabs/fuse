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
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QElapsedTimer, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDockWidget,
    QFileDialog,
    QLabel,
    QListWidget,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from fuse.app.about import AboutDialog
from fuse.app.project_settings_dialog import ProjectSettingsDialog
from fuse.app.splash import create_splash_screen
from fuse.core.app_info import APP_NAME, ORG_NAME
from fuse.core.model.project_settings import ProjectSettings
from fuse.core.model.validation import validate_model
from fuse.core.persistence.db_access import ensure_database_ready, load_framework_targets
from fuse.core.persistence.project_io import (
    build_project_dict,
    load_project_file,
    load_project_into_scene,
    save_project_file,
)
from fuse.core.ui.component_palette import ComponentPalette
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.ui.properties_panel import PropertiesPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FUSE")
        self.resize(1300, 800)

        self.current_project_path: Optional[Path] = None
        self.project_name = "Untitled FUSE Project"
        self.project_settings = ProjectSettings(
            project_name=self.project_name,
            active_plugin_id="sst",
        )
        self.active_plugin_id: str | None = None
        self.active_target_id: str | None = None
        self.is_dirty = False

        self.palette = ComponentPalette()
        self.scene = ModelScene()
        self.model_view = ModelView(self.scene)
        self.properties_panel = PropertiesPanel()
        self.model_outline = QListWidget()

        self.properties_dock: QDockWidget | None = None
        self.model_outline_dock: QDockWidget | None = None

        self.scene.properties_panel = self.properties_panel
        self.scene.model_changed_callback = self.mark_dirty
        self.scene.component_added_callback = self.on_component_added
        self.scene.selection_changed_callback = self.on_scene_selection_changed
        self.properties_panel.property_changed_callback = self.on_property_changed

        self.setup_menu_bar()
        self.setup_layout()
        self.setup_docks()
        self.setup_status_bar()

        ensure_database_ready()
        self.load_framework_targets()

    def setup_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        tools_menu = menu_bar.addMenu("Tools")
        help_menu = menu_bar.addMenu("Help")

        new_action = QAction("New Project...", self)
        open_action = QAction("Open Project...", self)
        project_settings_action = QAction("Project Settings...", self)
        save_action = QAction("Save", self)
        save_as_action = QAction("Save As...", self)
        export_sst_json_action = QAction("SST JSON...", self)
        exit_action = QAction("Exit", self)

        new_action.triggered.connect(self.new_project)
        open_action.triggered.connect(self.open_model)
        project_settings_action.triggered.connect(self.show_project_settings)
        save_action.triggered.connect(self.save_model)
        save_as_action.triggered.connect(self.save_model_as)
        export_sst_json_action.triggered.connect(self.export_sst_json)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(project_settings_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)

        export_menu = file_menu.addMenu("Export")
        export_menu.addAction(export_sst_json_action)

        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        refresh_action = QAction("Refresh Component List", self)
        refresh_action.triggered.connect(self.load_framework_targets)
        tools_menu.addAction(refresh_action)

        show_links_action = QAction("Show Links", self)
        show_links_action.triggered.connect(self.show_links)
        tools_menu.addAction(show_links_action)

        reroute_all_action = QAction("Reroute All Links", self)
        reroute_all_action.triggered.connect(self.scene.reroute_all_links)
        tools_menu.addAction(reroute_all_action)

        about_action = QAction("About FUSE", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        edit_menu.addAction(QAction("Undo", self))
        edit_menu.addAction(QAction("Redo", self))
        view_menu.addAction(QAction("Zoom In", self))
        view_menu.addAction(QAction("Zoom Out", self))

    def setup_layout(self):
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.addWidget(QLabel("Available Components"))
        left_layout.addWidget(self.palette)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left_panel)
        splitter.addWidget(self.model_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 4)
        splitter.setSizes([320, 980])

        self.setCentralWidget(splitter)

    def make_dock(self, title: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setWidget(widget)
        dock.setAllowedAreas(
            Qt.LeftDockWidgetArea
            | Qt.RightDockWidgetArea
            | Qt.TopDockWidgetArea
            | Qt.BottomDockWidgetArea
        )
        dock.setFeatures(
            QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
            | QDockWidget.DockWidgetClosable
        )
        return dock

    def setup_docks(self):
        """
        Create the default dock layout.

        The right dock column is split vertically:
        - Properties: about 60% of the column height
        - Model Outline: about 40% of the column height

        Users can still resize, move, float, or close these docks.
        """
        self.properties_dock = self.make_dock("Properties", self.properties_panel)
        self.model_outline_dock = self.make_dock("Model Outline", self.model_outline)

        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)
        self.splitDockWidget(
            self.properties_dock,
            self.model_outline_dock,
            Qt.Vertical,
        )

        # Approximate 60/40 default vertical split in the right dock column.
        # The user can adjust this interactively at runtime.
        self.resizeDocks(
            [self.properties_dock, self.model_outline_dock],
            [600, 400],
            Qt.Vertical,
        )

        # Give the right dock column a reasonable initial width.
        self.resizeDocks(
            [self.properties_dock],
            [360],
            Qt.Horizontal,
        )

    def setup_status_bar(self):
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def load_framework_targets(self):
        """Initialize the project target from imported plugin targets.

        New projects default to the imported default SST catalog. Existing
        projects keep their saved project settings.
        """
        targets = load_framework_targets()
        active = self.project_settings.active_plugin_settings()

        if active is None or not active.target_id:
            chosen = None
            for target in targets:
                if target.plugin_id == "sst" and target.is_default:
                    chosen = target
                    break

            if chosen is None:
                for target in targets:
                    if target.plugin_id == "sst":
                        chosen = target
                        break

            if chosen is not None:
                self.project_settings.active_plugin_id = chosen.plugin_id
                settings = self.project_settings.plugin_settings(chosen.plugin_id)
                settings.enabled = True
                settings.target_id = chosen.target_id
                settings.target_label = chosen.display_name
                settings.framework_version = chosen.framework_version

        self.apply_project_settings_to_ui()

    def apply_project_settings_to_ui(self):
        active = self.project_settings.active_plugin_settings()

        if active is None or not active.enabled:
            self.active_plugin_id = None
            self.active_target_id = None
            self.scene.active_plugin_id = None
            self.palette.set_active_target(None, None)
            return

        self.active_plugin_id = active.plugin_id
        self.active_target_id = active.target_id
        self.scene.active_plugin_id = active.plugin_id

        self.palette.set_active_target(active.plugin_id, active.target_id)

    def show_project_settings(self):
        dialog = ProjectSettingsDialog(self.project_settings, self)

        if dialog.exec() != QDialog.Accepted:
            return

        new_settings = dialog.settings()
        old_active = self.project_settings.active_plugin_settings()
        new_active = new_settings.active_plugin_settings()

        old_key = (
            old_active.plugin_id if old_active else "",
            old_active.target_id if old_active else "",
        )
        new_key = (
            new_active.plugin_id if new_active else "",
            new_active.target_id if new_active else "",
        )

        if self.scene.component_items() and old_key != new_key:
            response = QMessageBox.warning(
                self,
                "Project Target Changed",
                (
                    "Changing the framework target for a non-empty project can make "
                    "existing components, ports, parameters, or links invalid.\n\n"
                    "FUSE will keep the model unchanged and validation will report "
                    "any incompatibilities. Continue?"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if response != QMessageBox.Yes:
                return

        self.project_settings = new_settings
        self.project_name = self.project_settings.project_name or self.project_name
        self.apply_project_settings_to_ui()
        self.statusBar().showMessage("Project settings updated", 3000)
        self.mark_dirty()

    def on_component_added(self, node):
        self.update_model_outline()

    def on_scene_selection_changed(self, node):
        if node is None:
            self.palette.clear_compatibility_context()
        else:
            self.palette.set_compatibility_context(node)

    def on_property_changed(self):
        self.update_model_outline()
        self.mark_dirty()

    def update_model_outline(self):
        self.model_outline.clear()

        for node in self.scene.component_items():
            self.model_outline.addItem(node.instance_name)

    def set_dirty(self, dirty: bool):
        self.is_dirty = dirty
        marker = "*" if dirty else ""

        if self.current_project_path is not None:
            self.setWindowTitle(f"FUSE - {self.current_project_path.name}{marker}")
        else:
            self.setWindowTitle(f"FUSE{marker}")

    def mark_dirty(self):
        self.set_dirty(True)

    def new_project(self):
        settings = ProjectSettings(
            project_name="Untitled FUSE Project",
            active_plugin_id="sst",
        )

        dialog = ProjectSettingsDialog(settings, self)

        if dialog.exec() != QDialog.Accepted:
            return

        self.project_settings = dialog.settings()
        self.project_name = self.project_settings.project_name or "Untitled FUSE Project"
        self.scene.clear_model()
        self.properties_panel.set_validation_issues([])
        self.properties_panel.show_empty()
        self.set_current_project_path(None)
        self.apply_project_settings_to_ui()
        self.update_model_outline()
        self.set_dirty(False)
        self.statusBar().showMessage("New project created", 3000)

    def new_model(self):
        # Backward-compatible alias for older tests/callers.
        self.new_project()

    def project_dict(self) -> dict:
        self.project_settings.project_name = self.project_name
        return build_project_dict(
            self.scene,
            self.model_view,
            self.project_name,
            active_plugin_id=self.active_plugin_id,
            active_target_id=self.active_target_id,
            project_settings=self.project_settings,
        )

    def set_current_project_path(self, path: Optional[str | Path]) -> None:
        self.current_project_path = Path(path) if path else None

        if self.current_project_path is not None:
            self.project_name = self.current_project_path.stem
        else:
            self.project_name = "Untitled FUSE Project"

        self.set_dirty(self.is_dirty)

    def save_model(self):
        if not self.validate_model_before_save():
            return

        if self.current_project_path is None:
            self.save_model_as()
            return

        project = self.project_dict()
        save_project_file(project, self.current_project_path)
        self.set_dirty(False)
        self.statusBar().showMessage(f"Saved {self.current_project_path}", 3000)

    def save_model_as(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FUSE Model",
            str(self.current_project_path or ""),
            "FUSE Model (*.fse);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return

        if not file_path.endswith(".fse"):
            file_path += ".fse"

        self.set_current_project_path(file_path)
        self.save_model()

    def export_sst_json(self):
        """
        Export the current FUSE model to SST's JSON configuration format.

        This does not replace the native .fse project save format. The .fse
        file remains the editable FUSE project file. This method writes a
        generated SST JSON configuration file for use with SST.
        """
        if not self.scene.component_items():
            QMessageBox.information(
                self,
                "Export SST JSON",
                "There are no components to export.",
            )
            return

        active = self.project_settings.active_plugin_settings()

        if active is None or active.plugin_id != "sst":
            QMessageBox.warning(
                self,
                "Export SST JSON",
                (
                    "The active project target is not SST.\n\n"
                    "Open Project Settings and select an SST target before "
                    "exporting to SST JSON."
                ),
            )
            return

        if not self.validate_model_before_save():
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export SST JSON",
            str(self.current_project_path.with_suffix(".sst.json"))
            if self.current_project_path
            else "",
            "SST JSON (*.json);;All Files (*)",
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".json"):
            file_path += ".json"

        try:
            from fuse.plugins.community.sst.export_json import export_sst_json

            export_sst_json(
                scene=self.scene,
                output_path=file_path,
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Export SST JSON Failed",
                str(error),
            )
            return

        self.statusBar().showMessage(
            f"Exported SST JSON to {file_path}",
            5000,
        )

    def open_model(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open FUSE Model",
            "",
            "FUSE Model (*.fse);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return

        try:
            project = load_project_file(file_path)
            self.project_settings = ProjectSettings.from_project_dict(project)
            load_project_into_scene(project, self.scene)
            self.properties_panel.set_validation_issues([])
            self.properties_panel.show_empty()
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        self.set_current_project_path(file_path)

        self.apply_project_settings_to_ui()
        self.update_model_outline()
        self.set_dirty(False)

        self.statusBar().showMessage(f"Opened {file_path}", 3000)

    def show_about(self):
        dialog = AboutDialog(self)
        dialog.exec()

    def show_links(self):
        if not self.scene.links:
            QMessageBox.information(self, "Links", "No links have been created yet.")
            return

        text = "\n".join(
            f"{link.name}: "
            f"{link.source_component_name}.{link.source_port} -> "
            f"{link.target_component_name}.{link.target_port} "
            f"latency={link.latency}"
            for link in self.scene.links
        )

        QMessageBox.information(self, "Links", text)

    def apply_validation_issues(self, issues):
        issues_by_node: dict[int, list[str]] = {}

        for issue in issues:
            if issue.node_id is not None:
                issues_by_node.setdefault(issue.node_id, []).append(issue.message)

        for node in self.scene.component_items():
            node.set_validation_warnings(issues_by_node.get(node.node_id, []))

        self.properties_panel.set_validation_issues(issues)

    def format_validation_message(self, issues) -> str:
        lines = ["The model has issues that must be fixed before saving:", ""]

        for issue in issues[:25]:
            lines.append(f"• {issue.object_name}: {issue.message}")

        if len(issues) > 25:
            lines.append("")
            lines.append(f"...and {len(issues) - 25} more issue(s).")

        lines.append("")
        lines.append("Components with missing required values are marked with a warning icon.")

        return "\n".join(lines)

    def validate_model_before_save(self) -> bool:
        issues = validate_model(self.scene)
        self.apply_validation_issues(issues)

        if not issues:
            return True

        first_component_issue = next(
            (issue for issue in issues if issue.node_id is not None),
            None,
        )

        if first_component_issue is not None:
            for node in self.scene.component_items():
                if node.node_id == first_component_issue.node_id:
                    self.scene.select_component(node)
                    self.model_view.centerOn(node)
                    break

        QMessageBox.warning(
            self,
            "Model Needs Attention",
            self.format_validation_message(issues),
        )

        return False


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(ORG_NAME)

    splash_timer = QElapsedTimer()
    splash_timer.start()

    splash = create_splash_screen()
    splash.set_message("Initializing FUSE...")
    splash.show_centered()
    app.processEvents()

    window = MainWindow()

    splash.set_message("Loading plugins and editor...")
    app.processEvents()

    minimum_splash_ms = int(os.environ.get("FUSE_SPLASH_MS", "8000"))
    remaining_ms = max(0, minimum_splash_ms - splash_timer.elapsed())

    def show_main_window():
        window.showMaximized()
        splash.finish(window)

        auto_close_ms = os.environ.get("FUSE_TEST_AUTOCLOSE_MS")
        if auto_close_ms:
            QTimer.singleShot(int(auto_close_ms), app.quit)

    QTimer.singleShot(remaining_ms, show_main_window)

    sys.exit(app.exec())