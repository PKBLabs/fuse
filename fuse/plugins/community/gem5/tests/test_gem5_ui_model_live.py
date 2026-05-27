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
import os
import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt


pytestmark = pytest.mark.gem5_live


def find_gem5_binary() -> str:
    explicit = os.environ.get("GEM5_BINARY", "").strip()

    if explicit:
        path = Path(explicit)
        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    gem5_root = os.environ.get("GEM5_ROOT", "").strip()

    if gem5_root:
        root = Path(gem5_root)
        for candidate in [
            root / "build" / "X86" / "gem5.opt",
            root / "build" / "RISCV" / "gem5.opt",
            root / "build" / "ARM" / "gem5.opt",
            root / "gem5.opt",
        ]:
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)

    from_path = shutil.which("gem5")

    if from_path:
        return from_path

    pytest.skip("No gem5 binary found. Run inside a gem5-capable CI image.")


def prepare_gem5_catalog():
    find_gem5_binary()

    from fuse.core.persistence.db_access import (
        ensure_database_ready,
        load_component_definitions,
        load_framework_targets,
    )

    ensure_database_ready(run_plugin_bootstrap=False)
    targets = [target for target in load_framework_targets() if target.plugin_id == "gem5"]
    assert targets

    target = next((candidate for candidate in targets if candidate.is_default), targets[0])
    components = load_component_definitions(plugin_id="gem5", target_id=target.target_id)
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


def test_gem5_live_catalog_populates_gem5_components():
    target, components = prepare_gem5_catalog()

    assert target.framework_version
    assert any(component.plugin_id == "gem5" for component in components)
    assert all(component.target_id == target.target_id for component in components)
    assert {component.name for component in components} >= {
        "System",
        "TimingSimpleCPU",
        "SystemXBar",
    }


def test_gem5_live_component_instance_and_parameter_editor_use_real_metadata(qtbot):
    from fuse.core.persistence.db_access import get_component_details
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.properties_panel import PropertiesPanel

    _, components = prepare_gem5_catalog()
    component = next(component for component in components if component.name == "TimingSimpleCPU")
    details = get_component_details(component.plugin_id, component.component_id, component.target_id)

    scene = ModelScene()
    node = scene.create_component_node(component, QPointF(10, 20))

    assert node.component.plugin_id == "gem5"
    assert node.instance_name == "TimingSimpleCPU_1"
    assert node.pos() == QPointF(10, 20)

    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    num_threads = find_tree_item_by_key(panel, "component.parameter.numThreads")
    clock = find_tree_item_by_key(panel, "component.parameter.clock")

    assert details["parameters"]
    assert num_threads.text(0) == "numThreads *"
    assert num_threads.text(1) == "1"
    assert num_threads.data(1, Qt.UserRole)["required"] is True
    assert clock.text(0) == "clock *"
    assert clock.text(1) == "2GHz"


def test_gem5_live_parameter_updates_write_back_to_component_instance(qtbot):
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.properties_panel import PropertiesPanel

    _, components = prepare_gem5_catalog()
    component = next(component for component in components if component.name == "TimingSimpleCPU")

    scene = ModelScene()
    node = scene.create_component_node(component, QPointF(0, 0))
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    num_threads = find_tree_item_by_key(panel, "component.parameter.numThreads")
    num_threads.setText(1, "4")

    assert node.parameters["numThreads"] == "4"
