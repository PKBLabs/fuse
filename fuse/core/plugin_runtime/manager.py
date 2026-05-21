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

import importlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FUSE_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = FUSE_PACKAGE_ROOT / "plugins"


@dataclass
class LoadedPlugin:
    plugin_id: str
    name: str
    root: Path
    manifest: dict[str, Any]
    instance: Any


def _load_register_callable(register_path: str):
    module_name, function_name = register_path.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def discover_plugin_manifests() -> list[Path]:
    manifests: list[Path] = []

    for plugin_toml in PLUGIN_ROOT.glob("community/*/plugin.toml"):
        manifests.append(plugin_toml)

    return sorted(manifests)


def load_enabled_plugins() -> list[LoadedPlugin]:
    loaded: list[LoadedPlugin] = []

    for manifest_path in discover_plugin_manifests():
        with manifest_path.open("rb") as handle:
            manifest = tomllib.load(handle)

        plugin_meta = manifest.get("plugin", {})
        entry_points = manifest.get("entry_points", {})

        plugin_id = plugin_meta.get("id", manifest_path.parent.name)
        name = plugin_meta.get("name", plugin_id)
        register_path = entry_points.get("register")

        if not register_path:
            continue

        register_plugin = _load_register_callable(register_path)
        instance = register_plugin()

        loaded.append(
            LoadedPlugin(
                plugin_id=plugin_id,
                name=name,
                root=manifest_path.parent,
                manifest=manifest,
                instance=instance,
            )
        )

    return loaded