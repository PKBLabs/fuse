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
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.gem5_live


def find_gem5_binary() -> str:
    explicit = os.environ.get("GEM5_BINARY", "").strip()

    if explicit:
        path = Path(explicit)

        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    gem5_root = os.environ.get("GEM5_ROOT", "").strip()

    if gem5_root:
        root = Path(gem5_root)

        candidates = [
            root / "build" / "X86" / "gem5.opt",
            root / "build" / "RISCV" / "gem5.opt",
            root / "build" / "ARM" / "gem5.opt",
            root / "gem5.opt",
        ]

        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)

    from_path = shutil.which("gem5")

    if from_path:
        return from_path

    pytest.skip(
        "No gem5 binary found. Set GEM5_BINARY or GEM5_ROOT, or run inside a "
        "gem5-capable CI image."
    )


def test_real_gem5_binary_runs():
    gem5_binary = find_gem5_binary()

    result = subprocess.run(
        [gem5_binary, "--help"],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    output = result.stdout + result.stderr

    assert result.returncode == 0
    assert "gem5" in output.lower()
    assert "usage" in output.lower() or "options" in output.lower()

def test_real_gem5_metadata_probe_discovers_simobjects():
    from fuse.core.model.project_settings import ToolchainSettings
    from fuse.plugins.community.gem5.plugin import query_gem5_metadata

    gem5_binary = find_gem5_binary()
    metadata = query_gem5_metadata(ToolchainSettings(tool_paths={"gem5Binary": gem5_binary}))

    type_names = {component["type_name"] for component in metadata["components"]}
    assert "System" in type_names
    assert "Root" in type_names
    assert any(name.endswith("CPU") for name in type_names)
    assert any(name in type_names for name in {"SystemXBar", "IOXBar"})


def test_real_gem5_import_metadata_populates_live_catalog(tmp_path, monkeypatch):
    from fuse.core.model.project_settings import PluginProjectSettings, ToolchainSettings
    from fuse.core.persistence.database import get_connection
    from fuse.plugins.community.gem5.plugin import Gem5Plugin

    gem5_binary = find_gem5_binary()
    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "app.db"))

    plugin = Gem5Plugin()
    with get_connection() as conn:
        plugin.initialize_database(conn)
        conn.commit()

    plugin.import_metadata_for_toolchain(
        PluginProjectSettings(
            plugin_id="gem5",
            target_label="Live gem5 import",
            toolchain=ToolchainSettings(tool_paths={"gem5Binary": gem5_binary}),
        )
    )

    live_target = next(target for target in plugin.list_targets() if target.display_name == "Live gem5 import")
    items = plugin.load_palette_items(target_id=live_target.target_id)
    type_names = {item.type_name for item in items}

    assert "System" in type_names
    assert "Root" in type_names
    assert any(name.endswith("CPU") for name in type_names)

    system_item = next(item for item in items if item.type_name == "System")
    details = plugin.load_item_details(system_item.item_id, target_id=live_target.target_id)

    assert details.palette_item.type_name == "System"
    assert details.properties or details.connectors
