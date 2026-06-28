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


def test_sync_sstinfo_file_to_database(tmp_path, sample_sstinfo):
    from fuse.plugins.community.sst.db_utils import (
        get_all_components_for_element,
        get_all_elements,
    )
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_file_to_database

    path = tmp_path / "sample_sstinfo.txt"
    path.write_text(sample_sstinfo, encoding="utf-8")

    sync_sstinfo_file_to_database(str(path))

    elements = get_all_elements()
    components = get_all_components_for_element("testElement")

    assert len(elements) == 1
    assert elements[0]["name"] == "testElement"
    assert {component["name"] for component in components} == {
        "TestCPU",
        "TestCache",
        "TestMMU",
    }


def test_sync_sstinfo_file_missing_file_raises(tmp_path):
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_file_to_database

    missing_path = tmp_path / "does_not_exist.txt"

    with pytest.raises(FileNotFoundError):
        sync_sstinfo_file_to_database(str(missing_path))


def test_sync_empty_sstinfo_file_imports_nothing(tmp_path):
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import get_all_elements
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_file_to_database

    ensure_database_ready(run_plugin_bootstrap=False)

    path = tmp_path / "empty_sstinfo.txt"
    path.write_text("", encoding="utf-8")

    sync_sstinfo_file_to_database(str(path))

    assert get_all_elements() == []