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
        CREATE TABLE IF NOT EXISTS sst_info_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            command TEXT NOT NULL,
            return_code INTEGER NOT NULL,
            stdout TEXT NOT NULL DEFAULT '',
            stderr TEXT NOT NULL DEFAULT '',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT ''
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_components (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_subcomp INTEGER NOT NULL DEFAULT 0 CHECK (is_subcomp IN (0, 1)),
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,
            category TEXT NOT NULL DEFAULT '',
            functionality TEXT NOT NULL DEFAULT '',
            icon_path TEXT DEFAULT '',
            checkpointable INTEGER NOT NULL DEFAULT 0 CHECK (checkpointable IN (0, 1)),

            UNIQUE(parent_id, name, is_subcomp),

            FOREIGN KEY (parent_id) REFERENCES sst_elements(id)
                ON DELETE CASCADE
                ON UPDATE RESTRICT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_subcomp_slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            iface TEXT NOT NULL,
            parent_id INTEGER NOT NULL,

            FOREIGN KEY (parent_id) REFERENCES sst_components(id)
                ON DELETE CASCADE
                ON UPDATE RESTRICT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_parameters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            units TEXT NOT NULL DEFAULT '',
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,

            FOREIGN KEY (parent_id) REFERENCES sst_components(id)
                ON DELETE CASCADE
                ON UPDATE RESTRICT
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS sst_ports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            iface TEXT NOT NULL DEFAULT '',
            parent_id INTEGER NOT NULL,

            FOREIGN KEY (parent_id) REFERENCES sst_components(id)
                ON DELETE CASCADE
                ON UPDATE RESTRICT
        )
    """)


def initialize_database() -> None:
    initialize_core_database()

    with get_connection() as conn:
        initialize_sst_schema(conn)
        conn.commit()


def save_sst_info_run(command, return_code, stdout, stderr):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sst_info_runs (
                command,
                return_code,
                stdout,
                stderr
            )
            VALUES (?, ?, ?, ?)
            """,
            (
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