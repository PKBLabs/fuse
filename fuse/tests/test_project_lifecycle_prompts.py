from pathlib import Path

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QDialog

from fuse.core.model.models import ComponentDefinition


def _component(name="CPU"):
    return ComponentDefinition(
        plugin_id="core",
        component_id=name.lower(),
        element="test",
        name=name,
        category="processor",
    )


class _FakeCloseEvent:
    def __init__(self):
        self.accepted = False
        self.ignored = False

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


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
    monkeypatch.setattr("fuse.app.app.QMessageBox.critical", lambda *args, **kwargs: None)
    monkeypatch.setattr("fuse.app.app.QMessageBox.warning", lambda *args, **kwargs: None)

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)
    window.reset_undo_history(mark_clean=True)
    return window


def test_confirm_discard_unsaved_changes_honors_save_discard_cancel(qtbot, monkeypatch):
    from fuse.app.app import (
        UNSAVED_CHOICE_CANCEL,
        UNSAVED_CHOICE_DISCARD,
        UNSAVED_CHOICE_SAVE,
    )

    window = _make_window(qtbot, monkeypatch)
    save_calls = []
    monkeypatch.setattr(window, "save_model", lambda: save_calls.append("save") or True)

    window.set_dirty(False)
    assert window.confirm_discard_unsaved_changes("open") is True
    assert save_calls == []

    window.set_dirty(True)
    monkeypatch.setattr(window, "prompt_for_unsaved_changes", lambda action: UNSAVED_CHOICE_DISCARD)
    assert window.confirm_discard_unsaved_changes("open") is True
    assert save_calls == []

    monkeypatch.setattr(window, "prompt_for_unsaved_changes", lambda action: UNSAVED_CHOICE_CANCEL)
    assert window.confirm_discard_unsaved_changes("open") is False
    assert save_calls == []

    monkeypatch.setattr(window, "prompt_for_unsaved_changes", lambda action: UNSAVED_CHOICE_SAVE)
    assert window.confirm_discard_unsaved_changes("open") is True
    assert save_calls == ["save"]

    monkeypatch.setattr(window, "save_model", lambda: False)
    assert window.confirm_discard_unsaved_changes("open") is False

    window.set_dirty(False)
    window.close()


def test_open_model_cancel_and_failed_save_do_not_prompt_for_file(qtbot, monkeypatch):
    from fuse.app.app import MainWindow, UNSAVED_CHOICE_CANCEL, UNSAVED_CHOICE_SAVE

    window = _make_window(qtbot, monkeypatch)
    window.set_dirty(True)

    def fail_file_dialog(*args, **kwargs):
        raise AssertionError("file dialog should not open")

    monkeypatch.setattr("fuse.app.app.QFileDialog.getOpenFileName", fail_file_dialog)
    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_CANCEL)
    window.open_model()

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_SAVE)
    monkeypatch.setattr(window, "save_model", lambda: False)
    window.open_model()

    window.set_dirty(False)
    window.close()


def test_open_model_discard_loads_selected_file_and_marks_clean(qtbot, monkeypatch, tmp_path):
    from fuse.app.app import MainWindow, UNSAVED_CHOICE_DISCARD

    opened_path = tmp_path / "demo.fse"
    project = {
        "project": {"name": "Demo"},
        "projectSettings": {"projectName": "Demo", "activePluginId": "sst", "plugins": {}},
        "components": [],
        "links": [],
        "subcompAttachments": [],
    }
    load_scene_calls = []

    window = _make_window(qtbot, monkeypatch)
    window.set_dirty(True)

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_DISCARD)
    monkeypatch.setattr("fuse.app.app.QFileDialog.getOpenFileName", lambda *args, **kwargs: (str(opened_path), ""))
    monkeypatch.setattr("fuse.app.app.load_project_file", lambda path: project)
    monkeypatch.setattr("fuse.app.app.load_project_into_scene", lambda project, scene: load_scene_calls.append((project, scene)))

    window.open_model()

    assert window.current_project_path == opened_path
    assert window.project_name == "demo"
    assert window.is_dirty is False
    assert load_scene_calls and load_scene_calls[0][0] is project

    window.close()


