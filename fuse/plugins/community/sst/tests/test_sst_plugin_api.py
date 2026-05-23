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
def populate_sample_database():
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.get_sstinfo import (
        parse_sstinfo_output,
        sync_parsed_sstinfo_to_database,
    )
    from fuse.plugins.community.sst.tests.conftest import SAMPLE_SSTINFO

    ensure_database_ready(run_plugin_bootstrap=False)

    elements, components = parse_sstinfo_output(SAMPLE_SSTINFO)
    sync_parsed_sstinfo_to_database(elements, components)


def test_sst_plugin_loads_palette_items():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    populate_sample_database()

    plugin = SSTPlugin()
    items = plugin.load_palette_items()

    names = {item.type_name for item in items}

    assert "TestCPU" in names
    assert "TestCache" in names
    assert "TestMMU" in names

    for item in items:
        assert item.plugin_id == "sst"
        assert item.item_id


def test_sst_plugin_loads_item_details():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    populate_sample_database()

    plugin = SSTPlugin()
    items = plugin.load_palette_items()

    cpu_item = next(item for item in items if item.type_name == "TestCPU")
    details = plugin.load_item_details(cpu_item.item_id)

    assert details.palette_item.type_name == "TestCPU"
    assert {connector.name for connector in details.connectors} == {
        "cache_link",
        "memory_link",
    }
    assert {prop.name for prop in details.properties} == {
        "clock",
        "threads",
    }


def test_sst_plugin_bootstrap_skips_when_sst_info_missing(monkeypatch, capsys):
    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.plugin import SSTPlugin

    ensure_database_ready(run_plugin_bootstrap=False)

    monkeypatch.setattr("shutil.which", lambda command: None)

    plugin = SSTPlugin()
    plugin.bootstrap_database()

    captured = capsys.readouterr()

    assert "sst-info not found" in captured.out