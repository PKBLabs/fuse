from PySide6.QtCore import QPointF

from fuse.core.model.models import ComponentDefinition
from fuse.plugin_api.interfaces import LinkCompatibilityResult


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
    assert nodes[0].instance_name == "CPU_0"
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

    assert window.scene.component_items()[0].instance_name == "CPU_0"
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
    assert restored[0].instance_name == "CPU_0"
    assert restored[0].pos() == QPointF(10, 20)
    assert window.is_dirty is False

    window.redo()

    assert window.scene.component_items() == []
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()



def _port(node, name):
    return next(port for port in node.ports if port.name == name)


def _subcomp_component(name, *, is_subcomp=0, iface=""):
    return ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        component_id=name,
        element="test",
        name=name,
        is_subcomp=is_subcomp,
        iface=iface,
    )


def _subcomp_metadata(plugin_id, component_id, target_id=None):
    if component_id == "Parent":
        return [{"name": "slot", "role": "slot", "required_interface": "Iface", "interface": "Iface"}]
    if component_id == "Child":
        return [{"name": "iface", "role": "interface", "provided_interface": "Iface", "interface": "Iface"}]
    return []


def test_undo_redo_link_creation_and_deletion(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    src = window.scene.create_component_node(_component("Source"), QPointF(10, 20))
    dst = window.scene.create_component_node(_component("Target"), QPointF(320, 20))
    window.reset_undo_history(mark_clean=True)

    connection = window.scene.create_link_between_ports(
        _port(src, "out"),
        _port(dst, "in"),
        LinkCompatibilityResult(),
    )

    assert len(window.scene.links) == 1
    assert window.is_dirty is True

    window.undo()

    assert window.scene.links == []
    assert window.scene.connection_items() == []
    assert window.is_dirty is False

    window.redo()

    assert len(window.scene.links) == 1
    assert len(window.scene.connection_items()) == 1
    assert window.is_dirty is True

    restored_connection = window.scene.connection_items()[0]
    window.scene.delete_link(restored_connection)

    assert window.scene.links == []
    # Deleting the redone link returns the model to the clean baseline
    # captured after the two components were created.
    assert window.is_dirty is False

    window.undo()

    assert len(window.scene.links) == 1
    assert window.scene.links[0].source_port == "out"
    assert window.scene.links[0].target_port == "in"
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()


def test_undo_redo_subcomponent_attachment_creation_and_deletion(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_subcomp_connector_metadata_for_component",
        _subcomp_metadata,
    )
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        lambda *args, **kwargs: [],
    )
    window = _make_window(qtbot, monkeypatch)
    parent = window.scene.create_component_node(_subcomp_component("Parent"), QPointF(0, 0))
    child = window.scene.create_component_node(
        _subcomp_component("Child", is_subcomp=1, iface="Iface"),
        QPointF(320, 0),
    )
    window.reset_undo_history(mark_clean=True)

    item = window.scene.create_subcomp_attachment(
        parent.subcomp_connectors[0],
        child.subcomp_connectors[0],
        LinkCompatibilityResult(),
    )

    assert len(window.scene.subcomp_attachments) == 1
    assert len(window.scene.subcomp_attachment_items()) == 1
    assert window.is_dirty is True

    window.undo()

    assert window.scene.subcomp_attachments == []
    assert window.scene.subcomp_attachment_items() == []
    assert window.is_dirty is False

    window.redo()

    assert len(window.scene.subcomp_attachments) == 1
    assert len(window.scene.subcomp_attachment_items()) == 1
    assert window.is_dirty is True

    window.scene.delete_subcomp_attachment(window.scene.subcomp_attachment_items()[0])

    assert window.scene.subcomp_attachments == []

    window.undo()

    assert len(window.scene.subcomp_attachments) == 1
    assert window.scene.subcomp_attachments[0].slot_name == "slot"
    assert window.scene.subcomp_attachments[0].provided_interface == "Iface"

    window.set_dirty(False)
    window.close()


def test_undo_redo_component_move_restores_canvas_layout(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.reset_undo_history(mark_clean=True)

    node.setPos(QPointF(250, 140))

    assert window.is_dirty is True
    assert window.scene.component_items()[0].pos() == QPointF(250, 140)

    window.undo()

    assert window.scene.component_items()[0].pos() == QPointF(10, 20)
    assert window.is_dirty is False

    window.redo()

    assert window.scene.component_items()[0].pos() == QPointF(250, 140)
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()


def test_interactive_drag_records_one_history_entry(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    node = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.reset_undo_history(mark_clean=True)

    window.scene.begin_node_drag()
    node.setPos(QPointF(100, 120))
    node.setPos(QPointF(180, 240))
    node.setPos(QPointF(260, 300))
    window.scene.end_node_drag(node)

    assert len(window._undo_stack) == 2
    assert window.scene.component_items()[0].pos() == QPointF(260, 300)

    window.undo()

    assert window.scene.component_items()[0].pos() == QPointF(10, 20)
    assert window.is_dirty is False

    window.set_dirty(False)
    window.close()


def test_redo_stack_clears_after_new_edit(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    first = window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    window.reset_undo_history(mark_clean=True)

    second = window.scene.create_component_node(_component("Cache"), QPointF(300, 20))
    assert window.redo_action.isEnabled() is False

    window.undo()

    assert len(window.scene.component_items()) == 1
    assert window.redo_action.isEnabled() is True

    window.scene.component_items()[0].set_instance_name("EditedCPU")
    window.on_property_changed()

    assert window.redo_action.isEnabled() is False
    assert len(window._redo_stack) == 0
    assert window.scene.component_items()[0].instance_name == "EditedCPU"

    window.set_dirty(False)
    window.close()


def test_undo_history_is_bounded(qtbot, monkeypatch):
    window = _make_window(qtbot, monkeypatch)
    window._history_limit = 3
    window.reset_undo_history(mark_clean=True)

    for index in range(8):
        window.scene.create_component_node(_component(f"Node{index}"), QPointF(index * 20, 20))

    assert len(window._undo_stack) == 4
    assert window.undo_action.isEnabled() is True

    window.set_dirty(False)
    window.close()
