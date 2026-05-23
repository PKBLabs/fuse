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
def test_splash_can_be_constructed(qtbot):
    from fuse.app.splash import create_splash_screen

    splash = create_splash_screen()
    qtbot.addWidget(splash)

    splash.set_message("Testing splash...")
    splash.show_centered()
    qtbot.wait(100)

    assert splash.isVisible()

    splash.close()
    qtbot.wait(50)

    assert not splash.isVisible()


def test_splash_message_can_be_updated(qtbot):
    from fuse.app.splash import create_splash_screen

    splash = create_splash_screen()
    qtbot.addWidget(splash)

    splash.set_message("Loading test plugins...")

    assert splash.message_label.text() == "Loading test plugins..."