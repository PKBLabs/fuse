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
"""Composite component data structures and file-format helpers.

Composite components let users group an internal mini-model behind a reusable
external component-like boundary. This module owns the persisted definition,
external-to-internal port mappings, and conversion helpers used by the palette,
instance editor, project serializer, and composite import/export logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any
from uuid import uuid4


COMPOSITE_SCHEMA_VERSION = "0.1.0"
COMPOSITE_PLUGIN_ID = "core"
COMPOSITE_TARGET_ID = "fuse-composite"
COMPOSITE_CATEGORY = "Composite Components"
COMPOSITE_ELEMENT = "Composite Components"
COMPOSITE_FILE_KIND = "fuse.composite-component"


@dataclass
class CompositePortMapping:
    """Mapping from an external composite port to an internal component port.

    Only mappings with ``exposed`` set to true are displayed on composite
    instances and used when links cross the composite boundary.
    """
    external_port_name: str
    internal_node_id: int
    internal_component_name: str
    internal_port_name: str
    side: str = ""
    iface: str = ""
    description: str = ""
    exposed: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of the port mapping."""
        return {
            "external_port_name": self.external_port_name,
            "internal_node_id": int(self.internal_node_id),
            "internal_component_name": self.internal_component_name,
            "internal_port_name": self.internal_port_name,
            "side": self.side,
            "iface": self.iface,
            "description": self.description,
            "exposed": bool(self.exposed),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CompositePortMapping":
        """Build a port mapping from persisted project or composite-file data."""
        return CompositePortMapping(
            external_port_name=str(data.get("external_port_name") or ""),
            internal_node_id=int(data.get("internal_node_id") or 0),
            internal_component_name=str(data.get("internal_component_name") or ""),
            internal_port_name=str(data.get("internal_port_name") or ""),
            side=str(data.get("side") or ""),
            iface=str(data.get("iface") or ""),
            description=str(data.get("description") or ""),
            exposed=bool(data.get("exposed", True)),
        )


@dataclass
class CompositeComponentDefinition:
    """Reusable composite component template stored in the FUSE database.

    A definition contains metadata shown in the palette plus a normalized
    mini-model describing the internal components, links, attachments, and
    exposed boundary ports used when a composite instance is placed.
    """
    composite_id: str
    name: str
    description: str = ""
    icon_path: str = ""
    mini_model: dict[str, Any] = field(default_factory=dict)
    port_mappings: list[CompositePortMapping] = field(default_factory=list)
    schema_version: str = COMPOSITE_SCHEMA_VERSION
    created_at: str = ""
    updated_at: str = ""

    @staticmethod
    def make(
        name: str,
        description: str = "",
        icon_path: str = "",
        mini_model: dict[str, Any] | None = None,
        port_mappings: list[CompositePortMapping] | None = None,
        composite_id: str | None = None,
    ) -> "CompositeComponentDefinition":
        """Create a new composite definition with timestamps and optional id."""
        timestamp = datetime.now(timezone.utc).isoformat()
        return CompositeComponentDefinition(
            composite_id=composite_id or str(uuid4()),
            name=name,
            description=description,
            icon_path=icon_path,
            mini_model=dict(mini_model or {}),
            port_mappings=list(port_mappings or []),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation of this definition."""
        return {
            "composite_id": self.composite_id,
            "name": self.name,
            "description": self.description,
            "icon_path": self.icon_path,
            "mini_model": self.mini_model,
            "port_mappings": [mapping.to_dict() for mapping in self.port_mappings],
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "CompositeComponentDefinition":
        """Build a composite definition from saved project/database data."""
        return CompositeComponentDefinition(
            composite_id=str(data.get("composite_id") or ""),
            name=str(data.get("name") or ""),
            description=str(data.get("description") or ""),
            icon_path=str(data.get("icon_path") or ""),
            mini_model=dict(data.get("mini_model") or {}),
            port_mappings=[
                CompositePortMapping.from_dict(mapping)
                for mapping in data.get("port_mappings") or []
                if isinstance(mapping, dict)
            ],
            schema_version=str(data.get("schema_version") or COMPOSITE_SCHEMA_VERSION),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )

    def to_storage_values(self) -> dict[str, str]:
        """Return column values used by the composite definition database table."""
        return {
            "id": self.composite_id,
            "name": self.name,
            "description": self.description,
            "icon_path": self.icon_path,
            "mini_model_json": json.dumps(self.mini_model, sort_keys=True),
            "port_map_json": json.dumps(
                [mapping.to_dict() for mapping in self.port_mappings],
                sort_keys=True,
            ),
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_storage_row(row) -> "CompositeComponentDefinition":
        """Build a composite definition from a database result row."""
        mini_model = {}
        port_mappings = []

        try:
            loaded_model = json.loads(row["mini_model_json"] or "{}")
            if isinstance(loaded_model, dict):
                mini_model = loaded_model
        except (TypeError, json.JSONDecodeError):
            mini_model = {}

        try:
            loaded_ports = json.loads(row["port_map_json"] or "[]")
            if isinstance(loaded_ports, list):
                port_mappings = [
                    CompositePortMapping.from_dict(mapping)
                    for mapping in loaded_ports
                    if isinstance(mapping, dict)
                ]
        except (TypeError, json.JSONDecodeError):
            port_mappings = []

        return CompositeComponentDefinition(
            composite_id=str(row["id"] or ""),
            name=str(row["name"] or ""),
            description=str(row["description"] or ""),
            icon_path=str(row["icon_path"] or ""),
            mini_model=mini_model,
            port_mappings=port_mappings,
            schema_version=str(row["schema_version"] or COMPOSITE_SCHEMA_VERSION),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
