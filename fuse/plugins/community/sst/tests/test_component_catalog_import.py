
from __future__ import annotations

from fuse.plugins.community.sst.tests.conftest import memcontroller_component, write_catalog


def test_component_catalog_json_import_preserves_parameters_ports_slots_and_variable_metadata(sst_env, tmp_path):
    env = sst_env
    catalog_path = write_catalog(
        tmp_path / "sst-16.0.0.json",
        {
            "schema_version": "1.0.0",
            "source": "pytest",
            "sst_version": "16.0.0",
            "elements": [{"name": "memHierarchy", "description": "memHierarchy element"}],
            "components": [memcontroller_component()],
        },
    )

    framework_id = env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        catalog_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="pytest catalog import",
        is_default=True,
        clear_existing=True,
    )

    plugin = env.sst_plugin.SSTPlugin()
    items = plugin.load_palette_items(target_id=str(framework_id))
    mem = next(item for item in items if item.element_name == "memHierarchy" and item.type_name == "MemController")

    details = plugin.load_item_details(mem.item_id, target_id=str(framework_id))

    property_names = {prop.name for prop in details.properties}
    assert {"clock", "addr_range_start"}.issubset(property_names)

    connector_by_name = {connector.name: connector for connector in details.connectors}
    assert "direct_link" in connector_by_name
    assert "highlink%(num_ports)d" in connector_by_name

    variable = connector_by_name["highlink%(num_ports)d"]
    assert variable.is_variable is True
    assert variable.base_name == "highlink"
    assert variable.count_parameter == "num_ports"
    assert variable.default_count == 1

    slot_by_name = {slot.name: slot for slot in details.subcomp_connectors}
    assert "backend" in slot_by_name
    assert slot_by_name["backend"].required_interface == "SST::MemHierarchy::MemBackend"
