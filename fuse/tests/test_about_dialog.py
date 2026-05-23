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
def test_about_dialog_opens_and_closes(qtbot):
    from fuse.app.about import AboutDialog

    dialog = AboutDialog()
    qtbot.addWidget(dialog)

    dialog.show()
    qtbot.wait(100)

    assert dialog.isVisible()
    assert "About" in dialog.windowTitle()

    dialog.close()
    qtbot.wait(50)

    assert not dialog.isVisible()