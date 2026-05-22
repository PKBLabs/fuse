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