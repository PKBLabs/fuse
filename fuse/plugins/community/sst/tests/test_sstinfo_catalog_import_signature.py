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
import inspect

from fuse.plugins.community.sst.get_sstinfo import (
    sync_sstinfo_catalog_json_to_database,
)


def test_catalog_json_import_accepts_source_metadata_keywords():
    """Guard the catalog import API used by SST catalog lifecycle tests.

    CI previously failed when component_catalog.py and several SST tests called
    sync_sstinfo_catalog_json_to_database(..., source_kind=...) but the checked
    out get_sstinfo.py still had the older import function signature.
    """

    signature = inspect.signature(sync_sstinfo_catalog_json_to_database)

    for parameter_name in (
        "source_kind",
        "source_path",
        "command",
        "is_default",
        "clear_existing",
    ):
        assert parameter_name in signature.parameters
