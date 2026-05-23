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

from PySide6.QtCore import QPointF


def make_component_definition():
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="test",
        component_id="1",
        element="testElement",
        name="TestComponent",
        category="TEST",
        display_name_override="testElement.TestComponent",
    )


def add_node(scene, instance_name: str, parameters=None):
    from fuse.core.ui.graphics_items import ComponentNodeItem

    node = ComponentNodeItem(
        component=make_component_definition(),
        instance_name=instance_name,
        parameters=parameters or {},
    )

    node.setPos(QPointF(0, 0))
    scene.addItem(node)

    return node


def patch_default_ports(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id: ["in", "out"],
    )


def patch_no_required_parameters(monkeypatch):
    import fuse.core.model.validation as validation_module

    monkeypatch.setattr(
        validation_module,
        "get_component_details",
        lambda plugin_id, component_id: {"parameters": []},
    )


def test_empty_model_validation_has_no_issues():
    from fuse.core.model.validation import validate_model
    from fuse.core.ui.model_scene import ModelScene

    scene = ModelScene()

    issues = validate_model(scene)

    assert issues == []


def test_duplicate_component_names_are_flagged(monkeypatch):
    patch_default_ports(monkeypatch)
    patch_no_required_parameters(monkeypatch)

    from fuse.core.model.validation import validate_model
    from fuse.core.ui.model_scene import ModelScene

    scene = ModelScene()

    add_node(scene, "dup")
    add_node(scene, "dup")

    issues = validate_model(scene)

    assert any(
        "unique" in issue.message.lower()
        or "already used" in issue.message.lower()
        or "duplicate" in issue.message.lower()
        for issue in issues
    )


def test_missing_required_parameter_is_flagged(monkeypatch):
    patch_default_ports(monkeypatch)

    import fuse.core.model.validation as validation_module

    def fake_get_component_details(plugin_id, component_id):
        return {
            "parameters": [
                {
                    "name": "clock",
                    "default_val": "<required>",
                    "required": True,
                    "description": "Required clock",
                }
            ]
        }

    monkeypatch.setattr(
        validation_module,
        "get_component_details",
        fake_get_component_details,
    )

    from fuse.core.model.validation import validate_model
    from fuse.core.ui.model_scene import ModelScene

    scene = ModelScene()
    add_node(scene, "node0", parameters={})

    issues = validate_model(scene)

    assert any("clock" in issue.message for issue in issues)


def test_required_parameter_with_value_passes(monkeypatch):
    patch_default_ports(monkeypatch)

    import fuse.core.model.validation as validation_module

    def fake_get_component_details(plugin_id, component_id):
        return {
            "parameters": [
                {
                    "name": "clock",
                    "default_val": "<required>",
                    "required": True,
                    "description": "Required clock",
                }
            ]
        }

    monkeypatch.setattr(
        validation_module,
        "get_component_details",
        fake_get_component_details,
    )

    from fuse.core.model.validation import validate_model
    from fuse.core.ui.model_scene import ModelScene

    scene = ModelScene()
    add_node(scene, "node0", parameters={"clock": "2GHz"})

    issues = validate_model(scene)

    assert not any("clock" in issue.message for issue in issues)