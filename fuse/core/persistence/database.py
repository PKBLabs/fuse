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
from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parents[2] / "app_data" / "app.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def initialize_core_database() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS plugins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                namespace TEXT NOT NULL,
                version TEXT NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, version)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS elements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT ''
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
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

                FOREIGN KEY (parent_id) REFERENCES elements(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS subcomp_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS parameters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                default_val TEXT NOT NULL DEFAULT '',
                parent_id INTEGER NOT NULL,
                parent_type TEXT NOT NULL CHECK (
                    parent_type IN (
                        'components',
                        'statistics'
                    )
                ),
                required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                units TEXT NOT NULL,
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS ports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                iface TEXT NOT NULL,
                parent_id INTEGER NOT NULL,

                FOREIGN KEY (parent_id) REFERENCES components(id)
                    ON DELETE CASCADE
                    ON UPDATE RESTRICT
            )
        """)

        ensure_component_icon_column(conn)


def ensure_component_icon_column(conn) -> None:
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(components)").fetchall()
    }

    if "icon_path" not in columns:
        conn.execute("""
            ALTER TABLE components
            ADD COLUMN icon_path TEXT DEFAULT ''
        """)