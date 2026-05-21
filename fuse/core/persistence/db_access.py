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
from typing import Optional

from fuse.core.model.models import ComponentDefinition
from fuse.core.persistence.database import (
    get_connection,
    initialize_core_database,
    rows_to_dicts,
)
from fuse.core.plugin_runtime.manager import load_enabled_plugins


def ensure_database_ready() -> None:
    initialize_core_database()

    plugins = load_enabled_plugins()

    with get_connection() as conn:
        for plugin in plugins:
            instance = plugin.instance

            if hasattr(instance, "initialize_database"):
                instance.initialize_database(conn)


def get_all_elements():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, name, description
            FROM elements
            ORDER BY name
        """).fetchall()

    return rows_to_dicts(rows)


def get_all_components_for_element(element_name):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM components c
            JOIN elements e ON c.parent_id = e.id
            WHERE e.name = ?
            ORDER BY c.is_subcomp, c.name
        """, (element_name,)).fetchall()

    return rows_to_dicts(rows)


def get_parameters_for_component(component_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM parameters
            WHERE parent_id = ?
              AND parent_type = 'components'
            ORDER BY name
        """, (component_id,)).fetchall()

    return rows_to_dicts(rows)


def get_ports_for_component(component_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM ports
            WHERE parent_id = ?
            ORDER BY name
        """, (component_id,)).fetchall()

    return rows_to_dicts(rows)


def get_statistics_for_component(component_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM statistics
            WHERE parent_id = ?
            ORDER BY name
        """, (component_id,)).fetchall()

    return rows_to_dicts(rows)


def get_parameters_for_statistics(statistic_ids):
    if not statistic_ids:
        return {}

    placeholders = ", ".join("?" for _ in statistic_ids)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM parameters
            WHERE parent_type = 'statistics'
              AND parent_id IN ({placeholders})
            ORDER BY parent_id, name
            """,
            statistic_ids,
        ).fetchall()

    grouped = {}

    for row in rows:
        parameter = dict(row)
        grouped.setdefault(parameter["parent_id"], []).append(parameter)

    return grouped


def get_subcomponent_slots_for_component(component_id):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM subcomp_slots
            WHERE parent_id = ?
            ORDER BY name
        """, (component_id,)).fetchall()

    return rows_to_dicts(rows)


def get_component_details(component_id):
    with get_connection() as conn:
        component = conn.execute("""
            SELECT c.*, e.name AS element_name
            FROM components c
            JOIN elements e ON c.parent_id = e.id
            WHERE c.id = ?
        """, (component_id,)).fetchone()

    if component is None:
        return None

    statistics = get_statistics_for_component(component_id)
    statistic_ids = [stat["id"] for stat in statistics]
    params_by_stat_id = get_parameters_for_statistics(statistic_ids)

    for statistic in statistics:
        statistic["parameters"] = params_by_stat_id.get(statistic["id"], [])

    return {
        "component": dict(component),
        "parameters": get_parameters_for_component(component_id),
        "ports": get_ports_for_component(component_id),
        "statistics": statistics,
        "subcomponent_slots": get_subcomponent_slots_for_component(component_id),
    }


def load_component_definitions() -> list[ComponentDefinition]:
    try:
        definitions: list[ComponentDefinition] = []
        elements = get_all_elements()

        for element in elements:
            element_name = element["name"]
            components = get_all_components_for_element(element_name)

            for component in components:
                definitions.append(
                    ComponentDefinition(
                        component_id=component.get("id"),
                        element=element_name,
                        name=component.get("name", ""),
                        is_subcomp=int(component.get("is_subcomp", 0)),
                        category=component.get("category", ""),
                        iface=component.get("iface", ""),
                        icon_path=component.get("icon_path", ""),
                    )
                )

        return definitions

    except Exception as exc:
        print(f"Failed to load components from database: {exc}")
        return []


def load_port_names_for_component(component_id: Optional[int]) -> list[str]:
    if component_id is None:
        return []

    try:
        ports = get_ports_for_component(component_id)
        return [port["name"] for port in ports]
    except Exception as exc:
        print(f"Failed to load ports for component {component_id}: {exc}")
        return []