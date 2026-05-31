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


def make_test_component_definition(name: str, component_id: int):
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="sst",
        component_id=component_id,
        element="testElement",
        name=name,
        is_subcomp=0,
        category="TEST COMPONENT",
        iface="",
        icon_path="",
        display_name_override=f"testElement.{name}",
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


def test_fuse_model_save_load_single_component_round_trip(tmp_path, qtbot, monkeypatch):
    """
    Save and reload a simple FUSE model containing one component instance.
    """

    # Avoid depending on the real plugin database for this UI-level save/load test.
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id: ["in", "out"],
    )

    from fuse.core.persistence.project_io import (
        build_project_dict,
        load_project_file,
        load_project_into_scene,
        save_project_file,
    )
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.model_view import ModelView

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    component = make_test_component_definition("TestCPU", 1)

    add_test_node(
        scene=scene,
        component=component,
        instance_name="cpu0",
        x=100,
        y=150,
        parameters={
            "clock": "2GHz",
            "threads": "4",
        },
    )

    project = build_project_dict(scene, view, "Round Trip Test")
    path = tmp_path / "round_trip_single_component.fse"

    save_project_file(project, path)
    loaded_project = load_project_file(path)

    restored_scene = ModelScene()
    load_project_into_scene(loaded_project, restored_scene)

    restored_nodes = restored_scene.component_items()

    assert len(restored_nodes) == 1

    restored_node = restored_nodes[0]

    assert restored_node.instance_name == "cpu0"
    assert restored_node.component.name == "TestCPU"
    assert restored_node.component.plugin_id == "sst"
    assert restored_node.parameters["clock"] == "2GHz"
    assert restored_node.parameters["threads"] == "4"

    # Position should survive save/load.
    assert int(restored_node.pos().x()) == 100
    assert int(restored_node.pos().y()) == 150


def test_fuse_model_save_load_two_components_with_link_round_trip(tmp_path, qtbot, monkeypatch):
    """
    Save and reload a FUSE model containing two component instances and one link.
    """

    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id: ["in", "out"],
    )

    from fuse.core.model.models import ModelLink
    from fuse.core.persistence.project_io import (
        build_project_dict,
        load_project_file,
        load_project_into_scene,
        save_project_file,
    )
    from fuse.core.ui.graphics_items import ConnectionItem
    from fuse.core.ui.model_scene import ModelScene
    from fuse.core.ui.model_view import ModelView

    scene = ModelScene()
    view = ModelView(scene)
    qtbot.addWidget(view)

    cpu_def = make_test_component_definition("TestCPU", 1)
    cache_def = make_test_component_definition("TestCache", 2)

    cpu_node = add_test_node(
        scene=scene,
        component=cpu_def,
        instance_name="cpu0",
        x=100,
        y=150,
        parameters={"clock": "2GHz"},
    )

    cache_node = add_test_node(
        scene=scene,
        component=cache_def,
        instance_name="cache0",
        x=420,
        y=150,
        parameters={"size": "32KiB"},
    )

    # With the monkeypatched port list ["in", "out"], each node should have those ports.
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
        source_latency="1ns",
        target_latency="1ns",
    )

    connection = ConnectionItem(link, cpu_out, cache_in)
    scene.addItem(connection)
    scene.links.append(link)

    project = build_project_dict(scene, view, "Linked Round Trip Test")
    path = tmp_path / "round_trip_linked_model.fse"

    save_project_file(project, path)
    loaded_project = load_project_file(path)

    restored_scene = ModelScene()
    load_project_into_scene(loaded_project, restored_scene)

    restored_nodes = sorted(
        restored_scene.component_items(),
        key=lambda node: node.instance_name,
    )

    assert len(restored_nodes) == 2

    names = {node.instance_name for node in restored_nodes}
    assert names == {"cpu0", "cache0"}

    restored_cpu = next(node for node in restored_nodes if node.instance_name == "cpu0")
    restored_cache = next(node for node in restored_nodes if node.instance_name == "cache0")

    assert restored_cpu.parameters["clock"] == "2GHz"
    assert restored_cache.parameters["size"] == "32KiB"

    assert len(restored_scene.links) == 1

    restored_link = restored_scene.links[0]

    assert restored_link.name == "link_cpu_cache"
    assert restored_link.source_component_name == "cpu0"
    assert restored_link.source_port == "out"
    assert restored_link.target_component_name == "cache0"
    assert restored_link.target_port == "in"
    assert restored_link.latency == "1ns"