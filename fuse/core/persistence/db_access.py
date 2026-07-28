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
"""Read-side access helpers for framework and component metadata.

This module provides compatibility functions used by legacy UI paths while newer code increasingly routes simulator-specific data through plugin APIs."""

from fuse.core.persistence.database import initialize_core_database, get_connection
from fuse.core.plugin_runtime.manager import (
    clear_plugin_runtime_caches,
    list_all_targets,
    load_enabled_plugins,
    load_all_palette_items,
    load_item_details,
)
from fuse.core.model.composite import (
    COMPOSITE_CATEGORY,
    COMPOSITE_ELEMENT,
    COMPOSITE_PLUGIN_ID,
    COMPOSITE_TARGET_ID,
)
from fuse.core.model.models import ComponentDefinition
from fuse.core.model.subcomponents import mark_visual_subcomponent_connection_parameters_optional
from fuse.core.persistence.composite_components import (
    get_composite_component_definition,
    list_composite_component_definitions,
)


def ensure_database_ready(run_plugin_bootstrap: bool = False) -> None:
    """Initialize core and known plugin metadata schemas before reads."""
    initialize_core_database()

    plugins = load_enabled_plugins()

    with get_connection() as conn:
        for plugin in plugins:
            instance = plugin.instance
            version = plugin.manifest.get("plugin", {}).get("version", "")

            conn.execute("""
                INSERT INTO core_plugins (
                    id,
                    name,
                    version,
                    enabled
                )
                VALUES (?, ?, ?, 1)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    version = excluded.version,
                    enabled = excluded.enabled
            """, (plugin.plugin_id, plugin.name, version))

            if hasattr(instance, "initialize_database"):
                instance.initialize_database(conn)

        conn.commit()

    if run_plugin_bootstrap:
        for plugin in plugins:
            instance = plugin.instance

            if hasattr(instance, "bootstrap_database"):
                instance.bootstrap_database()

    # Database initialization and plugin bootstrap can add or migrate targets,
    # palette rows, and component details. Drop metadata caches so subsequent UI
    # reads see the refreshed catalog while still keeping plugin objects loaded.
    clear_plugin_runtime_caches()


def load_framework_targets():
    """Return available framework targets for the component palette and project settings UI."""
    return list_all_targets()


def load_component_definitions(
    plugin_id: str | None = None,
    target_id: str | None = None,
) -> list[ComponentDefinition]:
    """Load component definitions for the default/selected framework target."""
    definitions = []

    for item in load_all_palette_items(plugin_id=plugin_id, target_id=target_id):
        definitions.append(
            ComponentDefinition(
                plugin_id=item.plugin_id,
                target_id=item.target_id,
                target_label=item.target_label,
                framework_version=item.framework_version,
                component_id=item.item_id,
                element=getattr(item, "element_name", "") or item.category,
                name=item.type_name,
                is_subcomp=1 if getattr(item, "raw_kind", "") == "SubComponent" else 0,
                category=item.category,
                functionality=getattr(item, "functionality", "") or "",
                description=getattr(item, "description", "") or "",
                iface=getattr(item, "iface", "") or "",
                icon_path=item.icon_path,
                display_name_override=item.display_name,
            )
        )

    definitions.extend(load_composite_component_definitions())

    return definitions


def load_composite_component_definitions() -> list[ComponentDefinition]:
    """Load reusable composite component definitions as palette-ready component definitions."""
    definitions = []

    for composite in list_composite_component_definitions():
        definitions.append(
            ComponentDefinition(
                plugin_id=COMPOSITE_PLUGIN_ID,
                target_id=COMPOSITE_TARGET_ID,
                target_label="FUSE Composite Components",
                framework_version=composite.schema_version,
                component_id=composite.composite_id,
                element=COMPOSITE_ELEMENT,
                name=composite.name,
                is_subcomp=0,
                category=COMPOSITE_CATEGORY,
                functionality="Reusable mini-model",
                description=composite.description,
                icon_path=composite.icon_path,
                display_name_override=f"{composite.name} (Composite)",
                is_composite=1,
                composite_id=composite.composite_id,
            )
        )

    return definitions


