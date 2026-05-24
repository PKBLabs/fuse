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
from dataclasses import dataclass
import json


MIME_COMPONENT = "application/x-fuse-component"
SCHEMA_VERSION = "0.1.0"


@dataclass
class ComponentDefinition:
    element: str
    name: str
    component_id: str | int | None = None
    plugin_id: str = "core"
    target_id: str = ""
    target_label: str = ""
    framework_version: str = ""
    is_subcomp: int = 0
    category: str = ""
    iface: str = ""
    icon_path: str = ""
    display_name_override: str = ""

    @property
    def display_name(self) -> str:
        if self.display_name_override:
            return self.display_name_override

        kind = "SubComponent" if self.is_subcomp else "Component"

        if self.element:
            return f"{self.element}.{self.name} ({kind})"

        return f"{self.name} ({kind})"

    def to_drag_text(self) -> str:
        return json.dumps(
            {
                "component_id": str(self.component_id or ""),
                "plugin_id": self.plugin_id or "core",
                "target_id": self.target_id or "",
                "target_label": self.target_label or "",
                "framework_version": self.framework_version or "",
                "element": self.element or "",
                "name": self.name or "",
                "is_subcomp": int(self.is_subcomp or 0),
                "category": self.category or "",
                "iface": self.iface or "",
                "icon_path": self.icon_path or "",
                "display_name_override": self.display_name_override or "",
            }
        )

    @staticmethod
    def from_drag_text(text: str) -> "ComponentDefinition":
        stripped = text.strip()

        if stripped.startswith("{"):
            data = json.loads(stripped)

            return ComponentDefinition(
                component_id=data.get("component_id") or None,
                plugin_id=data.get("plugin_id") or "core",
                target_id=data.get("target_id") or "",
                target_label=data.get("target_label") or "",
                framework_version=data.get("framework_version") or "",
                element=data.get("element") or "",
                name=data.get("name") or "",
                is_subcomp=int(data.get("is_subcomp") or 0),
                category=data.get("category") or "",
                iface=data.get("iface") or "",
                icon_path=data.get("icon_path") or "",
                display_name_override=data.get("display_name_override") or "",
            )

        parts = text.split("|")

        # Backward-compatible plugin-aware pipe format:
        # component_id | plugin_id | element | name | is_subcomp | category | iface | icon_path | display_name_override
        if len(parts) >= 9:
            (
                component_id_text,
                plugin_id,
                element,
                name,
                is_subcomp,
                category,
                iface,
                icon_path,
                display_name_override,
            ) = parts[:9]

            return ComponentDefinition(
                component_id=component_id_text or None,
                plugin_id=plugin_id or "core",
                target_id="",
                element=element,
                name=name,
                is_subcomp=int(is_subcomp or 0),
                category=category,
                iface=iface,
                icon_path=icon_path,
                display_name_override=display_name_override,
            )

        # Backward-compatible old SST-only format:
        # component_id | element | name | is_subcomp | category | iface
        old_parts = text.split("|", 5)
        while len(old_parts) < 6:
            old_parts.append("")

        component_id_text, element, name, is_subcomp, category, iface = old_parts

        return ComponentDefinition(
            component_id=component_id_text or None,
            plugin_id="sst",
            target_id="",
            element=element,
            name=name,
            is_subcomp=int(is_subcomp or 0),
            category=category,
            iface=iface,
        )


@dataclass
class ModelLink:
    """
    One point-to-point or bus-like link in the model.
    """

    link_id: int
    name: str
    latency: str
    source_node_id: int
    source_component_name: str
    source_port: str
    target_node_id: int
    target_component_name: str
    target_port: str
    link_type: str = "point_to_point"
