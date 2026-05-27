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

    if not PLUGIN_ROOT.exists():
        return manifests

    for plugin_toml in PLUGIN_ROOT.glob("community/*/plugin.toml"):
        manifests.append(plugin_toml)

    return sorted(manifests)


def load_enabled_plugins() -> list[LoadedPlugin]:
    loaded: list[LoadedPlugin] = []

    for manifest_path in discover_plugin_manifests():
        try:
            with manifest_path.open("rb") as handle:
                manifest = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            print(f"Skipping plugin manifest {manifest_path}: invalid TOML: {exc}")
            continue

        plugin_meta = manifest.get("plugin", {})
        entry_points = manifest.get("entry_points", {})

        plugin_id = plugin_meta.get("id", manifest_path.parent.name)
        name = plugin_meta.get("name", plugin_id)
        register_path = entry_points.get("register")

        if not register_path:
            print(f"Skipping plugin '{plugin_id}': no entry_points.register in {manifest_path}")
            continue

        try:
            register_plugin = _load_register_callable(register_path)
            instance = register_plugin()
        except Exception as exc:
            print(
                f"Skipping plugin '{plugin_id}' from {manifest_path}: "
                f"failed to load {register_path}: {exc}"
            )
            continue

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


def get_plugin_by_id(plugin_id: str):
    for plugin in load_enabled_plugins():
        instance_plugin_id = getattr(plugin.instance, "plugin_id", None)

        if plugin.plugin_id == plugin_id or instance_plugin_id == plugin_id:
            return plugin.instance

    loaded_ids = [
        f"{plugin.plugin_id} / {getattr(plugin.instance, 'plugin_id', '<no instance id>')}"
        for plugin in load_enabled_plugins()
    ]

    raise KeyError(
        f"No enabled plugin with id '{plugin_id}'. "
        f"Loaded plugin ids: {loaded_ids}"
    )


def list_all_targets():
    targets = []

    for plugin in load_enabled_plugins():
        instance = plugin.instance

        if hasattr(instance, "list_targets"):
            targets.extend(instance.list_targets())

    return targets


def load_all_palette_items(plugin_id: str | None = None, target_id: str | None = None):
    items = []

    for plugin in load_enabled_plugins():
        instance_plugin_id = getattr(plugin.instance, "plugin_id", plugin.plugin_id)

        if plugin_id is not None and plugin.plugin_id != plugin_id and instance_plugin_id != plugin_id:
            continue

        instance = plugin.instance

        if hasattr(instance, "load_palette_items"):
            items.extend(instance.load_palette_items(target_id=target_id))

    return items


def load_item_details(plugin_id: str, item_id: str, target_id: str | None = None):
    plugin = get_plugin_by_id(plugin_id)

    if not hasattr(plugin, "load_item_details"):
        raise KeyError(f"Plugin '{plugin_id}' does not provide item details.")

    return plugin.load_item_details(item_id, target_id=target_id)
