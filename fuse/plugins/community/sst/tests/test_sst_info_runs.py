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


def test_run_and_store_raw_sstinfo_stores_success(monkeypatch):
    from fuse.core.persistence.database import get_connection
    from fuse.plugins.community.sst import get_sstinfo as module

    def fake_get_sstinfo(args=None, timeout_seconds=60):
        return module.CommandResult(
            command=["sst-info"],
            return_code=0,
            stdout="sample stdout",
            stderr="",
        )

    monkeypatch.setattr(module, "get_sstinfo", fake_get_sstinfo)

    run_id = module.run_and_store_raw_sstinfo()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT command, return_code, stdout, stderr
            FROM sst_info_runs
            WHERE id = ?
            """,
            (run_id,),
        ).fetchone()

    assert row is not None
    assert row["return_code"] == 0
    assert row["stdout"] == "sample stdout"


def test_run_and_store_raw_sstinfo_stores_failure_before_raising(monkeypatch):
    from fuse.core.persistence.database import get_connection
    from fuse.plugins.community.sst import get_sstinfo as module

    def fake_get_sstinfo(args=None, timeout_seconds=60):
        return module.CommandResult(
            command=["sst-info"],
            return_code=2,
            stdout="bad stdout",
            stderr="bad stderr",
        )

    monkeypatch.setattr(module, "get_sstinfo", fake_get_sstinfo)

    with pytest.raises(RuntimeError):
        module.run_and_store_raw_sstinfo()

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT return_code, stdout, stderr
            FROM sst_info_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert row is not None
    assert row["return_code"] == 2
    assert row["stdout"] == "bad stdout"
    assert row["stderr"] == "bad stderr"