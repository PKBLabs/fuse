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
import os
import sqlite3


_DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "app_data" / "app.db"

# Keep DB_PATH for compatibility, but do not rely on it inside get_connection().
DB_PATH = _DEFAULT_DB_PATH


def get_database_path() -> Path:
    return Path(
        os.environ.get("FUSE_DB_PATH", str(_DEFAULT_DB_PATH))
    ).expanduser()


def get_connection():
    db_path = get_database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def rows_to_dicts(rows):
    return [dict(row) for row in rows]


def initialize_core_database() -> None:
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS core_plugins (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS core_schema_migrations (
                namespace TEXT NOT NULL,
                version TEXT NOT NULL,
                applied_at TEXT DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (namespace, version)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS core_composite_components (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                icon_path TEXT NOT NULL DEFAULT '',
                mini_model_json TEXT NOT NULL,
                port_map_json TEXT NOT NULL DEFAULT '[]',
                schema_version TEXT NOT NULL DEFAULT '0.1.0',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()