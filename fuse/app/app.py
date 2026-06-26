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
"""Main Qt application shell for the FUSE desktop editor.

This module owns the top-level application lifecycle: database initialization,
plugin discovery, framework target selection, model tab management, document
save/load/export actions, validation result presentation, and dock/widget
composition. Most simulator-specific behavior is delegated to plugin-facing
services or exporters so that the main window remains responsible for workflow
coordination rather than simulator semantics.

The central ``MainWindow`` class deliberately connects many UI subsystems
because it is the point where project state, Qt widgets, and user actions meet.
Lower-level modules such as ``ModelScene`` and ``ModelView`` implement canvas
behavior, while this module decides when those behaviors become application
commands.
"""
import copy
import json
import os
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QElapsedTimer, QPoint, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDockWidget,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QMenu,
    QMenuBar,
    QMessageBox,
    QStatusBar,
    QStyle,
    QTabWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fuse.app.about import AboutDialog
from fuse.app.composite_component_dialog import CompositeComponentDialog
from fuse.app.composite_component_manager_dialog import CompositeComponentManagerDialog
from fuse.app.project_settings_dialog import ProjectSettingsDialog
from fuse.app.splash import create_splash_screen
from fuse.core.app_info import APP_NAME, ORG_NAME
from fuse.core.model.project_settings import ProjectSettings
from fuse.plugins.community.sst.component_catalog import (
    sst_target_requires_runtime_verification,
    verify_project_sst_runtime,
)
from fuse.core.model.validation import validate_model, validate_model_for_export
from fuse.core.plugin_runtime.manager import get_plugin_by_id
from fuse.core.persistence.composite_components import (
    get_composite_component_definition,
    save_composite_component_definition,
)
from fuse.core.persistence.composite_component_files import (
    CompositeComponentFileError,
    import_composite_component_file,
    write_composite_component_file,
)
from fuse.core.persistence.db_access import ensure_database_ready, load_framework_targets
from fuse.core.persistence.project_io import (
    build_project_dict,
    load_project_file,
    load_project_into_scene,
    save_project_file,
)
from fuse.core.ui.component_palette import ComponentPalette
from fuse.core.ui.composite_builder import (
    build_composite_definition_from_selection,
    replace_selection_with_composite_instance,
    selection_boundary_report,
)
from fuse.core.ui.composite_instance_editor import (
    CompositeInstanceEditorWidget,
    CompositeTemplateEditorWidget,
)
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.ui.properties_panel import PropertiesPanel
from fuse.core.ui.selection_helpers import (
    can_create_composite_from_selection,
    request_composite_from_selection,
)

OUTLINE_ROLE_KIND = Qt.UserRole
OUTLINE_ROLE_NODE_ID = Qt.UserRole + 1
OUTLINE_ROLE_LINK_ID = Qt.UserRole + 2
OUTLINE_ROLE_ATTACHMENT_ID = Qt.UserRole + 3

VALIDATION_ROLE_ISSUE_INDEX = Qt.UserRole
VALIDATION_ROLE_SEVERITY = Qt.UserRole + 1
VALIDATION_ROLE_NODE_ID = Qt.UserRole + 2
VALIDATION_ROLE_LINK_ID = Qt.UserRole + 3
VALIDATION_ROLE_ATTACHMENT_ID = Qt.UserRole + 4

UNSAVED_CHOICE_SAVE = "save"
UNSAVED_CHOICE_DISCARD = "discard"
UNSAVED_CHOICE_CANCEL = "cancel"



def prefer_xcb_platform_for_window_manager_shadows() -> None:
    """Use X11/XWayland on Linux Wayland sessions unless the user opts out.

    Some PySide6/Qt Wayland client-side decorations are rendered without the
    compositor-provided outer window shadow even when other desktop apps have
    one. Running the normal native main window through xcb lets the desktop
    window manager decorate FUSE like the rest of the user's applications.

    Users can override this by setting QT_QPA_PLATFORM themselves, or disable
    the FUSE default with FUSE_PREFER_XCB_WINDOW_SHADOWS=0.
    """

    if sys.platform != "linux":
        return
    if os.environ.get("FUSE_PREFER_XCB_WINDOW_SHADOWS", "1").lower() in {"0", "false", "no"}:
        return
    if os.environ.get("QT_QPA_PLATFORM"):
        return
    if os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland":
        return

    os.environ["QT_QPA_PLATFORM"] = "xcb"


