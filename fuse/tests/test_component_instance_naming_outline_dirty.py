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
from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition
from fuse.core.ui.model_scene import ModelScene


def _outline_leaf_texts(tree):
    texts = []

    def visit(item):
        if item.childCount() == 0:
            texts.append(item.text(0))
            return
        for index in range(item.childCount()):
            visit(item.child(index))

    for index in range(tree.topLevelItemCount()):
        visit(tree.topLevelItem(index))

    return texts


def _component(name="CPU"):
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
        category="processor",
    )


def test_scene_generates_unique_default_component_names(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    first = scene.create_component_node(_component("CPU"), QPointF(10, 20))
    second = scene.create_component_node(_component("CPU"), QPointF(30, 40))
    third = scene.create_component_node(_component("CPU"), QPointF(50, 60))

    assert [node.instance_name for node in (first, second, third)] == [
        "CPU_1",
        "CPU_2",
        "CPU_3",
    ]


def test_main_window_outline_and_dirty_state_track_component_creation(qtbot, monkeypatch):
    monkeypatch.setattr("fuse.app.app.ensure_database_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr("fuse.app.app.load_framework_targets", lambda: [])
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )
    monkeypatch.setattr(
        "fuse.core.ui.component_palette.ComponentPalette.load_components",
        lambda self: None,
    )

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.set_dirty(False)

    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))

    assert window.is_dirty is True
    assert window.model_outline.topLevelItemCount() >= 1
    assert node.instance_name in _outline_leaf_texts(window.model_outline)


def test_main_window_dirty_state_tracks_parameter_edits(qtbot, monkeypatch):
    monkeypatch.setattr("fuse.app.app.ensure_database_ready", lambda *args, **kwargs: None)
    monkeypatch.setattr("fuse.app.app.load_framework_targets", lambda: [])
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )
    monkeypatch.setattr(
        "fuse.core.ui.component_palette.ComponentPalette.load_components",
        lambda self: None,
    )

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.set_dirty(False)

    node.set_instance_name("RenamedCPU")
    window.properties_panel.property_changed_callback()

    assert window.is_dirty is True
    assert window.model_outline.topLevelItemCount() >= 1
    assert "RenamedCPU" in _outline_leaf_texts(window.model_outline)
