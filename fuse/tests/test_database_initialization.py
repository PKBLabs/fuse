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
def test_database_initialization_creates_core_and_plugin_tables():
    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready

    ensure_database_ready(run_plugin_bootstrap=False)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        ).fetchall()

    table_names = {row["name"] for row in rows}

    assert "core_plugins" in table_names
    assert "core_schema_migrations" in table_names

    assert "sst_info_runs" in table_names
    assert "sst_elements" in table_names
    assert "sst_components" in table_names
    assert "sst_ports" in table_names
    assert "sst_parameters" in table_names
    assert "sst_statistics" in table_names
    assert "sst_subcomp_slots" in table_names


def test_database_registers_plugins():
    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready

    ensure_database_ready(run_plugin_bootstrap=False)

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, enabled
            FROM core_plugins
            ORDER BY id
            """
        ).fetchall()

    plugins = {row["id"]: dict(row) for row in rows}

    assert "sst" in plugins
    assert "gem5" in plugins
    assert plugins["sst"]["enabled"] == 1