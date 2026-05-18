import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenuBar,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from component_pallette import ComponentPalette
from db_access import ensure_database_ready
from model_scene import ModelScene
from model_view import ModelView
from project_io import (
    build_project_dict,
    load_project_file,
    load_project_into_scene,
    save_project_file,
)
from properties_panel import PropertiesPanel
from validation import validate_model

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FUSE SST Model Builder")
        self.resize(1300, 800)

        self.current_project_path: Optional[Path] = None
        self.project_name = "Untitled SST Model"

        self.palette = ComponentPalette()
        self.scene = ModelScene()
        self.model_view = ModelView(self.scene)
        self.properties_panel = PropertiesPanel()
        self.scene.properties_panel = self.properties_panel

        self.setup_menu_bar()
        self.setup_layout()
        self.setup_properties_panel()
        self.setup_status_bar()

        ensure_database_ready()
        self.palette.load_components()

    def setup_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        tools_menu = menu_bar.addMenu("Tools")
        help_menu = menu_bar.addMenu("Help")

        new_action = QAction("New Model", self)
        open_action = QAction("Open...", self)
        save_action = QAction("Save", self)
        save_as_action = QAction("Save As...", self)
        exit_action = QAction("Exit", self)

        new_action.triggered.connect(self.new_model)
        open_action.triggered.connect(self.open_model)
        save_action.triggered.connect(self.save_model)
        save_as_action.triggered.connect(self.save_model_as)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(exit_action)

        refresh_action = QAction("Refresh Component List", self)
        refresh_action.triggered.connect(self.palette.load_components)
        tools_menu.addAction(refresh_action)

        show_links_action = QAction("Show Links", self)
        show_links_action.triggered.connect(self.show_links)
        tools_menu.addAction(show_links_action)

        reroute_all_action = QAction("Reroute All Links", self)
        reroute_all_action.triggered.connect(self.scene.reroute_all_links)
        tools_menu.addAction(reroute_all_action)

        about_action = QAction("About", self)
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
        splitter.addWidget(left_panel)
        splitter.addWidget(self.model_view)
        splitter.setSizes([320, 980])

        self.setCentralWidget(splitter)

    def setup_properties_panel(self):
        dock = QDockWidget("Properties", self)
        dock.setWidget(self.properties_panel)
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
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

    def setup_status_bar(self):
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.setStatusBar(status)

    def project_dict(self) -> dict:
        return build_project_dict(self.scene, self.model_view, self.project_name)

    def set_current_project_path(self, path: Optional[str | Path]) -> None:
        self.current_project_path = Path(path) if path else None

        if self.current_project_path is not None:
            self.project_name = self.current_project_path.stem
            self.setWindowTitle(f"FUSE SST Model Builder - {self.current_project_path.name}")
        else:
            self.project_name = "Untitled SST Model"
            self.setWindowTitle("FUSE SST Model Builder")

    def new_model(self):
        self.scene.clear_model()
        self.properties_panel.set_validation_issues([])
        self.properties_panel.show_empty()
        self.set_current_project_path(None)
        self.statusBar().showMessage("New model created", 3000)

    def save_model(self):
        if not self.validate_model_before_save():
            return

        if self.current_project_path is None:
            self.save_model_as()
            return

        project = self.project_dict()
        save_project_file(project, self.current_project_path)
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
            load_project_into_scene(project, self.scene)
            self.properties_panel.set_validation_issues([])
            self.properties_panel.show_empty()
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        self.set_current_project_path(file_path)
        self.statusBar().showMessage(f"Opened {file_path}", 3000)

    def show_about(self):
        QMessageBox.information(
            self,
            "About FUSE",
            "FUSE SST Model Builder\n\n"
            "Drag components from the left panel into the canvas.\n"
            "Click one port, then another port, to create an SST-style link.",
        )

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
    window = MainWindow()
    window.show()
    sys.exit(app.exec())