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
def test_guess_component_icon_path_returns_string_for_cache():
    from fuse.plugins.community.sst.sst_icon_resolver import guess_component_icon_path

    icon_path = guess_component_icon_path(
        name="TestCache",
        description="Cache memory component",
        category="MEMORY COMPONENT",
        iface="",
        element="testElement",
        object_kind="Component",
    )

    assert isinstance(icon_path, str)


def test_guess_component_icon_path_returns_string_for_nic():
    from fuse.plugins.community.sst.sst_icon_resolver import guess_component_icon_path

    icon_path = guess_component_icon_path(
        name="MemNIC",
        description="Network interface for memory hierarchy",
        category="NETWORK COMPONENT",
        iface="",
        element="testElement",
        object_kind="Component",
    )

    assert isinstance(icon_path, str)


def test_guess_component_icon_path_does_not_crash_for_unknown_component():
    from fuse.plugins.community.sst.sst_icon_resolver import guess_component_icon_path

    icon_path = guess_component_icon_path(
        name="CompletelyUnknownThing",
        description="",
        category="",
        iface="",
        element="",
        object_kind="Component",
    )

    assert isinstance(icon_path, str)