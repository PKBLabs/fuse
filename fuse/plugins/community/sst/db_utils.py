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
"""Database query helpers for SST metadata.

The SST plugin stores imported sst-info metadata in SQLite tables. This module
centralizes read-only query helpers used by palette loading, details panels,
compatibility checks, exporters, and migration code."""

from fuse.core.persistence.database import get_connection, rows_to_dicts


SST_COMPONENT_PARENT_TYPE = "sst_components"
SST_STATISTIC_PARENT_TYPE = "sst_statistics"


def get_default_framework_version_id():
    """Return the default imported SST framework-version id."""
    with get_connection() as conn:
        row = conn.execute("""
            SELECT id
            FROM sst_framework_versions
            WHERE is_default = 1
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

        if row is not None:
            return int(row["id"])

        row = conn.execute("""
            SELECT id
            FROM sst_framework_versions
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

    return int(row["id"]) if row is not None else None


def resolve_framework_version_id(framework_version_id=None):
    """Resolve an explicit or default SST framework-version id."""
    if framework_version_id in (None, ""):
        return get_default_framework_version_id()

    return int(framework_version_id)


def get_framework_versions():
    """Return imported SST framework versions ordered for display."""
    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM sst_framework_versions
            ORDER BY is_default DESC, version DESC, id DESC
        """).fetchall()

    return rows_to_dicts(rows)


def get_all_elements(framework_version_id=None):
    """Return all SST elements for a framework version."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT id, framework_version_id, name, description
            FROM sst_elements
            WHERE framework_version_id = ?
            ORDER BY name
        """, (framework_version_id,)).fetchall()

    return rows_to_dicts(rows)


def get_element_by_name(element_name, framework_version_id=None):
    """Look up an SST element by name within a framework version."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return None

    with get_connection() as conn:
        row = conn.execute("""
            SELECT id, framework_version_id, name, description
            FROM sst_elements
            WHERE framework_version_id = ?
              AND name = ?
        """, (framework_version_id, element_name)).fetchone()

    return dict(row) if row is not None else None


def get_component_id(component_name, element_name=None, is_subcomp=None, framework_version_id=None):
    """Return the database id for an SST component or subcomponent."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return None

    query = """
        SELECT c.id
        FROM sst_components c
        JOIN sst_elements e ON c.parent_id = e.id
        WHERE c.framework_version_id = ?
          AND e.framework_version_id = ?
          AND c.name = ?
    """
    params = [framework_version_id, framework_version_id, component_name]

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


def get_all_components_for_element(element_name, framework_version_id=None):
    """Return all components and subcomponents associated with an SST element."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM sst_components c
            JOIN sst_elements e ON c.parent_id = e.id
            WHERE c.framework_version_id = ?
              AND e.framework_version_id = ?
              AND e.name = ?
            ORDER BY c.is_subcomp, c.name
        """, (framework_version_id, framework_version_id, element_name)).fetchall()

    return rows_to_dicts(rows)


def get_components_for_element(element_name, framework_version_id=None):
    """Return non-subcomponent SST components for an element."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM sst_components c
            JOIN sst_elements e ON c.parent_id = e.id
            WHERE c.framework_version_id = ?
              AND e.framework_version_id = ?
              AND e.name = ?
              AND c.is_subcomp = 0
            ORDER BY c.name
        """, (framework_version_id, framework_version_id, element_name)).fetchall()

    return rows_to_dicts(rows)


def get_subcomponents_for_element(element_name, framework_version_id=None):
    """Return SST subcomponents for an element."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT c.*
            FROM sst_components c
            JOIN sst_elements e ON c.parent_id = e.id
            WHERE c.framework_version_id = ?
              AND e.framework_version_id = ?
              AND e.name = ?
              AND c.is_subcomp = 1
            ORDER BY c.name
        """, (framework_version_id, framework_version_id, element_name)).fetchall()

    return rows_to_dicts(rows)


def get_parameters_for_component(component_id, framework_version_id=None):
    """Return parameter metadata attached to an SST component."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM sst_parameters
            WHERE framework_version_id = ?
              AND parent_id = ?
              AND parent_type = ?
            ORDER BY name
        """, (framework_version_id, component_id, SST_COMPONENT_PARENT_TYPE)).fetchall()

    return rows_to_dicts(rows)


def get_ports_for_component(component_id, framework_version_id=None):
    """Return port metadata attached to an SST component."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM sst_ports
            WHERE framework_version_id = ?
              AND parent_id = ?
            ORDER BY name
        """, (framework_version_id, component_id)).fetchall()

    return rows_to_dicts(rows)


def get_statistics_for_component(component_id, framework_version_id=None):
    """Return statistic metadata attached to an SST component."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM sst_statistics
            WHERE framework_version_id = ?
              AND parent_id = ?
            ORDER BY name
        """, (framework_version_id, component_id)).fetchall()

    return rows_to_dicts(rows)


def get_parameters_for_statistics(statistic_ids, framework_version_id=None):
    """Return parameter metadata attached to SST statistic rows."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None or not statistic_ids:
        return {}

    placeholders = ", ".join("?" for _ in statistic_ids)

    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM sst_parameters
            WHERE framework_version_id = ?
              AND parent_type = ?
              AND parent_id IN ({placeholders})
            ORDER BY parent_id, name
            """,
            [framework_version_id, SST_STATISTIC_PARENT_TYPE, *statistic_ids],
        ).fetchall()

    grouped = {}

    for row in rows:
        parameter = dict(row)
        grouped.setdefault(parameter["parent_id"], []).append(parameter)

    return grouped


def get_subcomponent_slots_for_component(component_id, framework_version_id=None):
    """Return subcomponent-slot metadata attached to an SST component."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    if framework_version_id is None:
        return []

    with get_connection() as conn:
        rows = conn.execute("""
            SELECT *
            FROM sst_subcomp_slots
            WHERE framework_version_id = ?
              AND parent_id = ?
            ORDER BY name
        """, (framework_version_id, component_id)).fetchall()

    return rows_to_dicts(rows)


def get_component_details(component_id, framework_version_id=None):
    """Return a complete details dictionary for an SST component database id."""
    framework_version_id = resolve_framework_version_id(framework_version_id)

    query = """
        SELECT c.*, e.name AS element_name
        FROM sst_components c
        JOIN sst_elements e ON c.parent_id = e.id
        WHERE c.id = ?
    """
    params = [component_id]

    if framework_version_id is not None:
        query += " AND c.framework_version_id = ? AND e.framework_version_id = ?"
        params.extend([framework_version_id, framework_version_id])

    with get_connection() as conn:
        component = conn.execute(query, params).fetchone()

    if component is None:
        return None

    component_dict = dict(component)
    resolved_version_id = int(component_dict["framework_version_id"])

    statistics = get_statistics_for_component(component_id, resolved_version_id)
    statistic_ids = [stat["id"] for stat in statistics]
    params_by_stat_id = get_parameters_for_statistics(statistic_ids, resolved_version_id)

    for statistic in statistics:
        statistic["parameters"] = params_by_stat_id.get(statistic["id"], [])

    return {
        "component": component_dict,
        "parameters": get_parameters_for_component(component_id, resolved_version_id),
        "ports": get_ports_for_component(component_id, resolved_version_id),
        "subcomp_slots": get_subcomponent_slots_for_component(component_id, resolved_version_id),
        "statistics": statistics,
    }
