# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

import json

from PySide6.QtCore import QPointF


def make_component_definition(element: str, name: str, component_id: str):
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        target_label="SST 15.0.0",
        framework_version="15.0.0",
        component_id=component_id,
        element=element,
        name=name,
        category="TEST",
        display_name_override=f"{element}.{name}",
    )


def add_test_node(scene, component, instance_name: str, x: float, y: float, parameters=None):
    from fuse.core.ui.graphics_items import ComponentNodeItem

    node = ComponentNodeItem(
        component=component,
        instance_name=instance_name,
        parameters=parameters or {},
    )

    node.setPos(QPointF(x, y))
    scene.addItem(node)

    return node


def test_build_sst_json_exports_components(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    scene = ModelScene()

    component = make_component_definition(
        element="memHierarchy",
        name="Cache",
        component_id="1",
    )

    add_test_node(
        scene,
        component,
        "cache0",
        100,
        200,
        {
            "cache_size": "32KiB",
            "associativity": "8",
            "empty_param": "",
        },
    )

    data = build_sst_json_dict(scene)

    assert list(data.keys()) == [
        "program_options",
        "shared_params",
        "statistics_options",
        "components",
        "statistics_group",
        "links",
    ]

    assert len(data["components"]) == 1

    exported_component = data["components"][0]

    assert exported_component["name"] == "cache0"
    assert exported_component["type"] == "memHierarchy.Cache"
    assert exported_component["params"] == {
        "cache_size": "32KiB",
        "associativity": "8",
    }


def test_build_sst_json_exports_links(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.model.models import ModelLink
    from fuse.core.ui.graphics_items import ConnectionItem
    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    scene = ModelScene()

    cpu_component = make_component_definition("simpleElementExample", "example0", "1")
    cache_component = make_component_definition("simpleElementExample", "example1", "2")

    cpu_node = add_test_node(scene, cpu_component, "cpu0", 100, 100, {})
    cache_node = add_test_node(scene, cache_component, "cache0", 400, 100, {})

    cpu_out = next(port for port in cpu_node.ports if port.name == "out")
    cache_in = next(port for port in cache_node.ports if port.name == "in")

    link = ModelLink(
        link_id=1,
        name="link_cpu_cache",
        source_node_id=cpu_node.node_id,
        source_component_name="cpu0",
        source_port="out",
        target_node_id=cache_node.node_id,
        target_component_name="cache0",
        target_port="in",
        latency="1ns",
    )

    scene.addItem(ConnectionItem(link, cpu_out, cache_in))
    scene.links.append(link)

    data = build_sst_json_dict(scene)

    assert len(data["links"]) == 1

    exported_link = data["links"][0]

    assert exported_link == {
        "name": "link_cpu_cache",
        "noCut": False,
        "nonlocal": False,
        "left": {
            "component": "cpu0",
            "port": "out",
            "latency": "1ns",
        },
        "right": {
            "component": "cache0",
            "port": "in",
            "latency": "1ns",
        },
    }


def test_export_sst_json_writes_file(tmp_path, qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import export_sst_json

    scene = ModelScene()

    component = make_component_definition(
        element="memHierarchy",
        name="Cache",
        component_id="1",
    )

    add_test_node(
        scene,
        component,
        "cache0",
        100,
        200,
        {"cache_size": "32KiB"},
    )

    output_path = tmp_path / "model.sst.json"

    export_sst_json(scene, output_path)

    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))

    assert data["components"][0]["name"] == "cache0"
    assert data["components"][0]["type"] == "memHierarchy.Cache"