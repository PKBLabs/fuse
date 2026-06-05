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


def test_main_window_constructs_and_closes(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    window.show()
    qtbot.wait(100)

    assert window.windowTitle()
    assert window.palette is not None
    assert window.scene is not None
    assert window.model_view is not None
    assert window.properties_panel is not None

    window.close()
    qtbot.wait(50)

    assert not window.isVisible()

def test_available_components_panel_is_dockable(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QDockWidget
    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(100)

    assert window.centralWidget() is window.model_tabs
    assert window.model_tabs.widget(0) is window.model_view
    assert isinstance(window.component_palette_dock, QDockWidget)
    assert window.component_palette_dock.windowTitle() == "Available Components"
    assert window.component_palette_dock.widget() is window.component_palette_panel
    assert window.palette.parent() is window.component_palette_panel
    assert window.dockWidgetArea(window.component_palette_dock) == Qt.LeftDockWidgetArea
    assert window.component_palette_dock.features() & QDockWidget.DockWidgetMovable
    assert window.component_palette_dock.features() & QDockWidget.DockWidgetFloatable
    assert window.component_palette_dock.titleBarWidget() is None

    window.component_palette_dock.setFloating(True)
    qtbot.wait(50)
    assert window.component_palette_dock.titleBarWidget() is not None
    window.component_palette_dock.setFloating(False)
    qtbot.wait(50)
    assert window.component_palette_dock.titleBarWidget() is None

    assert window.component_palette_dock.toggleViewAction() in window.view_menu.actions()

    window.close()


def test_docks_use_native_title_bars_until_floating(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(100)

    assert window.component_palette_dock.titleBarWidget() is None
    assert window.properties_dock.titleBarWidget() is None
    assert window.model_outline_dock.titleBarWidget() is None
    assert window.validation_results_dock.titleBarWidget() is None

    window.properties_dock.setFloating(True)
    qtbot.wait(50)
    floating_title_bar = window.properties_dock.titleBarWidget()
    assert floating_title_bar is not None
    assert floating_title_bar.__class__.__name__ == "FloatingDockTitleBar"

    window.properties_dock.setFloating(False)
    qtbot.wait(50)
    assert window.properties_dock.titleBarWidget() is None

    window.close()


def test_create_composite_action_follows_multiselection(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    from PySide6.QtCore import QPointF
    from fuse.app.app import MainWindow
    from fuse.core.model.models import ComponentDefinition

    window = MainWindow()
    qtbot.addWidget(window)

    first = window.scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="first", element="test", name="First"),
        QPointF(0.0, 0.0),
    )
    second = window.scene.create_component_node(
        ComponentDefinition(plugin_id="core", component_id="second", element="test", name="Second"),
        QPointF(300.0, 0.0),
    )

    assert window.create_composite_action.text() == "Create Composite Component from Selection"
    assert window.create_composite_action.isEnabled() is False

    first.setSelected(True)
    second.setSelected(True)
    window.model_view.update_selection_highlights()

    assert window.create_composite_action.isEnabled() is True

    second.setSelected(False)
    window.model_view.update_selection_highlights()

    assert window.create_composite_action.isEnabled() is False

    window.set_dirty(False)
    window.close()


def test_composite_import_export_actions_are_registered(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.import_composite_action.text() == "Import Composite Component..."
    assert window.export_composite_action.text() == "Selected Composite Component..."

    window.close()


def test_model_view_uses_project_tab(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.model_tabs.count() == 1
    assert window.model_tabs.tabText(0) == "Untitled FUSE Project"
    assert window.model_tabs.widget(0) is window.model_view

    window.close_model_tab(0)
    assert window.model_tabs.count() == 1

    window.close()


def test_double_click_composite_opens_model_view_tab(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    from PySide6.QtCore import QPointF
    from fuse.app.app import MainWindow
    from fuse.core.model.composite import CompositeComponentDefinition
    from fuse.core.persistence.composite_components import save_composite_component_definition
    from fuse.core.ui.composite_builder import component_definition_for_composite
    from fuse.core.ui.composite_instance_editor import CompositeInstanceEditorWidget

    definition = save_composite_component_definition(
        CompositeComponentDefinition.make(
            composite_id="tabbed-editor-template",
            name="Cache Pair",
            mini_model={
                "schemaVersion": "0.1.0",
                "kind": "fuse.composite-mini-model",
                "components": [],
                "links": [],
                "subcompAttachments": [],
            },
            port_mappings=[],
        )
    )

    window = MainWindow()
    qtbot.addWidget(window)
    node = window.scene.create_component_node(
        component_definition_for_composite(definition),
        QPointF(0.0, 0.0),
    )

    window.edit_composite_instance(node)

    assert window.model_tabs.count() == 2
    assert window.model_tabs.tabText(1) == node.instance_name
    assert isinstance(window.model_tabs.widget(1), CompositeInstanceEditorWidget)

    window.close_model_tab(1)
    assert window.model_tabs.count() == 1

    window.set_dirty(False)
    window.close()


def test_nested_composite_opens_hierarchical_model_view_tab(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"

    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))
    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    from PySide6.QtCore import QPointF
    from fuse.app.app import MainWindow
    from fuse.core.model.composite import CompositeComponentDefinition
    from fuse.core.persistence.composite_components import save_composite_component_definition
    from fuse.core.ui.composite_builder import component_definition_for_composite
    from fuse.core.ui.composite_instance_editor import CompositeInstanceEditorWidget

    inner = save_composite_component_definition(
        CompositeComponentDefinition.make(
            composite_id="inner-tab-template",
            name="Inner",
            mini_model={
                "schemaVersion": "0.1.0",
                "kind": "fuse.composite-mini-model",
                "components": [],
                "links": [],
                "subcompAttachments": [],
            },
            port_mappings=[],
        )
    )
    outer = save_composite_component_definition(
        CompositeComponentDefinition.make(
            composite_id="outer-tab-template",
            name="Outer",
            mini_model={
                "schemaVersion": "0.1.0",
                "kind": "fuse.composite-mini-model",
                "components": [
                    {
                        "id": 1,
                        "element": "Composite Components",
                        "name": "Inner",
                        "pluginId": "core",
                        "targetId": "fuse-composite",
                        "componentId": inner.composite_id,
                        "isComposite": 1,
                        "compositeId": inner.composite_id,
                        "instanceName": "Inner_1",
                        "parameters": {},
                        "variablePortCounts": {},
                        "position": {"x": 0.0, "y": 0.0},
                    }
                ],
                "links": [],
                "subcompAttachments": [],
            },
            port_mappings=[],
        )
    )

    window = MainWindow()
    qtbot.addWidget(window)
    outer_node = window.scene.create_component_node(
        component_definition_for_composite(outer),
        QPointF(0.0, 0.0),
    )

    window.edit_composite_instance(outer_node)
    outer_editor = window.model_tabs.widget(1)
    assert isinstance(outer_editor, CompositeInstanceEditorWidget)
    inner_node = outer_editor.editor_scene.component_items()[0]

    outer_editor.request_nested_composite_edit(inner_node)

    assert window.model_tabs.count() == 3
    assert window.model_tabs.tabText(2) == f"{outer_node.instance_name}:{inner_node.instance_name}"

    window.close_model_tab(1)
    assert window.model_tabs.count() == 1

    window.set_dirty(False)
    window.close()
