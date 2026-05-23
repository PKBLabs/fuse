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
import shutil
import pytest


pytestmark = pytest.mark.sst_live


def require_sst_info():
    if shutil.which("sst-info") is None:
        pytest.skip("sst-info is not installed")


def test_real_sst_info_runs_successfully():
    require_sst_info()

    from fuse.plugins.community.sst.get_sstinfo import get_sstinfo

    result = get_sstinfo(args=[])

    assert result.return_code == 0
    assert result.stdout.strip()
    assert "ELEMENT LIBRARY" in result.stdout


def test_real_sst_info_can_sync_database():
    require_sst_info()

    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_to_database

    ensure_database_ready(run_plugin_bootstrap=False)

    run_id = sync_sstinfo_to_database()

    assert isinstance(run_id, int)

    with get_connection() as conn:
        element_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sst_elements"
        ).fetchone()["count"]

        component_count = conn.execute(
            "SELECT COUNT(*) AS count FROM sst_components"
        ).fetchone()["count"]

    assert element_count > 0
    assert component_count > 0