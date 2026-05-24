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
from fuse.core.persistence.database import (
    get_connection,
    initialize_core_database,
)


def initialize_sst_schema(conn) -> None:
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

            FOREIGN KEY (framework_version_id)
                REFERENCES sst_framework_versions(id)
                ON DELETE CASCADE,

            FOREIGN KEY (parent_id)
                REFERENCES sst_components(id)
                ON DELETE CASCADE
        )
    """)


def initialize_database() -> None:
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
