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


def test_plugin_manager_skips_invalid_metadata_file(tmp_path, monkeypatch):
    from fuse.core.plugin_runtime import manager

    plugin_root = tmp_path / "plugins"
    bad_plugin_dir = plugin_root / "community" / "bad_plugin"
    bad_plugin_dir.mkdir(parents=True)
    (bad_plugin_dir / "plugin.toml").write_text(
        "[plugin\nid = 'bad'\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(manager, "PLUGIN_ROOT", plugin_root)

    assert manager.discover_plugin_manifests() == [bad_plugin_dir / "plugin.toml"]
    assert manager.load_enabled_plugins() == []
