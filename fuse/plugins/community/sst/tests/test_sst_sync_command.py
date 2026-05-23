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
import pytest


def test_sync_sstinfo_to_database_uses_command_output(monkeypatch, sample_sstinfo):
    from fuse.core.persistence.database import get_connection
    from fuse.plugins.community.sst import get_sstinfo as module
    from fuse.plugins.community.sst.db_utils import get_all_components_for_element

    def fake_get_sstinfo(args=None, timeout_seconds=60):
        return module.CommandResult(
            command=["sst-info"],
            return_code=0,
            stdout=sample_sstinfo,
            stderr="",
        )

    monkeypatch.setattr(module, "get_sstinfo", fake_get_sstinfo)

    run_id = module.sync_sstinfo_to_database()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT return_code
            FROM sst_info_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    assert row["return_code"] == 0

    components = get_all_components_for_element("testElement")
    assert {component["name"] for component in components} == {
        "TestCPU",
        "TestCache",
        "TestMMU",
    }


def test_sync_sstinfo_to_database_raises_on_command_failure(monkeypatch):
    from fuse.plugins.community.sst import get_sstinfo as module

    def fake_get_sstinfo(args=None, timeout_seconds=60):
        return module.CommandResult(
            command=["sst-info"],
            return_code=1,
            stdout="",
            stderr="simulated failure",
        )

    monkeypatch.setattr(module, "get_sstinfo", fake_get_sstinfo)

    with pytest.raises(RuntimeError, match="sst-info failed"):
        module.sync_sstinfo_to_database()