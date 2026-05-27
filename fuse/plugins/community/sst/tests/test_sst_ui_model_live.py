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
from PySide6.QtCore import QPointF, Qt


pytestmark = pytest.mark.sst_live


def require_sst_info():
    if shutil.which("sst-info") is None:
        pytest.skip("sst-info is not installed")


def prepare_sst_catalog():
    require_sst_info()

    from fuse.core.persistence.db_access import ensure_database_ready, load_component_definitions
    from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_to_database

    ensure_database_ready(run_plugin_bootstrap=False)
    sync_sstinfo_to_database()

    from fuse.core.persistence.db_access import load_framework_targets

    targets = [target for target in load_framework_targets() if target.plugin_id == "sst"]
    assert targets

    target = next((candidate for candidate in targets if candidate.is_default), targets[0])
    components = load_component_definitions(plugin_id="sst", target_id=target.target_id)
    assert components
    return target, components


def find_tree_item_by_key(panel, key):
    root = panel.tree.invisibleRootItem()
    stack = [root.child(index) for index in range(root.childCount())]

    while stack:
        item = stack.pop(0)
        if item.data(0, Qt.UserRole) == key:
            return item
        stack.extend(item.child(index) for index in range(item.childCount()))

    raise AssertionError(f"No property item found for key {key!r}")




def valid_parameter_update_value(parameter):
    default_value = str(parameter.get("default_val") or "")

    if default_value == "<required>":
        default_value = ""

    if default_value:
        try:
            return str(int(default_value) + 1)
        except ValueError:
            pass

        try:
            return str(float(default_value) + 1.0)
        except ValueError:
            pass

    return "fuse_test_value"


def component_with_parameters(components):
    from fuse.core.persistence.db_access import get_component_details

    for component in components:
        details = get_component_details(
            component.plugin_id,
            component.component_id,
            component.target_id,
        )
        if details["parameters"]:
            return component, details

    pytest.skip("The synced SST catalog did not contain a component with parameters")


def test_sst_live_catalog_populates_real_sst_components():
    target, components = prepare_sst_catalog()

    assert target.framework_version
    assert any(component.plugin_id == "sst" for component in components)
    assert all(component.target_id == target.target_id for component in components)
    assert any(component.element for component in components)
    assert any(component.name for component in components)


def test_sst_live_component_instance_and_parameter_editor_use_real_metadata(qtbot):
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.properties_panel import PropertiesPanel

    _, components = prepare_sst_catalog()
    component, details = component_with_parameters(components)
    first_parameter = details["parameters"][0]

    scene = ModelScene()
    node = scene.create_component_node(component, QPointF(25, 50))

    assert node.component.plugin_id == "sst"
    assert node.instance_name == f"{component.name}_1"
    assert node.pos() == QPointF(25, 50)

    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    parameter_item = find_tree_item_by_key(
        panel,
        f"component.parameter.{first_parameter['name']}",
    )

    assert first_parameter["name"] in parameter_item.text(0)
    assert parameter_item.data(1, Qt.UserRole)["description"] == first_parameter["description"]


def test_sst_live_parameter_updates_write_back_to_component_instance(qtbot):
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.properties_panel import PropertiesPanel

    _, components = prepare_sst_catalog()
    component, details = component_with_parameters(components)
    first_parameter = details["parameters"][0]

    scene = ModelScene()
    node = scene.create_component_node(component, QPointF(0, 0))
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    parameter_item = find_tree_item_by_key(
        panel,
        f"component.parameter.{first_parameter['name']}",
    )
    updated_value = valid_parameter_update_value(first_parameter)
    parameter_item.setText(1, updated_value)

    assert node.parameters[first_parameter["name"]] == updated_value
