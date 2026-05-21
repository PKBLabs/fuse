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
from fuse.core.persistence.database import get_connection, rows_to_dicts


def get_all_elements():
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, name, description
            FROM elements
            ORDER BY name
        """).fetchall()

    return rows_to_dicts(rows)


def get_element_by_name(element_name):
    with get_connection() as conn:
        row = conn.execute("""
            SELECT id, name, description
            FROM elements
            WHERE name = ?
        """, (element_name,)).fetchone()

    return dict(row) if row is not None else None


def get_component_id(component_name, element_name=None, is_subcomp=None):
    query = """
        SELECT c.id
        FROM components c
        JOIN elements e ON c.parent_id = e.id
        WHERE c.name = ?
    """
    params = [component_name]

    if element_name is not None:
        query += " AND e.name = ?"
        params.append(element_name)

    if is_subcomp is not None:
        query += " AND c.is_subcomp = ?"
        params.append(1 if is_subcomp else 0)

    query += " ORDER BY c.id LIMIT 1"

    with get_connection() as conn:
        row = conn.execute(query, params).fetchone()

    return int(row["id"]) if row is not None else None


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


def get_components_for_element(element_name):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM components c
            JOIN elements e ON c.parent_id = e.id
            WHERE e.name = ?
              AND c.is_subcomp = 0
            ORDER BY c.name
        """, (element_name,)).fetchall()

    return rows_to_dicts(rows)


def get_subcomponents_for_element(element_name):
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM components c
            JOIN elements e ON c.parent_id = e.id
            WHERE e.name = ?
              AND c.is_subcomp = 1
            ORDER BY c.name
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
        "subcomp_slots": get_subcomponent_slots_for_component(component_id),
        "statistics": statistics,
    }