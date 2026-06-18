# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QKeyEvent

from fuse.core.model.models import ComponentDefinition
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


def _component(name: str) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
    )


def _scene_and_view(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    return scene, view


def _delete_key_event() -> QKeyEvent:
    return QKeyEvent(QEvent.KeyPress, Qt.Key_Delete, Qt.NoModifier)


def test_delete_key_removes_all_selected_components(qtbot, monkeypatch):
    scene, view = _scene_and_view(qtbot, monkeypatch)
    first = scene.create_component_node(_component("CPU"), QPointF(0, 0))
    second = scene.create_component_node(_component("Cache"), QPointF(240, 0))
    third = scene.create_component_node(_component("Memory"), QPointF(480, 0))

    first.setSelected(True)
    second.setSelected(True)

    event = _delete_key_event()
    view.keyPressEvent(event)

    assert event.isAccepted()
    assert [node.instance_name for node in scene.component_items()] == [third.instance_name]


def test_delete_key_expands_group_selection(qtbot, monkeypatch):
    scene, view = _scene_and_view(qtbot, monkeypatch)
    first = scene.create_component_node(_component("CPU"), QPointF(0, 0))
    second = scene.create_component_node(_component("Cache"), QPointF(240, 0))
    third = scene.create_component_node(_component("Memory"), QPointF(480, 0))

    first.setSelected(True)
    second.setSelected(True)
    assert scene.group_selection() is True

    scene.clearSelection()
    first.setSelected(True)

    event = _delete_key_event()
    view.keyPressEvent(event)

    assert event.isAccepted()
    assert [node.instance_name for node in scene.component_items()] == [third.instance_name]


def test_component_context_menu_remove_uses_current_selection(qtbot, monkeypatch):
    scene, _view = _scene_and_view(qtbot, monkeypatch)
    first = scene.create_component_node(_component("CPU"), QPointF(0, 0))
    second = scene.create_component_node(_component("Cache"), QPointF(240, 0))
    third = scene.create_component_node(_component("Memory"), QPointF(480, 0))

    first.setSelected(True)
    second.setSelected(True)

    from fuse.core.ui import graphics_items

    class FakeAction:
        def __init__(self, text: str):
            self._text = text
            self._enabled = True

        def text(self) -> str:
            return self._text

        def setEnabled(self, enabled: bool) -> None:
            self._enabled = bool(enabled)

        def isEnabled(self) -> bool:
            return self._enabled

    class FakeMenu:
        def __init__(self):
            self._actions = []

        def addAction(self, text: str):
            action = FakeAction(text)
            self._actions.append(action)
            return action

        def addSeparator(self) -> None:
            return None

        def actions(self):
            return list(self._actions)

        def exec(self, *_args, **_kwargs):
            for action in self._actions:
                if action.text().startswith("Remove"):
                    return action
            return None

    monkeypatch.setattr(graphics_items, "QMenu", FakeMenu)

    class FakeContextEvent:
        accepted = False

        def screenPos(self):
            return QPointF(0, 0)

        def scenePos(self):
            return QPointF(0, 0)

        def accept(self):
            self.accepted = True

    event = FakeContextEvent()
    first.contextMenuEvent(event)

    assert event.accepted is True
    assert [node.instance_name for node in scene.component_items()] == [third.instance_name]
