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
from __future__ import annotations

from datetime import datetime, timezone

from fuse.core.model.composite import CompositeComponentDefinition
from fuse.core.persistence.database import get_connection, initialize_core_database


def current_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_composite_component_definition(
    definition: CompositeComponentDefinition,
) -> CompositeComponentDefinition:
    initialize_core_database()

    stored = CompositeComponentDefinition.from_dict(definition.to_dict())
    timestamp = current_timestamp()

    if not stored.created_at:
        stored.created_at = timestamp
    stored.updated_at = timestamp

    values = stored.to_storage_values()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO core_composite_components (
                id,
                name,
                description,
                icon_path,
                mini_model_json,
                port_map_json,
                schema_version,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                icon_path = excluded.icon_path,
                mini_model_json = excluded.mini_model_json,
                port_map_json = excluded.port_map_json,
                schema_version = excluded.schema_version,
                updated_at = excluded.updated_at
            """,
            (
                values["id"],
                values["name"],
                values["description"],
                values["icon_path"],
                values["mini_model_json"],
                values["port_map_json"],
                values["schema_version"],
                values["created_at"],
                values["updated_at"],
            ),
        )
        conn.commit()

    return stored


def list_composite_component_definitions() -> list[CompositeComponentDefinition]:
    initialize_core_database()

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                name,
                description,
                icon_path,
                mini_model_json,
                port_map_json,
                schema_version,
                created_at,
                updated_at
            FROM core_composite_components
            ORDER BY name COLLATE NOCASE, id
            """
        ).fetchall()

    return [CompositeComponentDefinition.from_storage_row(row) for row in rows]


def get_composite_component_definition(
    composite_id: str,
) -> CompositeComponentDefinition | None:
    initialize_core_database()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                name,
                description,
                icon_path,
                mini_model_json,
                port_map_json,
                schema_version,
                created_at,
                updated_at
            FROM core_composite_components
            WHERE id = ?
            """,
            (composite_id,),
        ).fetchone()

    if row is None:
        return None

    return CompositeComponentDefinition.from_storage_row(row)


def delete_composite_component_definition(composite_id: str) -> None:
    initialize_core_database()

    with get_connection() as conn:
        conn.execute(
            """
            DELETE FROM core_composite_components
            WHERE id = ?
            """,
            (composite_id,),
        )
        conn.commit()
