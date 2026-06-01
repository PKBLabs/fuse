from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition


def _component(name="CPU"):
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
        category="processor",
    )


def _make_window(qtbot, monkeypatch):
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

    monkeypatch.setattr(
        MainWindow,
        "confirm_discard_unsaved_changes",
        lambda self, action_name: True,
    )

    window = MainWindow()
    qtbot.addWidget(window)
    window.reset_undo_history(mark_clean=True)
    return window


def test_undo_redo_component_creation_restores_scene_and_dirty_indicator(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)

    window.scene.create_component_node(_component("CPU"), QPointF(10, 20))

    assert len(window.scene.component_items()) == 1
    assert window.is_dirty is True
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()
    assert window.unsaved_indicator.text() == "● Unsaved"
    assert not window.unsaved_indicator.isHidden()

    window.undo()

    assert window.scene.component_items() == []
    assert window.is_dirty is False
    assert not window.undo_action.isEnabled()
    assert window.redo_action.isEnabled()
    assert window.unsaved_indicator.text() == ""
    assert window.unsaved_indicator.isHidden()

    window.redo()

    nodes = window.scene.component_items()
    assert len(nodes) == 1
    assert nodes[0].instance_name == "CPU_1"
    assert window.is_dirty is True
    assert window.undo_action.isEnabled()
    assert not window.redo_action.isEnabled()

    window.set_dirty(False)
    window.close()


def test_undo_redo_property_edit_restores_instance_name(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.reset_undo_history(mark_clean=True)

    node.set_instance_name("RenamedCPU")
    window.on_property_changed()

    assert window.scene.component_items()[0].instance_name == "RenamedCPU"
    assert window.is_dirty is True

    window.undo()

    assert window.scene.component_items()[0].instance_name == "CPU_1"
    assert window.is_dirty is False

    window.redo()

    assert window.scene.component_items()[0].instance_name == "RenamedCPU"
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()


def test_undo_redo_component_deletion_restores_component(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.reset_undo_history(mark_clean=True)

    window.scene.delete_component_node(node)

    assert window.scene.component_items() == []
    assert window.is_dirty is True

    window.undo()

    restored = window.scene.component_items()
    assert len(restored) == 1
    assert restored[0].instance_name == "CPU_1"
    assert restored[0].pos() == QPointF(10, 20)
    assert window.is_dirty is False

    window.redo()

    assert window.scene.component_items() == []
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()
