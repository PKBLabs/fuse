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


FUSE_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

ARCH_COMPONENT_ICON_RELATIVE_DIR = Path(
    "core/resources/media/arch_component_icons"
)

ARCH_COMPONENT_ICON_DIR = FUSE_PACKAGE_ROOT / ARCH_COMPONENT_ICON_RELATIVE_DIR

FUSE_LOGO_RELATIVE_PATH = Path("core") / "resources" / "media" / "fuse_logo.png"
FUSE_LOGO_PATH = FUSE_PACKAGE_ROOT / FUSE_LOGO_RELATIVE_PATH
FUSE_ICON_RELATIVE_PATH = Path("core") / "resources" / "media" / "fuse_icon.png"
FUSE_ICON_PATH = FUSE_PACKAGE_ROOT / FUSE_ICON_RELATIVE_PATH


def resolve_icon_path(icon_path: str) -> Path:
    if not icon_path:
        return Path()

    path = Path(icon_path)

    if path.is_absolute():
        return path

    candidates = [
        Path.cwd() / path,
        FUSE_PACKAGE_ROOT / path,
        ARCH_COMPONENT_ICON_DIR / path.name,
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return ARCH_COMPONENT_ICON_DIR / path.name