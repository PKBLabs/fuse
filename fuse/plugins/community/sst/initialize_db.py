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
"""SST plugin database schema initialization.

The functions in this module create and migrate SQLite tables used to cache SST
framework versions, imported components, ports, parameters, statistics, and
subcomponent slots."""

from fuse.core.persistence.database import (
    get_connection,
    initialize_core_database,
)


def ensure_column(conn, table_name: str, column_name: str, ddl: str) -> None:
    """Add a column to an existing SQLite table when it is not already present."""
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")}

    if column_name not in columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {ddl}")


def ensure_sst_port_variable_columns(conn) -> None:
    """Ensure the SST port table contains variable-port metadata columns."""
    ensure_column(
        conn,
        "sst_ports",
        "is_variable",
        "is_variable INTEGER NOT NULL DEFAULT 0 CHECK (is_variable IN (0, 1))",
    )
    ensure_column(
        conn,
        "sst_ports",
        "base_name",
        "base_name TEXT NOT NULL DEFAULT ''",
    )
    ensure_column(
        conn,
        "sst_ports",
        "count_parameter",
        "count_parameter TEXT NOT NULL DEFAULT ''",
    )
    ensure_column(
        conn,
        "sst_ports",
        "default_count",
        "default_count INTEGER NOT NULL DEFAULT 1",
    )


def initialize_sst_schema(conn) -> None:
    """Create or migrate all SQLite tables required by the SST plugin."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_framework_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT 'sst-info',
            source_path TEXT NOT NULL DEFAULT '',
            sst_info_command TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(version, source_kind, source_path)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_info_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER,
            command TEXT NOT NULL,
            return_code INTEGER NOT NULL,
            stdout TEXT NOT NULL DEFAULT '',
            stderr TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE SET NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',

            UNIQUE(framework_version_id, name),

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_subcomp INTEGER NOT NULL DEFAULT 0 CHECK (is_subcomp IN (0, 1)),
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            functionality TEXT NOT NULL DEFAULT '',
            icon_path TEXT DEFAULT '',
            checkpointable INTEGER NOT NULL DEFAULT 0 CHECK (checkpointable IN (0, 1)),

            UNIQUE(framework_version_id, parent_id, name, is_subcomp),

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE,

            FOREIGN KEY (parent_id)
                REFERENCES sst_elements(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_subcomp_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE,

            FOREIGN KEY (parent_id)
                REFERENCES sst_components(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            default_val TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,
            parent_type TEXT NOT NULL CHECK (
                parent_type IN (
                    'sst_components',
                    'sst_statistics'
                )
            ),
            required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            units TEXT NOT NULL DEFAULT '',
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE,

            FOREIGN KEY (parent_id)
                REFERENCES sst_components(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_ports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,
            is_variable INTEGER NOT NULL DEFAULT 0 CHECK (is_variable IN (0, 1)),
            base_name TEXT NOT NULL DEFAULT '',
            count_parameter TEXT NOT NULL DEFAULT '',
            default_count INTEGER NOT NULL DEFAULT 1,

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE,

            FOREIGN KEY (parent_id)
                REFERENCES sst_components(id)
                ON DELETE CASCADE
        )
    """)

    ensure_sst_port_variable_columns(conn)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_component_catalog_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            framework_version_id INTEGER,
            base_version TEXT NOT NULL DEFAULT '',
            source_kind TEXT NOT NULL DEFAULT '',
            source_label TEXT NOT NULL DEFAULT '',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            catalog_path TEXT NOT NULL DEFAULT '',
            discovered_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(base_version, source_fingerprint),

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE SET NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_component_enablement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_id INTEGER NOT NULL,
            component_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),

            UNIQUE(source_id, component_key),

            FOREIGN KEY (source_id)
                REFERENCES sst_component_catalog_sources(id)
                ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_project_component_enablement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_key TEXT NOT NULL,
            framework_version_id INTEGER,
            base_version TEXT NOT NULL DEFAULT '',
            source_fingerprint TEXT NOT NULL DEFAULT '',
            component_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0 CHECK (enabled IN (0, 1)),
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(project_key, base_version, source_fingerprint, component_key),

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE SET NULL
        )
    """)


def initialize_database() -> None:
    """Initialize the core database and then ensure SST-specific tables exist."""
    initialize_core_database()

    with get_connection() as conn:
        initialize_sst_schema(conn)
        conn.commit()


def get_or_create_sst_framework_version(
    conn,
    version: str,
    label: str = "",
    source_kind: str = "sst-info",
    source_path: str = "",
    command: str = "",
    is_default: bool = False,
) -> int:
    """Return an SST framework-version row, creating it when necessary."""
    row = conn.execute(
        """
        SELECT id
        FROM sst_framework_versions
        WHERE version = ?
          AND source_kind = ?
          AND source_path = ?
        """,
        (version, source_kind, source_path),
    ).fetchone()

    if row is not None:
        framework_version_id = int(row["id"])

        conn.execute(
            """
            UPDATE sst_framework_versions
            SET label = COALESCE(NULLIF(?, ''), label),
                sst_info_command = COALESCE(NULLIF(?, ''), sst_info_command)
            WHERE id = ?
            """,
            (label, command, framework_version_id),
        )

        if is_default:
            conn.execute("UPDATE sst_framework_versions SET is_default = 0")
            conn.execute(
                "UPDATE sst_framework_versions SET is_default = 1 WHERE id = ?",
                (framework_version_id,),
            )

        return framework_version_id

    if is_default:
        conn.execute("UPDATE sst_framework_versions SET is_default = 0")

    cursor = conn.execute(
        """
        INSERT INTO sst_framework_versions (
            version,
            label,
            source_kind,
            source_path,
            sst_info_command,
            is_default
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            version,
            label or f"SST {version}",
            source_kind,
            source_path,
            command,
            1 if is_default else 0,
        ),
    )

    return int(cursor.lastrowid)


def get_default_sst_framework_version_id(conn) -> int | None:
    """Return the default SST framework-version database id."""
    row = conn.execute(
        """
        SELECT id
        FROM sst_framework_versions
        WHERE is_default = 1
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    if row is not None:
        return int(row["id"])

    row = conn.execute(
        """
        SELECT id
        FROM sst_framework_versions
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()

    return int(row["id"]) if row is not None else None


def save_sst_info_run(command, return_code, stdout, stderr, framework_version_id=None):
    """Record an sst-info execution result for traceability and diagnostics."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sst_info_runs (
                framework_version_id,
                command,
                return_code,
                stdout,
                stderr
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                framework_version_id,
                " ".join(command),
                return_code,
                stdout,
                stderr,
            ),
        )

        return cursor.lastrowid


if __name__ == "__main__":
    initialize_database()
    print("SST database schema initialized.")
