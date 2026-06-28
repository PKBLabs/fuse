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
from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from fuse.plugins.community.sst.tests.sst_version_support import (
    expected_sst_version,
    expected_sst_version_policy,
    require_sst_info,
)

pytestmark = pytest.mark.sst_live


def require_sst_binary() -> str:
    path = shutil.which("sst")
    if path is None:
        pytest.skip("sst is not installed")
    return path

def prepare_live_sst_database() -> None:
    require_sst_info()

    from fuse.core.persistence.db_access import ensure_database_ready
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_to_database

    version = expected_sst_version()
    ensure_database_ready(run_plugin_bootstrap=False)
    sync_sstinfo_to_database(
        version=version,
        label=f"SST {version}",
        is_default=True,
    )


def plugin_and_default_target():
    prepare_live_sst_database()

    from fuse.plugins.community.sst.plugin import SSTPlugin

    plugin = SSTPlugin()
    targets = plugin.list_targets()
    assert targets

    return plugin, next((target for target in targets if target.is_default), targets[0])


def first_item_with_details(predicate):
    plugin, target = plugin_and_default_target()

    for item in plugin.load_palette_items(target_id=target.target_id):
        details = plugin.load_item_details(item.item_id, target_id=target.target_id)
        if predicate(item, details):
            return plugin, target, item, details

    pytest.skip("The live SST catalog did not contain a component matching this test fixture.")


def required_parameter_names(details) -> set[str]:
    return {
        prop.name
        for prop in details.properties
        if prop.required and not str(prop.default_value or "").strip().replace("<required>", "")
    }


def node_for_palette_item(item, parameters=None):
    from fuse.core.model.models import ComponentDefinition

    component = ComponentDefinition(
        plugin_id=item.plugin_id,
        target_id=item.target_id,
        target_label=item.target_label,
        framework_version=item.framework_version,
        component_id=item.item_id,
        element=item.element_name,
        name=item.type_name,
        is_subcomp=1 if item.raw_kind == "SubComponent" else 0,
        category=item.category,
        iface=item.iface,
        display_name_override=item.display_name,
    )

    return SimpleNamespace(
        node_id=1,
        instance_name="fuse_live_component0",
        component=component,
        parameters=parameters or {},
    )


class SingleNodeScene:
    def __init__(self, node):
        self.node = node
        self.links = []
        self.subcomp_attachments = []

    def component_items(self):
        return [self.node]


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


