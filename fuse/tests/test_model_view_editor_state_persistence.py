# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from fuse.core.persistence.project_io import build_project_dict
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


def test_project_dict_persists_model_view_editor_state(qtbot):
    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitExposed(view)

    view.set_zoom_percent(200.0)
    view.enable_multiselect_mode()
    view.set_snap_to_grid(True)
    view.set_toolbar_position(72, 36)
    view.centerOn(100.0, 150.0)

    project = build_project_dict(scene, view, "Editor State")

    assert project["editor"]["zoomPercent"] == 200.0
    assert project["editor"]["mode"] == "multiselect"
    assert project["editor"]["snapToGrid"] is True
    assert project["editor"]["toolbarPosition"] == {"x": 72, "y": 36}
    assert abs(project["editor"]["viewCenter"]["x"] - 100) <= 1
    assert abs(project["editor"]["viewCenter"]["y"] - 150) <= 1
