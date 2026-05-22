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
from typing import Optional

MIME_COMPONENT = "application/x-fuse-component"
SCHEMA_VERSION = "0.1.0"

@dataclass
class ComponentDefinition:
    element: str
    name: str
    component_id: str | int | None = None
    plugin_id: str = "core"
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
        return "|".join(
            [
                str(self.component_id or ""),
                self.plugin_id or "core",
                self.element or "",
                self.name or "",
                str(self.is_subcomp),
                self.category or "",
                self.iface or "",
                self.icon_path or "",
                self.display_name_override or "",
            ]
        )

    @staticmethod
    def from_drag_text(text: str) -> "ComponentDefinition":
        parts = text.split("|")

        # New plugin-aware format:
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
                element=element,
                name=name,
                is_subcomp=int(is_subcomp or 0),
                category=category,
                iface=iface,
                icon_path=icon_path,
                display_name_override=display_name_override,
            )

        # Backward-compatible old format:
        # component_id | element | name | is_subcomp | category | iface
        old_parts = text.split("|", 5)
        while len(old_parts) < 6:
            old_parts.append("")

        component_id_text, element, name, is_subcomp, category, iface = old_parts

        return ComponentDefinition(
            component_id=component_id_text or None,
            plugin_id="sst",
            element=element,
            name=name,
            is_subcomp=int(is_subcomp or 0),
            category=category,
            iface=iface,
        )

@dataclass
class ModelLink:
    """
    One SST-style link in the model.

    This is separate from the visual line. Later this should be saved to SQLite
    and eventually exported into an SST Python config.
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