def test_close_event_respects_unsaved_prompt_choice(qtbot, monkeypatch):
    from fuse.app.app import MainWindow, UNSAVED_CHOICE_CANCEL, UNSAVED_CHOICE_DISCARD

    window = _make_window(qtbot, monkeypatch)
    window.set_dirty(True)
    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_CANCEL)

    event = _FakeCloseEvent()
    window.closeEvent(event)

    assert event.ignored is True
    assert event.accepted is False

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_DISCARD)
    event = _FakeCloseEvent()
    window.closeEvent(event)

    assert event.accepted is True
    assert event.ignored is False

    window.set_dirty(False)
    window.close()


def test_save_model_as_appends_extension_updates_path_and_clears_dirty(qtbot, monkeypatch, tmp_path):
    saved_paths = []
    chosen_path = tmp_path / "renamed-project"

    window = _make_window(qtbot, monkeypatch)
    window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    assert window.is_dirty is True

    monkeypatch.setattr(window, "validate_model_before_save", lambda: True)
    monkeypatch.setattr("fuse.app.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(chosen_path), ""))
    monkeypatch.setattr("fuse.app.app.save_project_file", lambda project, path: saved_paths.append(Path(path)))

    assert window.save_model_as() is True

    assert saved_paths == [chosen_path.with_suffix(".fse")]
    assert window.current_project_path == chosen_path.with_suffix(".fse")
    assert window.project_name == "renamed-project"
    assert window.is_dirty is False

    window.close()


def test_save_model_as_restores_previous_path_after_failed_write(qtbot, monkeypatch, tmp_path):
    previous_path = tmp_path / "existing.fse"
    chosen_path = tmp_path / "failed-save"

    window = _make_window(qtbot, monkeypatch)
    window.set_current_project_path(previous_path)
    window.set_dirty(True)

    monkeypatch.setattr(window, "validate_model_before_save", lambda: True)
    monkeypatch.setattr("fuse.app.app.QFileDialog.getSaveFileName", lambda *args, **kwargs: (str(chosen_path), ""))

    def fail_save(project, path):
        raise OSError("disk full")

    monkeypatch.setattr("fuse.app.app.save_project_file", fail_save)

    assert window.save_model_as() is False

    assert window.current_project_path == previous_path
    assert window.project_name == "existing"
    assert window.is_dirty is True

    window.set_dirty(False)
    window.close()


def test_new_project_cancel_save_failure_and_discard_paths(qtbot, monkeypatch):
    from fuse.app.app import MainWindow, UNSAVED_CHOICE_CANCEL, UNSAVED_CHOICE_DISCARD, UNSAVED_CHOICE_SAVE

    class AcceptedProjectDialog:
        def __init__(self, settings, parent=None):
            self._settings = settings
            self._settings.project_name = "New Demo"
            self._settings.active_plugin_id = "gem5"

        def exec(self):
            return QDialog.Accepted

        def settings(self):
            return self._settings

    window = _make_window(qtbot, monkeypatch)
    window.scene.create_component_node(_component("CPU"), QPointF(10, 20))
    assert window.scene.component_items()
    window.set_dirty(True)

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_CANCEL)
    window.new_project()
    assert window.scene.component_items()
    assert window.is_dirty is True

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_SAVE)
    monkeypatch.setattr(window, "save_model", lambda: False)
    window.new_project()
    assert window.scene.component_items()
    assert window.is_dirty is True

    monkeypatch.setattr(MainWindow, "prompt_for_unsaved_changes", lambda self, action: UNSAVED_CHOICE_DISCARD)
    monkeypatch.setattr("fuse.app.app.ProjectSettingsDialog", AcceptedProjectDialog)
    window.new_project()

    assert window.scene.component_items() == []
    assert window.project_name == "New Demo"
    assert window.project_settings.active_plugin_id == "gem5"
    assert window.current_project_path is None
    assert window.is_dirty is False

    window.close()