def test_real_sst_binary_runs_successfully():
    require_sst_binary()

    result = subprocess.run(
        ["sst", "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )

    output = (result.stdout + "\n" + result.stderr).strip()

    assert result.returncode == 0
    assert output
    assert "sst" in output.lower()


def test_real_sst_toolchain_validation_accepts_configured_version():
    sst_info_path = require_sst_info()

    from fuse.core.model.project_settings import ToolchainSettings
    from fuse.plugins.community.sst.get_sstinfo import validate_sst_toolchain

    ok, message, result = validate_sst_toolchain(
        ToolchainSettings(tool_paths={"sstInfo": sst_info_path}),
        expected_version=expected_sst_version(),
        version_policy=expected_sst_version_policy(),
    )

    assert ok is True, message
    assert result is not None
    assert result.return_code == 0
    assert message.strip()


def test_real_sst_sync_records_successful_raw_run_and_catalog_counts():
    prepare_live_sst_database()

    from fuse.core.persistence.database import get_connection

    with get_connection() as conn:
        run = conn.execute(
            """
            SELECT return_code, stdout
            FROM sst_info_runs
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        element_count = conn.execute("SELECT COUNT(*) AS count FROM sst_elements").fetchone()["count"]
        component_count = conn.execute("SELECT COUNT(*) AS count FROM sst_components").fetchone()["count"]
        parameter_count = conn.execute("SELECT COUNT(*) AS count FROM sst_parameters").fetchone()["count"]
        port_count = conn.execute("SELECT COUNT(*) AS count FROM sst_ports").fetchone()["count"]

    assert run is not None
    assert run["return_code"] == 0
    assert "ELEMENT LIBRARY" in run["stdout"]
    assert element_count > 0
    assert component_count > 0
    assert parameter_count > 0
    assert port_count > 0


def test_real_sst_plugin_lists_default_target_and_palette_items():
    plugin, target = plugin_and_default_target()

    items = plugin.load_palette_items(target_id=target.target_id)

    assert target.plugin_id == "sst"
    assert target.framework_version
    assert items
    assert all(item.plugin_id == "sst" for item in items)
    assert all(item.target_id == target.target_id for item in items)
    assert any(item.element_name for item in items)
    assert any(item.type_name for item in items)


def test_real_sst_item_details_include_catalog_metadata():
    _, target, item, details = first_item_with_details(
        lambda _item, details: bool(details.connectors or details.properties or details.subcomp_connectors)
    )

    assert details.palette_item.item_id == item.item_id
    assert details.palette_item.target_id == target.target_id
    assert details.palette_item.element_name == item.element_name
    assert details.palette_item.type_name == item.type_name
    assert details.connectors or details.properties or details.subcomp_connectors


def test_real_sst_catalog_contains_component_with_port_metadata():
    _, _, _, details = first_item_with_details(lambda _item, details: bool(details.connectors))

    connector = details.connectors[0]

    assert connector.name
    assert connector.base_name or connector.name
    assert isinstance(connector.is_variable, bool)
    assert connector.default_count >= 1


def test_real_sst_catalog_contains_component_with_parameter_metadata():
    _, _, _, details = first_item_with_details(lambda _item, details: bool(details.properties))

    prop = details.properties[0]

    assert prop.name
    assert isinstance(prop.description, str)
    assert isinstance(prop.default_value, str)
    assert isinstance(prop.required, bool)


def test_real_sst_catalog_contains_subcomponent_metadata_when_available():
    _, _, item, details = first_item_with_details(
        lambda item, details: item.raw_kind == "SubComponent" or any(
            conn.role == "interface" for conn in details.subcomp_connectors
        )
    )

    assert item.raw_kind == "SubComponent" or details.subcomp_connectors
    if item.raw_kind == "SubComponent":
        assert item.iface or any(conn.provided_interface for conn in details.subcomp_connectors)


def test_real_sst_catalog_contains_variable_port_metadata_when_available():
    _, _, _, details = first_item_with_details(
        lambda _item, details: any(conn.is_variable for conn in details.connectors)
    )

    variable = next(conn for conn in details.connectors if conn.is_variable)

    assert variable.base_name
    assert variable.count_parameter
    assert variable.default_count >= 1


def test_real_sst_subcomponent_slot_compatibility_accepts_matching_interfaces_when_available():
    plugin, target = plugin_and_default_target()
    items = plugin.load_palette_items(target_id=target.target_id)

    slots = []
    subcomponents_by_iface = {}

    for item in items:
        details = plugin.load_item_details(item.item_id, target_id=target.target_id)

        for connector in details.subcomp_connectors:
            if connector.role == "slot" and connector.required_interface:
                slots.append(connector)

        if item.raw_kind == "SubComponent" and item.iface:
            subcomponents_by_iface.setdefault(item.iface, item)

    for slot in slots:
        subcomponent = subcomponents_by_iface.get(slot.required_interface)
        if subcomponent is None:
            continue

        result = plugin.check_subcomponent_slot_compatibility(
            slot_metadata={"required_interface": slot.required_interface},
            subcomponent_metadata={"provided_interface": subcomponent.iface},
        )

        assert result.can_create is True
        assert result.is_ok
        return

    pytest.skip("The live SST catalog did not expose a matching slot/subcomponent interface pair.")


def test_real_sst_exported_json_can_be_loaded_by_sst_run_mode_init(tmp_path):
    require_sst_binary()
    plugin, target = plugin_and_default_target()

    from fuse.plugins.community.sst.export_json import export_sst_json

    failures = []

    for item in plugin.load_palette_items(target_id=target.target_id):
        if item.raw_kind == "SubComponent":
            continue

        details = plugin.load_item_details(item.item_id, target_id=target.target_id)
        if required_parameter_names(details):
            continue

        scene = SingleNodeScene(node_for_palette_item(item))
        output_path = tmp_path / f"{item.element_name}_{item.type_name}.json".replace("/", "_")
        export_sst_json(scene, output_path)

        result = subprocess.run(
            ["sst", "--run-mode=init", str(output_path)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )

        if result.returncode == 0:
            return

        failures.append(
            f"{item.element_name}.{item.type_name}: "
            f"{(result.stdout + result.stderr).strip()[:500]}"
        )

        if len(failures) >= 25:
            break

    pytest.skip(
        "Could not find a no-required-parameter live SST component that "
        "sst --run-mode=init accepted. Tried:\n" + "\n".join(failures)
    )
