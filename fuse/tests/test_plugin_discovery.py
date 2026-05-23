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
def test_plugin_discovery_loads_community_plugins():
    from fuse.core.plugin_runtime.manager import load_enabled_plugins

    plugins = load_enabled_plugins()
    plugin_ids = {plugin.plugin_id for plugin in plugins}

    assert "sst" in plugin_ids
    assert "gem5" in plugin_ids


def test_loaded_plugins_have_instances():
    from fuse.core.plugin_runtime.manager import load_enabled_plugins

    plugins = load_enabled_plugins()

    for plugin in plugins:
        assert plugin.instance is not None
        assert hasattr(plugin.instance, "plugin_id")
        assert hasattr(plugin.instance, "name")