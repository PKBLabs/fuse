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
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt

from fuse.core.model.models import ComponentDefinition, MIME_COMPONENT
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


class _DropEvent:
    def __init__(self, mime_data, position):
        self._mime_data = mime_data
        self._position = QPointF(position)
        self.accepted = False

    def mimeData(self):
        return self._mime_data

    def position(self):
        return self._position

    def acceptProposedAction(self):
        self.accepted = True


def test_model_view_drop_creates_component_at_model_coordinates(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.show()
    qtbot.waitExposed(view)

    component = ComponentDefinition(
        plugin_id="core",
        component_id="cpu",
        element="test",
        name="CPU",
        category="processor",
    )
    mime = QMimeData()
    mime.setData(MIME_COMPONENT, component.to_drag_text().encode("utf-8"))

    viewport_position = QPoint(180, 140)
    expected_scene_position = view.mapToScene(viewport_position)
    event = _DropEvent(mime, viewport_position)

    view.dropEvent(event)

    nodes = scene.component_items()
    assert event.accepted is True
    assert len(nodes) == 1
    assert nodes[0].component.name == "CPU"
    assert nodes[0].instance_name == "CPU_1"
    assert nodes[0].pos() == expected_scene_position
