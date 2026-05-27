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
from PySide6.QtCore import Qt

from fuse.core.model.models import ComponentDefinition
from fuse.core.ui.graphics_items import ComponentNodeItem
from fuse.core.ui.properties_panel import PropertiesPanel


PARAMETERS = [
    {
        "name": "clock",
        "description": "Clock frequency",
        "default_val": "1.0",
        "required": True,
    },
    {
        "name": "num_cores",
        "description": "Number of cores",
        "default_val": "1",
        "required": True,
    },
    {
        "name": "label",
        "description": "User label",
        "default_val": "cpu0",
        "required": False,
    },
]


def _component_node(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: ["in", "out"],
    )
    return ComponentNodeItem(
        ComponentDefinition(
            plugin_id="core",
            component_id="cpu",
            element="test",
            name="CPU",
            category="processor",
        ),
        instance_name="CPU_1",
    )


def _find_item_by_key(panel, key):
    root = panel.tree.invisibleRootItem()
    stack = [root.child(index) for index in range(root.childCount())]

    while stack:
        item = stack.pop(0)
        if item.data(0, Qt.UserRole) == key:
            return item
        stack.extend(item.child(index) for index in range(item.childCount()))

    raise AssertionError(f"No property item found for key {key!r}")


def test_properties_panel_builds_parameter_editor_from_metadata(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.properties_panel.get_component_details",
        lambda *args, **kwargs: {"parameters": PARAMETERS},
    )
    node = _component_node(monkeypatch)
    panel = PropertiesPanel()
    qtbot.addWidget(panel)

    panel.show_component(node)

    clock = _find_item_by_key(panel, "component.parameter.clock")
    num_cores = _find_item_by_key(panel, "component.parameter.num_cores")
    label = _find_item_by_key(panel, "component.parameter.label")

    assert clock.text(0) == "clock *"
    assert clock.text(1) == "1.0"
    assert clock.data(1, Qt.UserRole)["required"] is True
    assert clock.data(1, Qt.UserRole)["description"] == "Clock frequency"
    assert num_cores.text(0) == "num_cores *"
    assert num_cores.text(1) == "1"
    assert label.text(0) == "label"
    assert label.text(1) == "cpu0"


def test_properties_panel_writes_parameter_updates_back_to_model(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.properties_panel.get_component_details",
        lambda *args, **kwargs: {"parameters": PARAMETERS},
    )
    node = _component_node(monkeypatch)
    panel = PropertiesPanel()
    qtbot.addWidget(panel)

    changed = []
    panel.property_changed_callback = lambda: changed.append(True)
    panel.show_component(node)

    clock = _find_item_by_key(panel, "component.parameter.clock")
    clock.setText(1, "2.5")

    assert node.parameters["clock"] == "2.5"
    assert changed


def test_properties_panel_validates_parameter_types_and_required_values(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.properties_panel.get_component_details",
        lambda *args, **kwargs: {"parameters": PARAMETERS},
    )

    warnings = []
    monkeypatch.setattr(
        "fuse.core.ui.properties_panel.QMessageBox.warning",
        lambda *args: warnings.append(args),
    )

    node = _component_node(monkeypatch)
    panel = PropertiesPanel()
    qtbot.addWidget(panel)
    panel.show_component(node)

    num_cores = _find_item_by_key(panel, "component.parameter.num_cores")
    num_cores.setText(1, "not-an-int")

    assert num_cores.text(1) == "1"
    assert "num_cores" not in node.parameters
    assert warnings

    warnings.clear()
    clock = _find_item_by_key(panel, "component.parameter.clock")
    clock.setText(1, "")

    assert clock.text(1) == "1.0"
    assert "clock" not in node.parameters
    assert warnings