def load_port_metadata_for_component(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
) -> list[dict]:
    """Return port metadata for a component definition."""
    if is_composite_component_request(plugin_id, component_id, target_id):
        composite = get_composite_component_definition(str(component_id or ""))

        if composite is None:
            return []

        return [
            {
                "name": mapping.external_port_name,
                "description": mapping.description,
                "iface": mapping.iface,
                "is_variable": False,
                "base_name": mapping.external_port_name,
                "count_parameter": "",
                "default_count": 1,
            }
            for mapping in composite.port_mappings
            if bool(getattr(mapping, "exposed", True))
        ]

    details = load_item_details(plugin_id, component_id, target_id=target_id)

    return [
        {
            "name": connector.name,
            "description": connector.description,
            "iface": connector.interface,
            "is_variable": bool(getattr(connector, "is_variable", False)),
            "base_name": getattr(connector, "base_name", "") or connector.name,
            "count_parameter": getattr(connector, "count_parameter", "") or "",
            "default_count": int(getattr(connector, "default_count", 1) or 1),
        }
        for connector in details.connectors
    ]

def load_port_names_for_component(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
) -> list[str]:
    """Return only port names for a component definition."""
    return [port["name"] for port in load_port_metadata_for_component(plugin_id, component_id, target_id)]

def load_subcomp_connector_metadata_for_component(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
) -> list[dict]:
    """Return subcomponent connector metadata for a component definition."""
    if is_composite_component_request(plugin_id, component_id, target_id):
        return []

    details = load_item_details(plugin_id, component_id, target_id=target_id)

    return [
        {
            "name": connector.name,
            "role": getattr(connector, "role", ""),
            "description": getattr(connector, "description", ""),
            "required_interface": getattr(connector, "required_interface", ""),
            "provided_interface": getattr(connector, "provided_interface", ""),
            "interface": getattr(connector, "interface", ""),
            "iface": getattr(connector, "interface", ""),
            "visual_only": bool(getattr(connector, "visual_only", False)),
            "allow_multiple": bool(getattr(connector, "allow_multiple", False)),
            "plugin_metadata": dict(getattr(connector, "plugin_metadata", {}) or {}),
        }
        for connector in getattr(details, "subcomp_connectors", [])
    ]

def is_composite_component_request(
    plugin_id: str,
    component_id: str | int | None,
    target_id: str | None = None,
) -> bool:
    """Return whether a framework/component request targets a stored composite definition."""
    return (
        (plugin_id or "") == COMPOSITE_PLUGIN_ID
        and (target_id or COMPOSITE_TARGET_ID) == COMPOSITE_TARGET_ID
        and bool(component_id)
    )


def get_component_details(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
):
    """Return detailed metadata for a component or composite definition."""
    if is_composite_component_request(plugin_id, component_id, target_id):
        composite = get_composite_component_definition(str(component_id or ""))

        if composite is None:
            return {}

        return {
            "component": {
                "name": composite.name,
                "description": composite.description,
                "category": COMPOSITE_CATEGORY,
                "icon_path": composite.icon_path,
                "target_id": COMPOSITE_TARGET_ID,
                "target_label": "FUSE Composite Components",
                "framework_version": composite.schema_version,
                "is_composite": 1,
                "composite_id": composite.composite_id,
            },
            "parameters": [],
            "ports": load_port_metadata_for_component(plugin_id, component_id, target_id),
            "subcomp_connectors": [],
            "statistics": [],
            "subcomponent_slots": [],
        }

    details = load_item_details(plugin_id, component_id, target_id=target_id)

    return {
        "component": {
            "name": details.palette_item.type_name,
            "description": details.palette_item.description,
            "category": details.palette_item.category,
            "icon_path": details.palette_item.icon_path,
            "target_id": details.palette_item.target_id,
            "target_label": details.palette_item.target_label,
            "framework_version": details.palette_item.framework_version,
        },
        "parameters": mark_visual_subcomponent_connection_parameters_optional(
            [
                {
                    "name": prop.name,
                    "description": prop.description,
                    "default_val": prop.default_value,
                    "required": prop.required,
                }
                for prop in details.properties
            ],
            component_is_subcomponent=bool(getattr(details.palette_item, "raw_kind", "") == "SubComponent"),
        ),
        "ports": [
            {
                "name": conn.name,
                "description": conn.description,
                "iface": conn.interface,
                "is_variable": bool(getattr(conn, "is_variable", False)),
                "base_name": getattr(conn, "base_name", "") or conn.name,
                "count_parameter": getattr(conn, "count_parameter", "") or "",
                "default_count": int(getattr(conn, "default_count", 1) or 1),
            }
            for conn in details.connectors
        ],
        "subcomp_connectors": [
            {
                "name": conn.name,
                "role": getattr(conn, "role", ""),
                "description": getattr(conn, "description", ""),
                "required_interface": getattr(conn, "required_interface", ""),
                "provided_interface": getattr(conn, "provided_interface", ""),
                "interface": getattr(conn, "interface", ""),
                "iface": getattr(conn, "interface", ""),
            }
            for conn in getattr(details, "subcomp_connectors", [])
        ],
        "statistics": details.statistics,
        "subcomponent_slots": [],
    }
