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
def test_sync_sstinfo_file_to_database(tmp_path):
    from fuse.plugins.community.sst.db_utils import (
        get_all_components_for_element,
        get_all_elements,
    )
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_file_to_database
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    path = tmp_path / "sample_sstinfo.txt"
    path.write_text(SAMPLE_SSTINFO, encoding="utf-8")

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