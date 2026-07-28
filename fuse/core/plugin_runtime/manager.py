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
"""Runtime discovery and dispatch for FUSE plugins.

The plugin runtime locates community plugin manifests, imports each plugin's
registration function, and exposes small dispatch helpers used by the UI,
validation, palette loading, and export flows."""

from __future__ import annotations

import importlib
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


FUSE_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = FUSE_PACKAGE_ROOT / "plugins"

_LOADED_PLUGINS_CACHE: list["LoadedPlugin"] | None = None
_TARGETS_CACHE: list[Any] | None = None
_PALETTE_ITEMS_CACHE: dict[tuple[str | None, str | None], list[Any]] = {}
_ITEM_DETAILS_CACHE: dict[tuple[str, str, str | None], Any] = {}


def clear_plugin_runtime_caches(*, include_plugins: bool = False) -> None:
    """Clear cached plugin metadata.

    Plugin discovery and SST catalog reads are relatively expensive on large
    project load paths. Runtime metadata is cached for normal UI reads and can be
    explicitly invalidated after catalog/bootstrap operations.
    """
    global _LOADED_PLUGINS_CACHE, _TARGETS_CACHE
    if include_plugins:
        _LOADED_PLUGINS_CACHE = None
    _TARGETS_CACHE = None
    _PALETTE_ITEMS_CACHE.clear()
    _ITEM_DETAILS_CACHE.clear()



@dataclass
class LoadedPlugin:
    """Loaded plugin instance and metadata parsed from its manifest."""
    plugin_id: str
    name: str
    root: Path
    manifest: dict[str, Any]
    instance: Any


def _load_register_callable(register_path: str):
    """Import and return a plugin registration callable from a manifest entry point."""
    module_name, function_name = register_path.split(":", 1)
    module = importlib.import_module(module_name)
    return getattr(module, function_name)


def discover_plugin_manifests() -> list[Path]:
    """Find plugin manifest files beneath a plugin root directory."""
    manifests: list[Path] = []

    if not PLUGIN_ROOT.exists():
        return manifests

    for plugin_toml in PLUGIN_ROOT.glob("community/*/plugin.toml"):
        manifests.append(plugin_toml)

    return sorted(manifests)


def load_enabled_plugins(*, refresh: bool = False) -> list[LoadedPlugin]:
    """Load all enabled plugins from discovered manifests.

    The set of installed plugins is effectively static for a running FUSE
    process. Cache the loaded plugin objects so hot paths such as project load,
    port-metadata lookup, validation, and export do not repeatedly re-read
    manifests, re-import modules, and re-instantiate plugin classes.
    """
    global _LOADED_PLUGINS_CACHE

    if _LOADED_PLUGINS_CACHE is not None and not refresh:
        return list(_LOADED_PLUGINS_CACHE)

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

    _LOADED_PLUGINS_CACHE = list(loaded)
    return list(_LOADED_PLUGINS_CACHE)


def get_plugin_by_id(plugin_id: str):
    """Return a loaded plugin instance by plugin identifier."""
    loaded_plugins = load_enabled_plugins()
    for plugin in loaded_plugins:
        instance_plugin_id = getattr(plugin.instance, "plugin_id", None)

        if plugin.plugin_id == plugin_id or instance_plugin_id == plugin_id:
            return plugin.instance

    loaded_ids = [
        f"{plugin.plugin_id} / {getattr(plugin.instance, 'plugin_id', '<no instance id>')}"
        for plugin in loaded_plugins
    ]

    raise KeyError(
        f"No enabled plugin with id '{plugin_id}'. "
        f"Loaded plugin ids: {loaded_ids}"
    )


def list_all_targets():
    """Return framework targets advertised by all loaded plugins."""
    global _TARGETS_CACHE

    if _TARGETS_CACHE is not None:
        return list(_TARGETS_CACHE)

    targets = []

    for plugin in load_enabled_plugins():
        instance = plugin.instance

        if hasattr(instance, "list_targets"):
            targets.extend(instance.list_targets())

    _TARGETS_CACHE = list(targets)
    return list(_TARGETS_CACHE)


def load_all_palette_items(plugin_id: str | None = None, target_id: str | None = None):
    """Load palette items for all framework targets associated with a plugin."""
    cache_key = (plugin_id, target_id)
    if cache_key in _PALETTE_ITEMS_CACHE:
        return list(_PALETTE_ITEMS_CACHE[cache_key])

    items = []

    for plugin in load_enabled_plugins():
        instance_plugin_id = getattr(plugin.instance, "plugin_id", plugin.plugin_id)

        if plugin_id is not None and plugin.plugin_id != plugin_id and instance_plugin_id != plugin_id:
            continue

        instance = plugin.instance

        if hasattr(instance, "load_palette_items"):
            items.extend(instance.load_palette_items(target_id=target_id))

    _PALETTE_ITEMS_CACHE[cache_key] = list(items)
    return list(items)


def load_item_details(plugin_id: str, item_id: str, target_id: str | None = None):
    """Load detailed palette metadata for one component item."""
    cache_key = (str(plugin_id or ""), str(item_id or ""), str(target_id) if target_id is not None else None)
    if cache_key in _ITEM_DETAILS_CACHE:
        return _ITEM_DETAILS_CACHE[cache_key]

    plugin = get_plugin_by_id(plugin_id)

    if not hasattr(plugin, "load_item_details"):
        raise KeyError(f"Plugin '{plugin_id}' does not provide item details.")

    details = plugin.load_item_details(item_id, target_id=target_id)
    _ITEM_DETAILS_CACHE[cache_key] = details
    return details