class FloatingDockTitleBar(QWidget):
    """Custom title bar used when a dock widget is floating.

    Qt's default floating dock title bar does not expose the exact controls and
    styling used by FUSE, so this lightweight widget provides explicit dock and
    close buttons while preserving drag-to-move behavior for floating panels.
    """
    def __init__(self, dock: QDockWidget, title: str):
        super().__init__(dock)
        self.dock = dock
        self.drag_start_global_position: QPoint | None = None
        self.drag_start_dock_position: QPoint | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 4, 2)
        layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("floatingDockTitleLabel")
        layout.addWidget(self.title_label, 1)

        self.dock_button = QToolButton(self)
        self.dock_button.setObjectName("floatingDockButton")
        self.dock_button.setAutoRaise(True)
        self.dock_button.setToolTip("Dock this panel")
        self.dock_button.setIcon(self.style().standardIcon(QStyle.SP_TitleBarNormalButton))
        self.dock_button.clicked.connect(self.dock_panel)
        layout.addWidget(self.dock_button)

        self.close_button = QToolButton(self)
        self.close_button.setObjectName("floatingDockCloseButton")
        self.close_button.setAutoRaise(True)
        self.close_button.setToolTip("Close this panel")
        self.close_button.setIcon(self.style().standardIcon(QStyle.SP_TitleBarCloseButton))
        self.close_button.clicked.connect(self.dock.close)
        layout.addWidget(self.close_button)

        self.setStyleSheet(
            """
            FloatingDockTitleBar {
                background: palette(window);
                border-bottom: 1px solid palette(mid);
            }
            QLabel#floatingDockTitleLabel {
                font-weight: 600;
            }
            QToolButton#floatingDockButton, QToolButton#floatingDockCloseButton {
                padding: 0px;
            }
            """
        )

    def dock_panel(self) -> None:
        self.dock.setFloating(False)

    def global_position_from_event(self, event) -> QPoint:
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def start_system_window_move(self) -> bool:
        window_handle = self.dock.windowHandle()
        if window_handle is None:
            return False

        try:
            return bool(window_handle.startSystemMove())
        except RuntimeError:
            return False

    def begin_manual_window_move(self, event) -> None:
        self.drag_start_global_position = self.global_position_from_event(event)
        self.drag_start_dock_position = self.dock.pos()

    def move_floating_dock_from_drag(self, global_position: QPoint) -> bool:
        if (
            not self.dock.isFloating()
            or self.drag_start_global_position is None
            or self.drag_start_dock_position is None
        ):
            return False

        delta = global_position - self.drag_start_global_position
        self.dock.move(self.drag_start_dock_position + delta)
        return True

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.dock.isFloating():
            self.begin_manual_window_move(event)
            if self.start_system_window_move():
                self.drag_start_global_position = None
                self.drag_start_dock_position = None
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            event.buttons() & Qt.LeftButton
            and self.move_floating_dock_from_drag(self.global_position_from_event(event))
        ):
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start_global_position = None
        self.drag_start_dock_position = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dock_panel()
            event.accept()
            return

        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    """Top-level window and command coordinator for the FUSE editor.

    ``MainWindow`` wires together the component palette, model canvas,
    properties panel, model outline, validation output, project settings, and
    export actions. It also owns tab lifecycles for normal model documents,
    composite instance editors, and composite template editors.

    The class intentionally keeps long-lived project state such as the active
    framework target, dirty flag, undo/redo snapshots, and current project path.
    Canvas items and scene-level interaction are delegated to ``ModelScene`` and
    ``ModelView``; simulator-specific validation/export work is delegated to the
    active plugin and exporter modules.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FUSE")
        self.resize(1300, 800)
        self.setObjectName("fuseMainWindow")


        self.current_project_path: Optional[Path] = None
        self.project_name = "Untitled FUSE Project"
        self.project_settings = ProjectSettings(
            project_name=self.project_name,
            active_plugin_id="sst",
        )
        self.active_plugin_id: str | None = None
        self.active_target_id: str | None = None
        self.is_dirty = False

        self._history_limit = 100
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._last_history_signature = ""
        self._saved_history_signature = ""
        self._restoring_history = False

        self.palette = ComponentPalette()
        self.scene = ModelScene()
        self.model_view = ModelView(self.scene)
        self.model_view.undo_callback = self.undo
        self.model_view.redo_callback = self.redo
        self.model_tabs: QTabWidget | None = None
        self.composite_editor_widgets: list[CompositeInstanceEditorWidget] = []
        self.composite_template_editor_widgets: list[CompositeTemplateEditorWidget] = []
        self.properties_panel = PropertiesPanel()
        self.model_outline = QTreeWidget()
        self.model_outline.setHeaderHidden(True)
        self.model_outline.setContextMenuPolicy(Qt.CustomContextMenu)
        self.model_outline.customContextMenuRequested.connect(
            self.show_model_outline_context_menu
        )
        self.model_outline.itemClicked.connect(self.on_model_outline_item_clicked)

        self.component_palette_panel: QWidget | None = None
        self.component_palette_dock: QDockWidget | None = None
        self.properties_dock: QDockWidget | None = None
        self.model_outline_dock: QDockWidget | None = None
        self.validation_results_panel = QWidget()
        validation_layout = QVBoxLayout(self.validation_results_panel)
        validation_layout.setContentsMargins(6, 6, 6, 6)

        validation_toolbar = QHBoxLayout()
        validation_toolbar.addWidget(QLabel("Show:"))
        self.validation_filter = QComboBox()
        self.validation_filter.addItems(["All", "Errors", "Warnings", "Info"])
        self.validation_filter.currentTextChanged.connect(self.refresh_validation_results_view)
        validation_toolbar.addWidget(self.validation_filter)
        validation_toolbar.addStretch(1)

        self.validation_results = QTreeWidget()
        self.validation_results.setHeaderLabels(["Severity", "Scope", "Object", "Message", "Suggested Fix"])
        self.validation_results.setRootIsDecorated(False)
        self.validation_results.setAlternatingRowColors(True)
        self.validation_results.itemDoubleClicked.connect(self.on_validation_result_activated)

        validation_layout.addLayout(validation_toolbar)
        validation_layout.addWidget(self.validation_results)
        self.validation_results_dock: QDockWidget | None = None
        self._last_validation_issues = []
        self._last_validation_title = ""

        self.scene.properties_panel = self.properties_panel
        self.scene.model_changed_callback = self.on_model_changed
        self.scene.component_added_callback = self.on_component_added
        self.scene.component_used_callback = self.on_component_used
        self.scene.component_favorite_requested_callback = self.on_component_favorite_requested
        self.scene.selection_changed_callback = self.on_scene_selection_changed
        self.scene.composite_creation_requested_callback = self.on_create_composite_from_selection_requested
        self.scene.composite_instance_edit_requested_callback = self.edit_composite_instance
        self.properties_panel.property_changed_callback = self.on_property_changed
        self.palette.preferences_changed_callback = self.on_component_palette_preferences_changed
        self.palette.edit_component_requested_callback = self.open_composite_template_from_palette_component

        self.setup_menu_bar()
        self.setup_layout()
        self.setup_docks()
        self.setup_status_bar()

        ensure_database_ready()
        self.load_framework_targets()
        self.reset_undo_history(mark_clean=True)

    def on_component_favorite_requested(self, component):
        self.palette.add_to_frequently_used(component)

    def update_create_composite_action_state(self) -> None:
        if hasattr(self, "create_composite_action"):
            self.create_composite_action.setEnabled(
                can_create_composite_from_selection(self.active_model_scene())
            )

    def request_create_composite_from_selection(self) -> None:
        request_composite_from_selection(
            self.active_model_scene(),
            self.on_create_composite_from_selection_requested,
        )

    def on_create_composite_from_selection_requested(self, components, links, attachments):
        self.last_composite_creation_request = {
            "components": list(components),
            "links": list(links),
            "attachments": list(attachments),
        }

        boundary = selection_boundary_report(self.scene, components, links, attachments)
        if boundary.has_boundary_items:
            self.statusBar().showMessage(
                "Cannot create a composite while selected components still have "
                "links or subcomponent attachments to unselected components.",
                7000,
            )
            return

        dialog = CompositeComponentDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return

        self.create_composite_from_selection(
            name=dialog.composite_name(),
            icon_path=dialog.icon_path(),
            description=dialog.composite_description(),
            components=components,
            links=links,
            attachments=attachments,
        )

    def create_composite_from_selection(
        self,
        name: str,
        icon_path: str,
        description: str,
        components,
        links,
        attachments,
    ):
        definition = build_composite_definition_from_selection(
            name=name,
            icon_path=icon_path,
            components=list(components),
            internal_connections=list(links),
            internal_attachments=list(attachments),
            description=description,
        )
        saved = save_composite_component_definition(definition)
        composite_node = replace_selection_with_composite_instance(
            self.scene,
            saved,
            list(components),
            list(links),
            list(attachments),
        )

        self.load_framework_targets()
        self.update_model_outline()
        self.update_create_composite_action_state()
        self.mark_dirty()
        self.statusBar().showMessage(
            f"Created composite component '{saved.name}' from selection.",
            5000,
        )
        return composite_node

    def selected_composite_node(self):
        for node in self.scene.component_items():
            if not node.isSelected():
                continue
            if int(getattr(node.component, "is_composite", 0) or 0):
                return node
        return None

    def composite_export_default_path(self, definition) -> str:
        safe_name = "".join(
            char if char.isalnum() or char in ("-", "_") else "_"
            for char in definition.name.strip()
        ).strip("_")
        if not safe_name:
            safe_name = "composite_component"
        return f"{safe_name}.fcc"

    def export_selected_composite_component(self) -> None:
        node = self.selected_composite_node()
        if node is None:
            QMessageBox.information(
                self,
                "Export Composite Component",
                "Select a composite component instance before exporting.",
            )
            return

        composite_id = getattr(node.component, "composite_id", "") or ""
        definition = get_composite_component_definition(composite_id)
        if definition is None:
            QMessageBox.warning(
                self,
                "Export Composite Component",
                "The selected composite component template could not be found.",
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Composite Component",
            self.composite_export_default_path(definition),
            "FUSE Composite Component (*.fcc);;JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            written_path = write_composite_component_file(definition, path)
        except CompositeComponentFileError as exc:
            QMessageBox.warning(self, "Export Composite Component", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(
                self,
                "Export Composite Component",
                f"Unable to write composite component file: {exc}",
            )
            return

        self.statusBar().showMessage(
            f"Exported composite component '{definition.name}' to {written_path}.",
            5000,
        )

    def import_composite_component(self) -> None:
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

        self.load_framework_targets()
        self.statusBar().showMessage(
            f"Imported composite component '{definition.name}'.",
            5000,
        )


    def show_composite_component_manager(self) -> None:
        dialog = CompositeComponentManagerDialog(self, edit_requested_callback=self.open_composite_definition_tab)
        dialog.exec()
        if dialog.changed:
            self.load_framework_targets()
            self.statusBar().showMessage("Composite component catalog refreshed.", 4000)

    def edit_composite_instance(self, node) -> None:
        self.open_composite_instance_tab(node)

    def setup_menu_bar(self):
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        file_menu = menu_bar.addMenu("File")
        edit_menu = menu_bar.addMenu("Edit")
        view_menu = menu_bar.addMenu("View")
        self.view_menu = view_menu
        tools_menu = menu_bar.addMenu("Tools")
        help_menu = menu_bar.addMenu("Help")

        new_action = QAction("New Project...", self)
        open_action = QAction("Open Project...", self)
        project_settings_action = QAction("Project Settings...", self)
        validate_model_action = QAction("Validate Model", self)
        validate_export_action = QAction("Validate for Export", self)
        save_action = QAction("Save", self)
        save_as_action = QAction("Save As...", self)
        export_sst_json_action = QAction("SST JSON...", self)
        export_gem5_python_action = QAction("gem5 Python...", self)
        self.import_composite_action = QAction("Import Composite Component...", self)
        self.export_composite_action = QAction("Selected Composite Component...", self)
        exit_action = QAction("Exit", self)

        new_action.triggered.connect(self.new_project)
        open_action.triggered.connect(self.open_model)
        project_settings_action.triggered.connect(self.show_project_settings)
        validate_model_action.triggered.connect(self.validate_current_model)
        validate_export_action.triggered.connect(self.validate_current_model_for_export)
        save_action.triggered.connect(self.save_model)
        save_as_action.triggered.connect(self.save_model_as)
        export_sst_json_action.triggered.connect(self.export_sst_json)
        export_gem5_python_action.triggered.connect(self.export_gem5_python)
        self.import_composite_action.triggered.connect(self.import_composite_component)
        self.export_composite_action.triggered.connect(self.export_selected_composite_component)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(new_action)
        file_menu.addAction(open_action)
        file_menu.addAction(project_settings_action)
        file_menu.addSeparator()
        file_menu.addAction(validate_model_action)
        file_menu.addAction(validate_export_action)
        file_menu.addSeparator()
        file_menu.addAction(save_action)
        file_menu.addAction(save_as_action)

        import_menu = file_menu.addMenu("Import")
        import_menu.addAction(self.import_composite_action)

        export_menu = file_menu.addMenu("Export")
        export_menu.addAction(export_sst_json_action)
        export_menu.addAction(export_gem5_python_action)
        export_menu.addSeparator()
        export_menu.addAction(self.export_composite_action)

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

        self.undo_action = QAction("Undo", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)

        self.redo_action = QAction("Redo", self)
        self.redo_action.setShortcut("Ctrl+Shift+Z")
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)

        self.copy_action = QAction("Copy", self)
        self.copy_action.setShortcut("Ctrl+C")
        self.copy_action.triggered.connect(lambda: self.active_model_view().copy_selection())

        self.paste_action = QAction("Paste", self)
        self.paste_action.setShortcut("Ctrl+V")
        self.paste_action.triggered.connect(lambda: self.active_model_view().paste_clipboard())

        self.group_action = QAction("Group", self)
        self.group_action.setShortcut("Ctrl+G")
        self.group_action.triggered.connect(lambda: self.active_model_view().group_selection())

        self.ungroup_action = QAction("Ungroup", self)
        self.ungroup_action.setShortcut("Ctrl+Shift+G")
        self.ungroup_action.triggered.connect(lambda: self.active_model_view().ungroup_selection())

        self.create_composite_action = QAction("Create Composite Component from Selection", self)
        self.create_composite_action.triggered.connect(self.request_create_composite_from_selection)
        self.create_composite_action.setEnabled(False)

        self.manage_composite_components_action = QAction("Manage Composite Components...", self)
        self.manage_composite_components_action.triggered.connect(self.show_composite_component_manager)

        self.save_composite_template_action = QAction("Save Template Changes", self)
        self.save_composite_template_action.triggered.connect(self.save_active_composite_template_changes)
        self.save_composite_template_action.setEnabled(False)

        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.copy_action)
        edit_menu.addAction(self.paste_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.group_action)
        edit_menu.addAction(self.ungroup_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.create_composite_action)
        edit_menu.addAction(self.manage_composite_components_action)
        edit_menu.addAction(self.save_composite_template_action)
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.setShortcut("Ctrl++")
        zoom_in_action.triggered.connect(self.model_view.zoom_in)
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.setShortcut("Ctrl+-")
        zoom_out_action.triggered.connect(self.model_view.zoom_out)
        view_menu.addAction(zoom_in_action)
        view_menu.addAction(zoom_out_action)

    def active_model_editor_widget(self):
        if self.model_tabs is None:
            return None
        widget = self.model_tabs.currentWidget()
        if isinstance(widget, (CompositeInstanceEditorWidget, CompositeTemplateEditorWidget)):
            return widget
        return None

    def active_composite_template_editor_widget(self):
        if self.model_tabs is None:
            return None
        widget = self.model_tabs.currentWidget()
        if isinstance(widget, CompositeTemplateEditorWidget):
            return widget
        return None

    def active_model_scene(self):
        editor = self.active_model_editor_widget()
        if editor is not None:
            return editor.editor_scene
        return self.scene

    def active_model_view(self):
        editor = self.active_model_editor_widget()
        if editor is not None:
            return editor.editor_view
        return self.model_view

    def model_tab_scenes(self):
        scenes = [self.scene]
        if self.model_tabs is None:
            return scenes

        for index in range(1, self.model_tabs.count()):
            widget = self.model_tabs.widget(index)
            if isinstance(widget, (CompositeInstanceEditorWidget, CompositeTemplateEditorWidget)):
                scenes.append(widget.editor_scene)
        return scenes

    def bind_global_panels_to_active_model_tab(self) -> None:
        active_scene = self.active_model_scene()
        for scene in self.model_tab_scenes():
            scene.properties_panel = None
            scene.selection_changed_callback = self.on_scene_selection_changed

        active_scene.properties_panel = self.properties_panel
        self.sync_properties_panel_to_active_scene()

    def sync_properties_panel_to_active_scene(self) -> None:
        scene = self.active_model_scene()

        selected_component = getattr(scene, "selected_component", None)
        if selected_component is not None and selected_component.scene() is scene:
            self.properties_panel.show_component(selected_component)
            return

        selected_connection = getattr(scene, "selected_connection", None)
        if selected_connection is not None and selected_connection.scene() is scene:
            self.properties_panel.show_link(selected_connection)
            return

        selected_attachment = getattr(scene, "selected_subcomp_attachment", None)
        if selected_attachment is not None and selected_attachment.scene() is scene:
            self.properties_panel.show_subcomp_attachment(selected_attachment)
            return

        self.properties_panel.show_empty()

    def on_model_tab_changed(self, index: int) -> None:
        self.bind_global_panels_to_active_model_tab()
        self.update_model_outline()
        self.update_create_composite_action_state()
        self.update_save_composite_template_action_state()

    def project_model_tab_title(self) -> str:
        name = (self.project_name or "Untitled FUSE Project").strip()
        return name or "Untitled FUSE Project"

    def refresh_project_model_tab_title(self) -> None:
        if self.model_tabs is not None and self.model_tabs.count() > 0:
            self.model_tabs.setTabText(0, self.project_model_tab_title())
            self.model_tabs.setTabToolTip(0, "Global project model")

    def update_save_composite_template_action_state(self) -> None:
        if not hasattr(self, "save_composite_template_action"):
            return
        editor = self.active_composite_template_editor_widget()
        self.save_composite_template_action.setEnabled(
            editor is not None and bool(getattr(editor, "template_dirty", False))
        )

    def open_composite_template_from_palette_component(self, component) -> None:
        if not bool(int(getattr(component, "is_composite", 0) or 0)):
            return
        composite_id = getattr(component, "composite_id", "") or getattr(component, "component_id", "") or ""
        definition = get_composite_component_definition(str(composite_id))
        if definition is not None:
            self.open_composite_definition_tab(definition)

    def find_composite_template_tab_index(self, composite_id: str) -> int:
        if self.model_tabs is None:
            return -1
        for index in range(1, self.model_tabs.count()):
            widget = self.model_tabs.widget(index)
            if not isinstance(widget, CompositeTemplateEditorWidget):
                continue
            if widget.definition.composite_id == composite_id:
                return index
        return -1

    def open_composite_definition_tab(self, definition) -> None:
        existing_index = self.find_composite_template_tab_index(definition.composite_id)
        if existing_index >= 0:
            self.model_tabs.setCurrentIndex(existing_index)
            return

        label = f"{definition.name} [Template]"
        editor = CompositeTemplateEditorWidget(
            definition,
            parent=self,
            nested_edit_requested_callback=self.open_nested_composite_instance_tab,
            template_changed_callback=self.on_composite_template_editor_changed,
            template_save_requested_callback=self.save_composite_template_changes_for_editor,
        )
        editor.editor_scene.selection_changed_callback = self.on_scene_selection_changed
        editor.composite_tab_path = label
        editor.parent_composite_editor = None
        self.composite_template_editor_widgets.append(editor)

        index = self.model_tabs.addTab(editor, label)
        self.model_tabs.setTabToolTip(index, f"Global template: {definition.name}")
        self.model_tabs.setCurrentIndex(index)
        self.statusBar().showMessage(f"Opened composite template tab '{definition.name}'.", 3000)

    def on_composite_template_editor_changed(self, editor) -> None:
        self.update_composite_template_tab_label(editor)
        self.update_save_composite_template_action_state()
        self.update_model_outline()

    def update_composite_template_tab_label(self, editor) -> None:
        if self.model_tabs is None:
            return
        index = self.model_tabs.indexOf(editor)
        if index < 0:
            return
        dirty_prefix = "*" if bool(getattr(editor, "template_dirty", False)) else ""
        label = f"{dirty_prefix}{editor.definition.name} [Template]"
        self.model_tabs.setTabText(index, label)
        self.model_tabs.setTabToolTip(index, f"Global template: {editor.definition.name}")

    def save_active_composite_template_changes(self) -> bool:
        editor = self.active_composite_template_editor_widget()
        if editor is None:
            return False
        return self.save_composite_template_changes_for_editor(editor)

    def save_composite_template_changes_for_editor(self, editor) -> bool:
        if editor is None:
            return False

        affected_instances = [
            node
            for node in self.scene.component_items()
            if bool(int(getattr(node.component, "is_composite", 0) or 0))
            and getattr(node.component, "composite_id", "") == editor.definition.composite_id
        ]
        apply_to_instances = False
        if affected_instances:
            response = QMessageBox.question(
                self,
                "Save Composite Template Changes",
                (
                    "This project contains existing instances of this composite component.\n\n"
                    "Apply the updated template to those instances in the current project? "
                    "This may replace instance-local composite edits."
                ),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.No,
            )
            if response == QMessageBox.Cancel:
                return False
            apply_to_instances = response == QMessageBox.Yes

        saved = editor.save_template_changes()
        if apply_to_instances:
            for node in affected_instances:
                node.composite_instance_model = copy.deepcopy(saved.mini_model)
                node.composite_port_mappings = copy.deepcopy(saved.port_mappings)
                node.sync_composite_ports_from_mappings()
            self.mark_dirty()

        self.load_framework_targets()
        self.update_model_outline()
        self.statusBar().showMessage(
            f"Saved composite template changes for '{saved.name}'.",
            5000,
        )
        self.update_composite_template_tab_label(editor)
        self.update_save_composite_template_action_state()
        return True

    def composite_tab_label(self, node, parent_editor=None) -> str:
        node_name = getattr(node, "instance_name", "Composite") or "Composite"
        if parent_editor is None:
            return str(node_name)

        parent_label = getattr(parent_editor, "composite_tab_path", "") or ""
        if not parent_label:
            return str(node_name)
        return f"{parent_label}:{node_name}"

    def find_composite_editor_tab_index(self, node, parent_editor=None) -> int:
        if self.model_tabs is None:
            return -1

        for index in range(1, self.model_tabs.count()):
            widget = self.model_tabs.widget(index)
            if not isinstance(widget, CompositeInstanceEditorWidget):
                continue
            if widget.node is not node:
                continue
            if getattr(widget, "parent_composite_editor", None) is parent_editor:
                return index
        return -1

    def open_composite_instance_tab(self, node, parent_editor=None) -> None:
        component_is_composite = bool(int(getattr(node.component, "is_composite", 0) or 0))
        if not component_is_composite:
            return

        existing_index = self.find_composite_editor_tab_index(node, parent_editor)
        if existing_index >= 0:
            self.model_tabs.setCurrentIndex(existing_index)
            return

        label = self.composite_tab_label(node, parent_editor)
        editor = CompositeInstanceEditorWidget(
            node,
            parent=self,
            nested_edit_requested_callback=self.open_nested_composite_instance_tab,
            instance_changed_callback=self.on_composite_editor_changed,
        )
        editor.editor_scene.selection_changed_callback = self.on_scene_selection_changed
        editor.composite_tab_path = label
        editor.parent_composite_editor = parent_editor
        self.composite_editor_widgets.append(editor)

        index = self.model_tabs.addTab(editor, label)
        self.model_tabs.setTabToolTip(index, label.replace(":", " > "))
        self.model_tabs.setCurrentIndex(index)
        self.statusBar().showMessage(f"Opened composite instance tab '{label}'.", 3000)

    def open_nested_composite_instance_tab(self, node, parent_editor) -> None:
        self.open_composite_instance_tab(node, parent_editor=parent_editor)

    def on_composite_editor_changed(self, editor) -> None:
        self.propagate_composite_editor_change_to_ancestors(editor)
        node = editor.node
        if self.properties_panel.current_node is node:
            self.properties_panel.show_component(node)
        self.update_model_outline()
        self.mark_dirty()

    def propagate_composite_editor_change_to_ancestors(self, editor) -> None:
        parent_editor = getattr(editor, "parent_composite_editor", None)
        while parent_editor is not None:
            if hasattr(parent_editor, "apply_current_edit_to_node"):
                parent_editor.apply_current_edit_to_node()
            parent_editor = getattr(parent_editor, "parent_composite_editor", None)

    def close_model_tab(self, index: int) -> None:
        if self.model_tabs is None or index <= 0:
            return

        widget = self.model_tabs.widget(index)
        if isinstance(widget, CompositeInstanceEditorWidget):
            self.close_child_composite_tabs(widget)
            widget.apply_current_edit_to_node()
            self.propagate_composite_editor_change_to_ancestors(widget)
            if widget in self.composite_editor_widgets:
                self.composite_editor_widgets.remove(widget)
        elif isinstance(widget, CompositeTemplateEditorWidget):
            if not self.confirm_close_composite_template_editor(widget):
                return
            self.close_child_composite_tabs(widget)
            if widget in self.composite_template_editor_widgets:
                self.composite_template_editor_widgets.remove(widget)

        self.model_tabs.removeTab(index)
        widget.deleteLater()
        self.bind_global_panels_to_active_model_tab()
        self.update_model_outline()
        self.update_create_composite_action_state()
        self.update_save_composite_template_action_state()

    def confirm_close_composite_template_editor(self, editor) -> bool:
        if not bool(getattr(editor, "template_dirty", False)):
            return True

        response = QMessageBox.question(
            self,
            "Unsaved Composite Template Changes",
            (
                f"Save changes to composite template '{editor.definition.name}' before closing this tab?"
            ),
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if response == QMessageBox.Cancel:
            return False
        if response == QMessageBox.Save:
            return self.save_composite_template_changes_for_editor(editor)
        return True

    def close_child_composite_tabs(self, parent_editor) -> None:
        if self.model_tabs is None:
            return

        index = self.model_tabs.count() - 1
        while index > 0:
            widget = self.model_tabs.widget(index)
            if (
                isinstance(widget, (CompositeInstanceEditorWidget, CompositeTemplateEditorWidget))
                and self.composite_editor_is_descendant(widget, parent_editor)
            ):
                widget.apply_current_edit_to_node()
                if widget in self.composite_editor_widgets:
                    self.composite_editor_widgets.remove(widget)
                self.model_tabs.removeTab(index)
                widget.deleteLater()
                self.bind_global_panels_to_active_model_tab()
            index -= 1

    def composite_editor_is_descendant(self, editor, ancestor) -> bool:
        parent_editor = getattr(editor, "parent_composite_editor", None)
        while parent_editor is not None:
            if parent_editor is ancestor:
                return True
            parent_editor = getattr(parent_editor, "parent_composite_editor", None)
        return False

    def close_all_composite_model_tabs(self) -> None:
        if self.model_tabs is None:
            return

        index = self.model_tabs.count() - 1
        while index > 0:
            self.close_model_tab(index)
            index -= 1

    def setup_layout(self):
        self.component_palette_panel = QWidget()
        palette_layout = QVBoxLayout(self.component_palette_panel)
        palette_layout.setContentsMargins(8, 8, 8, 8)
        palette_layout.addWidget(self.palette)

        self.model_tabs = QTabWidget(self)
        self.model_tabs.setObjectName("centralModelTabs")
        self.model_tabs.setDocumentMode(True)
        self.model_tabs.setTabsClosable(True)
        self.model_tabs.setStyleSheet(
            """
            QTabWidget#centralModelTabs::pane {
                background: palette(base);
                border: 1px solid #9ca3af;
                border-radius: 4px;
            }
            QTabBar::tab {
                padding: 6px 10px;
            }
            """
        )


        self.model_tabs.tabCloseRequested.connect(self.close_model_tab)
        self.model_tabs.currentChanged.connect(self.on_model_tab_changed)
        self.model_tabs.addTab(self.model_view, self.project_model_tab_title())
        self.setCentralWidget(self.model_tabs)
        self.bind_global_panels_to_active_model_tab()

    def make_dock(self, title: str, widget: QWidget, object_name: str = "") -> QDockWidget:
        dock = QDockWidget(title, self)
        if object_name:
            dock.setObjectName(object_name)
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
        dock.topLevelChanged.connect(
            lambda floating, current_dock=dock, current_title=title: self.on_dock_top_level_changed(
                current_dock,
                current_title,
                floating,
            )
        )
        return dock

    def on_dock_top_level_changed(
        self,
        dock: QDockWidget,
        title: str,
        floating: bool,
    ) -> None:
        if floating:
            dock.setTitleBarWidget(FloatingDockTitleBar(dock, title))
            return

        dock.setTitleBarWidget(None)

    def setup_docks(self):
        """
        Create the default dock layout.

        The right dock column is split vertically:
        - Properties: about 60% of the column height
        - Model Outline: about 40% of the column height

        Users can still resize, move, float, or close these docks.
        """
        self.component_palette_dock = self.make_dock(
            "Available Components",
            self.component_palette_panel,
            "availableComponentsDock",
        )
        self.properties_dock = self.make_dock("Properties", self.properties_panel, "propertiesDock")
        self.properties_panel.set_title_changed_callback(
            self.properties_dock.setWindowTitle
        )
        self.model_outline_dock = self.make_dock("Model Outline", self.model_outline, "modelOutlineDock")
        self.validation_results_dock = self.make_dock(
            "Validation Results",
            self.validation_results_panel,
            "validationResultsDock",
        )

        self.addDockWidget(Qt.LeftDockWidgetArea, self.component_palette_dock)
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

        self.addDockWidget(Qt.BottomDockWidgetArea, self.validation_results_dock)
        self.validation_results_dock.hide()

        # Give the dock columns reasonable initial widths.
        self.resizeDocks(
            [self.component_palette_dock, self.properties_dock],
            [340, 360],
            Qt.Horizontal,
        )

        self.add_dock_view_actions()

    def add_dock_view_actions(self) -> None:
        self.view_menu.addSeparator()
        self.view_menu.addAction(self.component_palette_dock.toggleViewAction())
        self.view_menu.addAction(self.properties_dock.toggleViewAction())
        self.view_menu.addAction(self.model_outline_dock.toggleViewAction())
        self.view_menu.addAction(self.validation_results_dock.toggleViewAction())

    def setup_status_bar(self):
        status = QStatusBar(self)
        status.showMessage("Ready")
        self.unsaved_indicator = QLabel("")
        self.unsaved_indicator.setToolTip("The current FUSE model has unsaved changes.")
        status.addPermanentWidget(self.unsaved_indicator)
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
        self.palette.set_project_preferences(
            grouping_mode=self.project_settings.preferred_component_grouping_mode,
            sorting_mode=self.project_settings.preferred_component_sorting_mode,
            auto_expand_all=self.project_settings.auto_expand_all_component_tree,
            catalog_expanded=self.project_settings.component_catalog_expanded,
        )

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
        self.refresh_project_model_tab_title()
        self.apply_project_settings_to_ui()
        self.statusBar().showMessage("Project settings updated", 3000)
        self.mark_dirty()

    def on_component_added(self, node):
        self.update_model_outline()

    def on_component_palette_preferences_changed(self, preferences: dict) -> None:
        self.project_settings.preferred_component_grouping_mode = str(
            preferences.get("preferred_component_grouping_mode", "Element")
        )
        self.project_settings.preferred_component_sorting_mode = str(
            preferences.get("preferred_component_sorting_mode", "Alphabetical")
        )
        self.project_settings.auto_expand_all_component_tree = bool(
            preferences.get("auto_expand_all_component_tree", False)
        )
        self.project_settings.component_catalog_expanded = bool(
            preferences.get("component_catalog_expanded", False)
        )
        self.mark_dirty()

    def on_scene_selection_changed(self, node):
        self.update_create_composite_action_state()

        if node is None:
            self.palette.clear_compatibility_context()
        else:
            self.palette.set_compatibility_context(node)

    def on_property_changed(self):
        self.update_model_outline()
        self.mark_dirty()

    def update_model_outline(self):
        self.model_outline.clear()
        scene = self.active_model_scene()

        attachments_by_parent, attached_child_ids = self.subcomponent_attachment_maps(scene)
        nodes_by_id = self.node_by_id(scene)

        component_groups: dict[str, list] = {}

        for node in scene.component_items():
            # Attached subcomponents are shown underneath their parent component
            # through subcomp_attachments, not as independent top-level outline rows.
            if node.node_id in attached_child_ids:
                continue

            group_name = self.model_outline_group_for_node(node)
            component_groups.setdefault(group_name, []).append(node)

        for group_name in sorted(component_groups, key=str.lower):
            group_item = QTreeWidgetItem([group_name])
            group_item.setData(0, OUTLINE_ROLE_KIND, "group")
            group_item.setFlags(group_item.flags() & ~Qt.ItemIsSelectable)
            self.model_outline.addTopLevelItem(group_item)

            for node in sorted(
                    component_groups[group_name],
                    key=lambda item: item.instance_name.lower(),
            ):
                self.add_outline_node_item(
                    group_item,
                    node,
                    attachments_by_parent,
                    nodes_by_id,
                )

        links_item = QTreeWidgetItem(["Links"])
        links_item.setData(0, OUTLINE_ROLE_KIND, "group")
        links_item.setFlags(links_item.flags() & ~Qt.ItemIsSelectable)
        self.model_outline.addTopLevelItem(links_item)

        for link in sorted(scene.links, key=lambda item: item.name.lower()):
            link_item = QTreeWidgetItem([link.name])
            link_item.setData(0, OUTLINE_ROLE_KIND, "link")
            link_item.setData(0, OUTLINE_ROLE_LINK_ID, link.link_id)
            link_item.setToolTip(
                0,
                (
                    f"{link.source_component_name}.{link.source_port} -> "
                    f"{link.target_component_name}.{link.target_port}"
                ),
            )
            links_item.addChild(link_item)

        self.model_outline.expandAll()

    def subcomponent_attachment_maps(self, scene=None):
        current_scene = scene or self.active_model_scene()
        attachments_by_parent: dict[int, list] = {}
        attached_child_ids: set[int] = set()

        for attachment in getattr(current_scene, "subcomp_attachments", []):
            attachments_by_parent.setdefault(
                attachment.parent_node_id,
                [],
            ).append(attachment)
            attached_child_ids.add(attachment.child_node_id)

        return attachments_by_parent, attached_child_ids

    def node_by_id(self, scene=None) -> dict[int, object]:
        current_scene = scene or self.active_model_scene()
        return {
            node.node_id: node
            for node in current_scene.component_items()
        }

    def outline_label_for_node(self, node) -> str:
        plugin_id = (getattr(node.component, "plugin_id", "") or "").strip()

        if plugin_id:
            return f"{node.instance_name} ({plugin_id.upper() if plugin_id == 'sst' else plugin_id.capitalize()})"

        return node.instance_name

    def add_outline_node_item(
            self,
            parent_item: QTreeWidgetItem,
            node,
            attachments_by_parent: dict[int, list],
            nodes_by_id: dict[int, object],
    ):
        node_item = QTreeWidgetItem([self.outline_label_for_node(node)])
        node_item.setData(0, OUTLINE_ROLE_KIND, "component")
        node_item.setData(0, OUTLINE_ROLE_NODE_ID, node.node_id)
        node_item.setToolTip(
            0,
            node.component.description or node.component.display_name,
        )

        if int(getattr(node.component, "is_subcomp", 0) or 0):
            font = node_item.font(0)
            font.setItalic(True)
            node_item.setFont(0, font)

        parent_item.addChild(node_item)

        child_attachments = attachments_by_parent.get(node.node_id, [])

        for attachment in sorted(
                child_attachments,
                key=lambda item: (
                        item.slot_name.lower(),
                        item.child_component_name.lower(),
                ),
        ):
            child_node = nodes_by_id.get(attachment.child_node_id)
            if child_node is None:
                continue

            slot_item = QTreeWidgetItem(
                [f"{attachment.slot_name}: {self.outline_label_for_node(child_node)}"]
            )
            slot_item.setData(0, OUTLINE_ROLE_KIND, "subcomp_attachment")
            slot_item.setData(0, OUTLINE_ROLE_ATTACHMENT_ID, attachment.attachment_id)
            slot_item.setToolTip(
                0,
                (
                    f"SubComponent slot: {attachment.slot_name}\n"
                    f"Required interface: {attachment.required_interface or '(unknown)'}"
                ),
            )
            node_item.addChild(slot_item)

            self.add_outline_node_item(
                slot_item,
                child_node,
                attachments_by_parent,
                nodes_by_id,
            )

    def model_outline_group_for_node(self, node) -> str:
        component = node.component

        if int(getattr(component, "is_composite", 0) or 0):
            return "Composite Components"

        text = " ".join(
            [
                getattr(component, "category", "") or "",
                getattr(component, "functionality", "") or "",
                getattr(component, "description", "") or "",
                getattr(component, "element", "") or "",
                getattr(component, "name", "") or "",
                getattr(component, "iface", "") or "",
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

        if int(getattr(component, "is_subcomp", 0) or 0):
            return "SubComponents"

        return "Other"

    def history_snapshot(self) -> dict:
        """Return a stable project snapshot suitable for undo/redo history."""
        snapshot = copy.deepcopy(self.project_dict())
        snapshot.setdefault("project", {})["updatedAt"] = ""
        return snapshot

    def history_signature(self, snapshot: dict | None = None) -> str:
        if snapshot is None:
            snapshot = self.history_snapshot()

        comparable = copy.deepcopy(snapshot)
        # Editor viewport state is persisted in .fse files and restored from
        # history snapshots, but it should not make an otherwise identical model
        # look dirty. QGraphicsView also normalizes some viewport coordinates
        # through integer scroll bars, so excluding this section prevents harmless
        # restore drift from breaking undo/redo cleanliness checks.
        comparable.pop("editor", None)
        return json.dumps(comparable, sort_keys=True, separators=(",", ":"))

    def reset_undo_history(self, mark_clean: bool = True):
        snapshot = self.history_snapshot()
        signature = self.history_signature(snapshot)
        self._undo_stack = [snapshot]
        self._redo_stack = []
        self._last_history_signature = signature
        if mark_clean:
            self._saved_history_signature = signature
        self.update_undo_redo_actions()
        if mark_clean:
            self.set_dirty(False)

    def update_undo_redo_actions(self):
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(len(self._undo_stack) > 1)
        if hasattr(self, "redo_action"):
            self.redo_action.setEnabled(bool(self._redo_stack))

    def record_history_snapshot(self):
        if self._restoring_history:
            return

        snapshot = self.history_snapshot()
        signature = self.history_signature(snapshot)

        if signature == self._last_history_signature:
            self.update_undo_redo_actions()
            return

        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._history_limit + 1:
            self._undo_stack = self._undo_stack[-(self._history_limit + 1):]

        self._redo_stack.clear()
        self._last_history_signature = signature
        self.update_undo_redo_actions()

    def restore_history_snapshot(self, snapshot: dict):
        self._restoring_history = True
        try:
            self.project_settings = ProjectSettings.from_project_dict(snapshot)
            self.project_name = snapshot.get("project", {}).get("name", self.project_name)
            self.close_all_composite_model_tabs()
            load_project_into_scene(snapshot, self.scene)
            self.properties_panel.set_validation_issues([])
            self.properties_panel.show_empty()
            self.apply_project_settings_to_ui()
            self.model_view.apply_editor_state(snapshot.get("editor", {}))
            self.refresh_project_model_tab_title()
            self.update_model_outline()
            self._last_history_signature = self.history_signature(snapshot)
        finally:
            self._restoring_history = False

        self.set_dirty(self._last_history_signature != self._saved_history_signature)
        self.update_undo_redo_actions()

    def undo(self):
        if len(self._undo_stack) <= 1:
            return

        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        snapshot = self._undo_stack[-1]
        self.restore_history_snapshot(snapshot)
        self.statusBar().showMessage("Undo", 1500)

    def redo(self):
        if not self._redo_stack:
            return

        snapshot = self._redo_stack.pop()
        self._undo_stack.append(snapshot)
        self.restore_history_snapshot(snapshot)
        self.statusBar().showMessage("Redo", 1500)

    def on_model_changed(self):
        if self._restoring_history:
            return

        self.update_model_outline()
        self.record_history_snapshot()
        self.set_dirty(self._last_history_signature != self._saved_history_signature)

    def set_dirty(self, dirty: bool):
        self.is_dirty = dirty
        marker = "*" if dirty else ""

        if self.current_project_path is not None:
            self.setWindowTitle(f"FUSE - {self.current_project_path.name}{marker}")
        else:
            self.setWindowTitle(f"FUSE{marker}")

        if hasattr(self, "unsaved_indicator"):
            self.unsaved_indicator.setText("● Unsaved" if dirty else "")
            self.unsaved_indicator.setVisible(dirty)

    def mark_dirty(self):
        # Backward-compatible alias for older tests/callers.
        self.on_model_changed()

    def prompt_for_unsaved_changes(self, action_name: str) -> str:
        """Ask the user how to handle dirty model state before a destructive action.

        Returns one of UNSAVED_CHOICE_SAVE, UNSAVED_CHOICE_DISCARD, or
        UNSAVED_CHOICE_CANCEL. Keeping this as a small separate method makes the
        New/Open/Exit lifecycle behavior testable without opening modal dialogs
        in headless/offscreen test runs.
        """
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle("Unsaved Changes")
        message.setText(f"The current FUSE model has unsaved changes. Save before {action_name}?")
        save_button = message.addButton(f"Save && {action_name.title()}", QMessageBox.AcceptRole)
        discard_button = message.addButton("Don't Save", QMessageBox.DestructiveRole)
        cancel_button = message.addButton(QMessageBox.Cancel)
        message.setDefaultButton(save_button)
        message.exec()

        clicked = message.clickedButton()
        if clicked == save_button:
            return UNSAVED_CHOICE_SAVE
        if clicked == discard_button:
            return UNSAVED_CHOICE_DISCARD
        return UNSAVED_CHOICE_CANCEL

    def confirm_discard_unsaved_changes(self, action_name: str) -> bool:
        if not self.is_dirty:
            return True

        choice = self.prompt_for_unsaved_changes(action_name)
        if choice == UNSAVED_CHOICE_CANCEL:
            return False
        if choice == UNSAVED_CHOICE_DISCARD:
            return True
        if choice == UNSAVED_CHOICE_SAVE:
            return self.save_model()

        # Unknown responses are treated as cancel to avoid accidental data loss.
        return False

    def new_project(self):
        if not self.confirm_discard_unsaved_changes("new"):
            return

        settings = ProjectSettings(
            project_name="Untitled FUSE Project",
            active_plugin_id="sst",
        )

        dialog = ProjectSettingsDialog(settings, self)

        if dialog.exec() != QDialog.Accepted:
            return

        self.project_settings = dialog.settings()
        self.project_name = self.project_settings.project_name or "Untitled FUSE Project"
        self.project_settings.project_name = self.project_name

        # Clear the associated file path for a new unsaved project without
        # resetting the project name chosen in Project Settings. Suppress model
        # change history while clearing the previous scene so the old project
        # state cannot be serialized back into the newly accepted settings.
        self.current_project_path = None
        self._restoring_history = True
        try:
            self.close_all_composite_model_tabs()
            self.scene.clear_model()
        finally:
            self._restoring_history = False

        self.properties_panel.set_validation_issues([])
        self.properties_panel.show_empty()
        self.apply_project_settings_to_ui()
        self.model_view.apply_editor_state({})
        self.refresh_project_model_tab_title()
        self.update_model_outline()
        self.reset_undo_history(mark_clean=True)
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

        self.refresh_project_model_tab_title()
        self.set_dirty(self.is_dirty)

    def save_model(self) -> bool:
        if not self.validate_model_before_save():
            return False

        if self.current_project_path is None:
            return self.save_model_as()

        project = self.project_dict()
        try:
            save_project_file(project, self.current_project_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return False

        self._saved_history_signature = self.history_signature()
        self._last_history_signature = self._saved_history_signature
        self.update_undo_redo_actions()
        self.set_dirty(False)
        issue_count = int(getattr(self, "_last_save_validation_issue_count", 0) or 0)
        if issue_count:
            self.statusBar().showMessage(
                f"Saved {self.current_project_path} with {issue_count} validation issue(s) still present",
                5000,
            )
        else:
            self.statusBar().showMessage(f"Saved {self.current_project_path}", 3000)
        return True

    def save_model_as(self) -> bool:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save FUSE Model",
            str(self.current_project_path or ""),
            "FUSE Model (*.fse);;JSON Files (*.json);;All Files (*)",
        )

        if not file_path:
            return False

        if not file_path.endswith(".fse"):
            file_path += ".fse"

        old_path = self.current_project_path
        self.set_current_project_path(file_path)
        if self.save_model():
            return True

        self.set_current_project_path(old_path)
        return False

    def verify_sst_runtime_before_export(self, active) -> bool:
        """Verify custom SST runtime availability before exporting SST JSON."""

        if active is None or active.plugin_id != "sst":
            return True

        target_id = str(getattr(active, "target_id", "") or "")

        if not sst_target_requires_runtime_verification(target_id):
            return True

        toolchain = getattr(active, "toolchain", None)

        if toolchain is None:
            QMessageBox.warning(
                self,
                "SST Runtime Verification Required",
                (
                    "This SST target was created from a discovered/custom SST "
                    "toolchain, but no toolchain settings are available for the "
                    "project. Open Project Settings and verify the SST runtime."
                ),
            )
            return False

        try:
            report = verify_project_sst_runtime(
                scene=self.active_model_scene(),
                framework_version_id=target_id,
                expected_version=getattr(active, "framework_version", "") or "",
                target_label=getattr(active, "target_label", "") or f"SST {getattr(active, 'framework_version', '')}",
                toolchain=toolchain,
                timeout_seconds=120,
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "SST Runtime Verification Failed",
                f"FUSE could not verify the configured SST runtime.\n\n{exc}",
            )
            return False

        if report.errors:
            QMessageBox.critical(
                self,
                "SST Runtime Verification Failed",
                report.message(),
            )
            return False

        if report.warnings:
            response = QMessageBox.warning(
                self,
                "SST Runtime Verification Warning",
                report.message() + "\n\nContinue exporting SST JSON anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            return response == QMessageBox.Yes

        return True

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

        if not self.validate_current_model_for_export():
            return

        if not self.verify_sst_runtime_before_export(active):
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
            plugin = get_plugin_by_id("sst")
            if not hasattr(plugin, "export_model"):
                raise RuntimeError("The SST plugin does not provide an export_model implementation.")

            result = plugin.export_model(
                scene=self.scene,
                output_path=file_path,
                format_id="sst.json",
                plugin_settings=active,
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Export SST JSON Failed",
                str(error),
            )
            return

        message = result.message or f"Exported SST JSON to {file_path}"
        if getattr(result, "report_path", ""):
            message += f" Report: {result.report_path}"

        self.statusBar().showMessage(message, 5000)


    def export_gem5_python(self):
        """
        Export the current gem5-only FUSE model to an editable gem5 Python
        configuration file.
        """
        if not self.scene.component_items():
            QMessageBox.information(
                self,
                "Export gem5 Python",
                "There are no components to export.",
            )
            return

        active = self.project_settings.active_plugin_settings()

        if active is None or active.plugin_id != "gem5":
            QMessageBox.warning(
                self,
                "Export gem5 Python",
                (
                    "The active project target is not gem5.\n\n"
                    "Open Project Settings and select a gem5 target before "
                    "exporting to a gem5 Python configuration."
                ),
            )
            return

        if not self.validate_current_model_for_export():
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export gem5 Python",
            str(self.current_project_path.with_suffix(".gem5.py"))
            if self.current_project_path
            else "",
            "gem5 Python (*.py);;All Files (*)",
        )

        if not file_path:
            return

        if not file_path.lower().endswith(".py"):
            file_path += ".py"

        try:
            from fuse.plugins.community.gem5.export_python import export_gem5_python

            export_gem5_python(
                scene=self.scene,
                output_path=file_path,
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Export gem5 Python Failed",
                str(error),
            )
            return

        self.statusBar().showMessage(
            f"Exported gem5 Python configuration to {file_path}",
            5000,
        )

    def open_model(self):
        if not self.confirm_discard_unsaved_changes("open"):
            return

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
            self.close_all_composite_model_tabs()
            load_project_into_scene(project, self.scene)
            self.properties_panel.set_validation_issues([])
            self.properties_panel.show_empty()
        except Exception as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return

        self.set_current_project_path(file_path)

        self.apply_project_settings_to_ui()
        self.refresh_project_model_tab_title()
        self.model_view.apply_editor_state(project.get("editor", {}))
        self.update_model_outline()
        self.reset_undo_history(mark_clean=True)

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
        issues_by_link: dict[int, list[str]] = {}
        issues_by_attachment: dict[int, list[str]] = {}

        for issue in issues:
            if issue.node_id is not None:
                issues_by_node.setdefault(issue.node_id, []).append(issue.message)
            if issue.link_id is not None:
                issues_by_link.setdefault(issue.link_id, []).append(issue.message)
            attachment_id = getattr(issue, "attachment_id", None)
            if attachment_id is not None:
                issues_by_attachment.setdefault(attachment_id, []).append(issue.message)

        for node in self.scene.component_items():
            node.set_validation_warnings(issues_by_node.get(node.node_id, []))

        for connection in self.scene.connection_items():
            if hasattr(connection, "set_validation_warnings"):
                connection.set_validation_warnings(issues_by_link.get(connection.link.link_id, []))

        for attachment in self.scene.subcomp_attachment_items():
            if hasattr(attachment, "set_validation_warnings"):
                attachment.set_validation_warnings(
                    issues_by_attachment.get(attachment.attachment.attachment_id, [])
                )

        self.properties_panel.set_validation_issues(issues)

    def format_validation_message(self, issues, title: str = "The model has issues") -> str:
        lines = [f"{title}:", ""]

        for issue in issues[:25]:
            lines.append(f"• {issue.object_name}: {issue.message}")

        if len(issues) > 25:
            lines.append("")
            lines.append(f"...and {len(issues) - 25} more issue(s).")

        lines.append("")
        lines.append("Affected components are marked in the canvas and parameter rows are highlighted where possible.")

        return "\n".join(lines)

    def issue_severity(self, issue) -> str:
        severity = (getattr(issue, "severity", "") or "").lower()
        if severity in {"error", "warning", "info"}:
            return severity
        if getattr(issue, "issue_type", "").startswith("info"):
            return "info"
        if getattr(issue, "issue_type", "").startswith("warning"):
            return "warning"
        return "error"

    def issue_scope(self, issue) -> str:
        if getattr(issue, "node_id", None) is not None:
            return "Component"
        if getattr(issue, "link_id", None) is not None:
            return "Link"
        if getattr(issue, "attachment_id", None) is not None:
            return "SubComponent"
        return "Project"

    def issue_suggested_fix(self, issue) -> str:
        parameter_name = getattr(issue, "parameter_name", None)
        issue_type = getattr(issue, "issue_type", "")

        if parameter_name:
            if issue_type in {"component_parameter", "link_parameter"}:
                return f"Set '{parameter_name}' in the Properties panel."
            return f"Review '{parameter_name}' in the Properties panel."

        if issue_type in {"component_name", "link_name"}:
            return "Rename the object so model names are unique and non-empty."
        if issue_type == "subcomp_attachment":
            return "Review or remove the SubComponent attachment."
        if issue_type == "export_target":
            return "Select the correct target or remove unsupported simulator components."
        if issue_type == "export_plugin":
            return "Check the active plugin and target settings."

        return "Review the affected model object."

    def validation_filter_accepts(self, issue) -> bool:
        selected = self.validation_filter.currentText().lower()
        if selected == "all":
            return True
        return self.issue_severity(issue) == selected.rstrip("s")

    def refresh_validation_results_view(self):
        self.validation_results.clear()

        issues = [
            issue
            for issue in getattr(self, "_last_validation_issues", [])
            if self.validation_filter_accepts(issue)
        ]

        if not getattr(self, "_last_validation_issues", []):
            item = QTreeWidgetItem(["Info", "Project", "Project", "No validation issues found.", ""])
            item.setData(0, VALIDATION_ROLE_SEVERITY, "info")
            self.validation_results.addTopLevelItem(item)
        else:
            for index, issue in enumerate(issues):
                severity = self.issue_severity(issue)
                item = QTreeWidgetItem(
                    [
                        severity.capitalize(),
                        self.issue_scope(issue),
                        issue.object_name or "Project",
                        issue.message,
                        self.issue_suggested_fix(issue),
                    ]
                )
                item.setData(0, VALIDATION_ROLE_ISSUE_INDEX, index)
                item.setData(0, VALIDATION_ROLE_SEVERITY, severity)
                item.setData(0, VALIDATION_ROLE_NODE_ID, getattr(issue, "node_id", None))
                item.setData(0, VALIDATION_ROLE_LINK_ID, getattr(issue, "link_id", None))
                item.setData(0, VALIDATION_ROLE_ATTACHMENT_ID, getattr(issue, "attachment_id", None))
                item.setToolTip(3, issue.message)
                item.setToolTip(4, self.issue_suggested_fix(issue))
                self.validation_results.addTopLevelItem(item)

        for column in range(self.validation_results.columnCount()):
            self.validation_results.resizeColumnToContents(column)

    def show_validation_results(self, issues, title: str):
        self._last_validation_issues = list(issues)
        self._last_validation_title = title
        self.refresh_validation_results_view()

        if self.validation_results_dock is not None:
            self.validation_results_dock.setWindowTitle(title)
            self.validation_results_dock.show()
            self.validation_results_dock.raise_()

    def focus_validation_issue(self, issue):
        if getattr(issue, "node_id", None) is not None:
            for node in self.scene.component_items():
                if node.node_id == issue.node_id:
                    self.scene.select_component(node)
                    self.model_view.centerOn(node)
                    return

        if getattr(issue, "link_id", None) is not None:
            connection = self.scene.find_connection_by_link_id(issue.link_id)
            if connection is not None:
                self.scene.select_link(connection)
                self.model_view.centerOn(connection.path().boundingRect().center())
                return

        attachment_id = getattr(issue, "attachment_id", None)
        if attachment_id is not None:
            attachment = self.scene.find_subcomp_attachment_by_id(attachment_id)
            if attachment is not None:
                self.scene.select_subcomp_attachment(attachment)
                self.model_view.centerOn(attachment.path().boundingRect().center())
                return

    def on_validation_result_activated(self, item, column):
        issue_index = item.data(0, VALIDATION_ROLE_ISSUE_INDEX)
        if issue_index is None:
            return

        filtered = [
            issue
            for issue in getattr(self, "_last_validation_issues", [])
            if self.validation_filter_accepts(issue)
        ]

        if 0 <= issue_index < len(filtered):
            self.focus_validation_issue(filtered[issue_index])

    def focus_first_validation_issue(self, issues):
        first_focusable_issue = next(
            (
                issue
                for issue in issues
                if getattr(issue, "node_id", None) is not None
                or getattr(issue, "link_id", None) is not None
                or getattr(issue, "attachment_id", None) is not None
            ),
            None,
        )

        if first_focusable_issue is not None:
            self.focus_validation_issue(first_focusable_issue)

    def validate_current_model(self) -> bool:
        issues = validate_model(self.scene)
        self.apply_validation_issues(issues)
        self.show_validation_results(issues, "FUSE model validation")

        if issues:
            self.focus_first_validation_issue(issues)
            self.statusBar().showMessage(f"Validation found {len(issues)} issue(s)", 5000)
            return False

        self.statusBar().showMessage("Model validation passed", 5000)
        return True

    def validate_current_model_for_export(self) -> bool:
        issues = validate_model_for_export(self.scene, self.active_plugin_id)
        active = self.project_settings.active_plugin_settings()
        target_label = active.target_label if active is not None else self.active_plugin_id or "active target"
        self.apply_validation_issues(issues)
        self.show_validation_results(issues, f"Export validation for {target_label}")

        errors = [issue for issue in issues if self.issue_severity(issue) == "error"]
        warnings = [issue for issue in issues if self.issue_severity(issue) == "warning"]

        if errors:
            self.focus_first_validation_issue(errors)
            self.statusBar().showMessage(
                f"Export validation found {len(errors)} error(s) and {len(warnings)} warning(s)",
                5000,
            )
            return False

        if warnings:
            self.statusBar().showMessage(
                f"Export validation passed with {len(warnings)} warning(s)",
                5000,
            )
            return True

        self.statusBar().showMessage("Export validation passed", 5000)
        return True

    def validate_model_before_save(self) -> bool:
        """Refresh validation feedback before saving without blocking the save.

        A .fse file is the editable project state, so users must be able to save
        work-in-progress models and return later to repair required parameters,
        duplicate names, or incomplete links. Export paths still run their own
        blocking validation because generated simulator files should be runnable.
        """
        issues = validate_model(self.scene)
        self._last_save_validation_issue_count = len(issues)
        self.apply_validation_issues(issues)

        if issues:
            self.focus_first_validation_issue(issues)

        return True

    def on_component_used(self, component):
        self.palette.record_component_used(component)

    def select_model_outline_component_node(self, scene, view, node) -> None:
        scene.clearSelection()
        node.setSelected(True)
        scene.select_component(node)
        view.centerOn(node)

    def on_model_outline_item_clicked(self, item: QTreeWidgetItem, column: int):
        kind = item.data(0, OUTLINE_ROLE_KIND)
        scene = self.active_model_scene()
        view = self.active_model_view()

        if kind == "component":
            node_id = item.data(0, OUTLINE_ROLE_NODE_ID)
            node = scene.find_node_by_id(int(node_id))
            if node is not None:
                self.select_model_outline_component_node(scene, view, node)
            return

        if kind == "link":
            link_id = item.data(0, OUTLINE_ROLE_LINK_ID)
            scene.select_link_by_id(int(link_id))
            return

        if kind == "subcomp_attachment":
            attachment_id = item.data(0, OUTLINE_ROLE_ATTACHMENT_ID)
            attachment = scene.find_subcomp_attachment_by_id(int(attachment_id))
            if attachment is not None:
                child_node = scene.find_node_by_id(attachment.attachment.child_node_id)
                if child_node is not None:
                    self.select_model_outline_component_node(scene, view, child_node)
                else:
                    scene.select_subcomp_attachment(attachment)
            return

    def show_model_outline_context_menu(self, position):
        item = self.model_outline.itemAt(position)

        if item is None:
            return

        kind = item.data(0, OUTLINE_ROLE_KIND)
        scene = self.active_model_scene()

        menu = QMenu(self.model_outline)

        if kind == "link":
            link_id = item.data(0, OUTLINE_ROLE_LINK_ID)
            remove_action = menu.addAction("Remove Link")

            action = menu.exec(self.model_outline.viewport().mapToGlobal(position))

            if action == remove_action:
                scene.delete_link_by_id(int(link_id))
                self.update_model_outline()

            return

        if kind == "subcomp_attachment":
            attachment_id = item.data(0, OUTLINE_ROLE_ATTACHMENT_ID)
            remove_action = menu.addAction("Remove SubComponent Attachment")

            action = menu.exec(self.model_outline.viewport().mapToGlobal(position))

            if action == remove_action:
                scene.delete_subcomp_attachment_by_id(int(attachment_id))
                self.update_model_outline()

            return

        if kind == "component":
            node_id = item.data(0, OUTLINE_ROLE_NODE_ID)
            node = scene.find_node_by_id(int(node_id))

            if node is None:
                return

            add_frequent_action = menu.addAction("Add to Frequently Used")
            menu.addSeparator()

            remove_text = (
                "Remove SubComponent"
                if int(getattr(node.component, "is_subcomp", 0) or 0)
                else "Remove Component"
            )
            remove_action = menu.addAction(remove_text)

            action = menu.exec(self.model_outline.viewport().mapToGlobal(position))

            if action == add_frequent_action:
                self.palette.add_to_frequently_used(node.component)

            elif action == remove_action:
                scene.delete_component_by_id(int(node_id))
                self.update_model_outline()

            return

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            item = self.model_outline.currentItem()
            scene = self.active_model_scene()

            if item is not None and self.model_outline.hasFocus():
                kind = item.data(0, OUTLINE_ROLE_KIND)

                if kind == "link":
                    link_id = item.data(0, OUTLINE_ROLE_LINK_ID)
                    scene.delete_link_by_id(int(link_id))
                    self.update_model_outline()
                    event.accept()
                    return

                if kind == "component":
                    node_id = item.data(0, OUTLINE_ROLE_NODE_ID)
                    scene.delete_component_by_id(int(node_id))
                    self.update_model_outline()
                    event.accept()
                    return

                if kind == "subcomp_attachment":
                    attachment_id = item.data(0, OUTLINE_ROLE_ATTACHMENT_ID)
                    scene.delete_subcomp_attachment_by_id(int(attachment_id))
                    self.update_model_outline()
                    event.accept()
                    return

            # If the outline does not own the focused selection, let the scene handle
            # the selected model item.
            scene.keyPressEvent(event)
            if event.isAccepted():
                self.update_model_outline()
                return

        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.confirm_discard_unsaved_changes("exit"):
            event.accept()
        else:
            event.ignore()

def main():
    """Run the FUSE desktop application event loop.

    The function creates the Qt application, displays the splash screen,
    initializes persistent storage and plugin data through ``MainWindow``, and
    then enters the Qt event loop. It is the console/script entry point used by
    development launches and packaged desktop artifacts.
    """
    prefer_xcb_platform_for_window_manager_shadows()
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
