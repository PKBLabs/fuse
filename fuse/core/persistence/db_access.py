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
from fuse.core.persistence.database import initialize_core_database, get_connection
from fuse.core.plugin_runtime.manager import (
    list_all_targets,
    load_enabled_plugins,
    load_all_palette_items,
    load_item_details,
)
from fuse.core.model.models import ComponentDefinition


def ensure_database_ready(run_plugin_bootstrap: bool = False) -> None:
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


def load_framework_targets():
    return list_all_targets()


def load_component_definitions(
    plugin_id: str | None = None,
    target_id: str | None = None,
) -> list[ComponentDefinition]:
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
                category=item.category,
                iface="",
                icon_path=item.icon_path,
                display_name_override=item.display_name,
            )
        )

    return definitions


def load_port_names_for_component(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
) -> list[str]:
    details = load_item_details(plugin_id, component_id, target_id=target_id)
    return [connector.name for connector in details.connectors]


def get_component_details(
    plugin_id: str,
    component_id: str,
    target_id: str | None = None,
):
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
        "parameters": [
            {
                "name": prop.name,
                "description": prop.description,
                "default_val": prop.default_value,
                "required": prop.required,
            }
            for prop in details.properties
        ],
        "ports": [
            {
                "name": conn.name,
                "description": conn.description,
                "iface": conn.interface,
            }
            for conn in details.connectors
        ],
        "statistics": details.statistics,
        "subcomponent_slots": [],
    }
