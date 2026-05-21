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


def initialize_database() -> None:
    initialize_core_database()

    with get_connection() as conn:
        initialize_sst_schema(conn)


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