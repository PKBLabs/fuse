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


def test_plugin_manager_skips_broken_plugin(tmp_path, monkeypatch, capsys):
    from fuse.core.plugin_runtime import manager

    plugin_dir = tmp_path / "community" / "broken"
    plugin_dir.mkdir(parents=True)

    (plugin_dir / "plugin.toml").write_text(
        """
[plugin]
id = "broken"
name = "Broken Plugin"
version = "0.0.1"

[entry_points]
register = "does.not.exist:register_plugin"
""",
        encoding="utf-8",
    )

    monkeypatch.setattr(manager, "PLUGIN_ROOT", tmp_path)

    plugins = manager.load_enabled_plugins()
    captured = capsys.readouterr()

    assert plugins == []
    assert "Skipping plugin" in captured.out