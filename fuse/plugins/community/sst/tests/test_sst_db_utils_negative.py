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
def test_get_missing_element_returns_none():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import get_element_by_name

    ensure_database_ready(run_plugin_bootstrap=False)

    assert get_element_by_name("missing") is None


def test_get_missing_component_id_returns_none():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import get_component_id

    ensure_database_ready(run_plugin_bootstrap=False)

    assert get_component_id("missing") is None


def test_get_missing_component_details_returns_none():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import get_component_details

    ensure_database_ready(run_plugin_bootstrap=False)

    assert get_component_details(999999) is None


def test_missing_element_component_queries_return_empty_lists():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.db_utils import (
        get_components_for_element,
        get_subcomponents_for_element,
    )

    ensure_database_ready(run_plugin_bootstrap=False)

    assert get_components_for_element("missing") == []
    assert get_subcomponents_for_element("missing") == []