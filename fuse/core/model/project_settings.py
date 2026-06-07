# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Project-level framework, target, and toolchain settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolchainSettings:
    """Project-specific execution/discovery settings for a plugin toolchain.

    The intent is to store enough information for FUSE to find/query the
    framework installation used by this project without storing secrets.
    Passwords, private keys, and passphrases must never be written here.
    """

    backend: str = "local"  # local, ssh, file, container in the future
    tool_paths: dict[str, str] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)

    # SSH settings. Auth should normally use ~/.ssh/config or ssh-agent.
    host: str = ""
    port: int = 22
    username: str = ""
    host_alias: str = ""
    auth_method: str = "ssh-agent"
    remote_setup_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "toolPaths": dict(self.tool_paths),
            "environment": dict(self.environment),
            "options": dict(self.options),
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "hostAlias": self.host_alias,
            "authMethod": self.auth_method,
            "remoteSetupCommand": self.remote_setup_command,
        }

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "ToolchainSettings":
        data = data or {}

        return ToolchainSettings(
            backend=data.get("backend", "local") or "local",
            tool_paths=dict(data.get("toolPaths", data.get("tool_paths", {})) or {}),
            environment=dict(data.get("environment", {}) or {}),
            options=dict(data.get("options", {}) or {}),
            host=data.get("host", "") or "",
            port=int(data.get("port", 22) or 22),
            username=data.get("username", "") or "",
            host_alias=data.get("hostAlias", data.get("host_alias", "")) or "",
            auth_method=data.get("authMethod", data.get("auth_method", "ssh-agent")) or "ssh-agent",
            remote_setup_command=data.get(
                "remoteSetupCommand",
                data.get("remote_setup_command", ""),
            ) or "",
        )


@dataclass
class PluginProjectSettings:
    """Project settings for one simulator plugin, including selected target and toolchain details."""
    plugin_id: str
    enabled: bool = False
    target_id: str = ""
    target_label: str = ""
    framework_version: str = ""
    toolchain: ToolchainSettings = field(default_factory=ToolchainSettings)
    options: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "targetId": self.target_id,
            "targetLabel": self.target_label,
            "frameworkVersion": self.framework_version,
            "toolchain": self.toolchain.to_dict(),
            "options": dict(self.options),
        }

    @staticmethod
    def from_dict(plugin_id: str, data: dict[str, Any] | None) -> "PluginProjectSettings":
        data = data or {}

        # Compatibility with the earlier flat proposal where toolchain fields
        # lived directly inside pluginSettings.<plugin>.
        toolchain_data = data.get("toolchain") or {
            "backend": data.get("executionBackend", data.get("backend", "local")),
            "toolPaths": {
                "sstInfo": data.get("sstInfoPath", ""),
                "sst": data.get("sstExecutablePath", ""),
                "gem5Binary": data.get("gem5Binary", ""),
                "gem5Root": data.get("gem5Root", ""),
            },
            "host": data.get("host", ""),
            "port": data.get("port", 22),
            "username": data.get("username", ""),
            "remoteSetupCommand": data.get("remoteSetupCommand", ""),
        }

        return PluginProjectSettings(
            plugin_id=plugin_id,
            enabled=bool(data.get("enabled", False)),
            target_id=str(data.get("targetId", data.get("target_id", "")) or ""),
            target_label=data.get("targetLabel", data.get("target_label", "")) or "",
            framework_version=data.get("frameworkVersion", data.get("framework_version", "")) or "",
            toolchain=ToolchainSettings.from_dict(toolchain_data),
            options=dict(data.get("options", {}) or {}),
        )


@dataclass
class ProjectSettings:
    """Aggregate project settings for all enabled simulator plugins."""
    project_name: str = "Untitled FUSE Project"
    active_plugin_id: str = ""
    preferred_component_sorting_mode: str = "Alphabetical"
    preferred_component_grouping_mode: str = "Element"
    auto_expand_all_component_tree: bool = False
    component_catalog_expanded: bool = False
    plugins: dict[str, PluginProjectSettings] = field(default_factory=dict)

    def active_plugin_settings(self) -> PluginProjectSettings | None:
        if not self.active_plugin_id:
            return None
        return self.plugins.get(self.active_plugin_id)

    def plugin_settings(self, plugin_id: str) -> PluginProjectSettings:
        if plugin_id not in self.plugins:
            self.plugins[plugin_id] = PluginProjectSettings(plugin_id=plugin_id)
        return self.plugins[plugin_id]

    def to_dict(self) -> dict[str, Any]:
        return {
            "projectName": self.project_name,
            "activePluginId": self.active_plugin_id,
            "preferredComponentSortingMode": self.preferred_component_sorting_mode,
            "preferredComponentGroupingMode": self.preferred_component_grouping_mode,
            "autoExpandAllComponentTree": self.auto_expand_all_component_tree,
            "componentCatalogExpanded": self.component_catalog_expanded,
            "plugins": {
                plugin_id: settings.to_dict()
                for plugin_id, settings in self.plugins.items()
            },
        }

    @staticmethod
    def from_dict(data: dict[str, Any] | None) -> "ProjectSettings":
        data = data or {}

        plugins_data = data.get("plugins", {}) or {}
        plugins = {
            plugin_id: PluginProjectSettings.from_dict(plugin_id, plugin_data)
            for plugin_id, plugin_data in plugins_data.items()
        }

        return ProjectSettings(
            project_name=data.get("projectName", data.get("project_name", "Untitled FUSE Project"))
            or "Untitled FUSE Project",
            active_plugin_id=data.get("activePluginId", data.get("active_plugin_id", "")) or "",
            preferred_component_sorting_mode=data.get(
                "preferredComponentSortingMode",
                data.get("preferred_component_sorting_mode", "Alphabetical"),
            ) or "Alphabetical",
            preferred_component_grouping_mode=data.get(
                "preferredComponentGroupingMode",
                data.get("preferred_component_grouping_mode", "Element"),
            ) or "Element",
            auto_expand_all_component_tree=bool(
                data.get(
                    "autoExpandAllComponentTree",
                    data.get("auto_expand_all_component_tree", False),
                )
            ),
            component_catalog_expanded=bool(
                data.get(
                    "componentCatalogExpanded",
                    data.get("component_catalog_expanded", False),
                )
            ),
            plugins=plugins,
        )

    @staticmethod
    def from_project_dict(project: dict[str, Any]) -> "ProjectSettings":
        if "projectSettings" in project:
            return ProjectSettings.from_dict(project.get("projectSettings"))

        # Compatibility with existing .fse files that only had activeTarget.
        active_target = project.get("activeTarget", {}) or {}
        plugin_id = active_target.get("pluginId", "") or ""
        target_id = active_target.get("targetId", "") or ""

        settings = ProjectSettings(
            project_name=(project.get("project", {}) or {}).get("name", "Untitled FUSE Project"),
            active_plugin_id=plugin_id,
        )

        if plugin_id:
            settings.plugins[plugin_id] = PluginProjectSettings(
                plugin_id=plugin_id,
                enabled=True,
                target_id=target_id,
            )

        return settings
