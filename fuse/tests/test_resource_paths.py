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
from pathlib import Path


def test_logo_path_points_to_png():
    from fuse.core.resource_paths import FUSE_LOGO_PATH

    assert FUSE_LOGO_PATH.name == "fuse_logo.png"
    assert FUSE_LOGO_PATH.suffix == ".png"


def test_arch_component_icon_dir_exists():
    from fuse.core.resource_paths import ARCH_COMPONENT_ICON_DIR

    assert ARCH_COMPONENT_ICON_DIR.exists()
    assert ARCH_COMPONENT_ICON_DIR.is_dir()


def test_resolve_icon_path_handles_existing_relative_icon():
    from fuse.core.resource_paths import ARCH_COMPONENT_ICON_DIR, resolve_icon_path

    icons = list(ARCH_COMPONENT_ICON_DIR.glob("*.png"))

    if not icons:
        return

    icon = icons[0]
    resolved = resolve_icon_path(str(Path("core/resources/media/arch_component_icons") / icon.name))

    assert resolved.exists()