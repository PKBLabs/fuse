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
def test_sst_schema_tables_are_created():
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

    tables = {row["name"] for row in rows}

    expected_tables = {
        "sst_info_runs",
        "sst_elements",
        "sst_components",
        "sst_parameters",
        "sst_ports",
        "sst_statistics",
        "sst_subcomp_slots",
    }

    assert expected_tables.issubset(tables)


def test_old_unprefixed_sst_tables_are_not_created():
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

    tables = {row["name"] for row in rows}

    old_tables = {
        "elements",
        "components",
        "parameters",
        "ports",
        "statistics",
        "subcomp_slots",
    }

    assert tables.isdisjoint(old_tables)