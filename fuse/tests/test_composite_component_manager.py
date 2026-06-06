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


def make_definition(composite_id="managed-template", name="Managed Template"):
    from fuse.core.model.composite import CompositeComponentDefinition

    return CompositeComponentDefinition.make(
        composite_id=composite_id,
        name=name,
        description="Reusable test composite",
        icon_path="icons/managed.png",
        mini_model={
            "schemaVersion": "0.1.0",
            "kind": "fuse.composite-mini-model",
            "components": [],
            "links": [],
            "subcompAttachments": [],
        },
    )


def test_composite_manager_lists_and_deletes_definitions(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))

    from PySide6.QtWidgets import QMessageBox
    from fuse.app.composite_component_manager_dialog import CompositeComponentManagerDialog
    from fuse.core.persistence.composite_components import (
        get_composite_component_definition,
        save_composite_component_definition,
    )

    definition = save_composite_component_definition(make_definition())
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)

    dialog = CompositeComponentManagerDialog()
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 1
    assert dialog.table.item(0, 0).text() == definition.name
    assert dialog.export_button.isEnabled() is False
    assert dialog.delete_button.isEnabled() is False

    dialog.table.selectRow(0)
    assert dialog.export_button.isEnabled() is True
    assert dialog.delete_button.isEnabled() is True

    dialog.delete_selected_definition()

    assert dialog.changed is True
    assert dialog.table.rowCount() == 0
    assert get_composite_component_definition(definition.composite_id) is None


def test_composite_manager_imports_and_exports_definitions(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))

    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from fuse.app.composite_component_manager_dialog import CompositeComponentManagerDialog
    from fuse.core.persistence.composite_component_files import write_composite_component_file
    from fuse.core.persistence.composite_components import save_composite_component_definition

    source_path = write_composite_component_file(
        make_definition(composite_id="imported-template", name="Imported Template"),
        tmp_path / "imported_template.fcc",
    )
    export_definition = save_composite_component_definition(
        make_definition(composite_id="export-template", name="Export Template")
    )
    export_path = tmp_path / "exported_template.fcc"

    open_paths = [str(source_path)]
    save_paths = [str(export_path)]
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args, **kwargs: (open_paths.pop(0), ""))
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (save_paths.pop(0), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: QMessageBox.Ok)

    dialog = CompositeComponentManagerDialog()
    qtbot.addWidget(dialog)

    assert dialog.table.rowCount() == 1
    dialog.import_definition()
    assert dialog.changed is True
    assert dialog.table.rowCount() == 2

    dialog.select_definition(export_definition.composite_id)
    dialog.export_selected_definition()
    assert export_path.exists()


def test_main_window_registers_composite_manager_action(qtbot, tmp_path, monkeypatch):
    db_path = tmp_path / "test_app.db"
    monkeypatch.setenv("FUSE_DB_PATH", str(db_path))

    from fuse.app.app import MainWindow

    window = MainWindow()
    qtbot.addWidget(window)

    assert window.manage_composite_components_action.text() == "Manage Composite Components..."

    window.close()
