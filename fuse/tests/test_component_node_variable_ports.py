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

from fuse.core.model.models import ComponentDefinition, ModelLink
from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem
from fuse.core.ui.model_scene import ModelScene


def _component(plugin_id="sst"):
    return ComponentDefinition(
        plugin_id=plugin_id,
        target_id="1",
        component_id="1",
        element="merlin",
        name="hr_router",
    )


def _variable_ports():
    return [
        {
            "name": "port%(num_ports)d",
            "description": "router port",
            "iface": "",
            "is_variable": True,
            "base_name": "port",
            "count_parameter": "num_ports",
            "default_count": 2,
        },
        {
            "name": "ctrl",
            "description": "control port",
            "iface": "",
            "is_variable": False,
            "base_name": "ctrl",
            "count_parameter": "",
            "default_count": 1,
        },
    ]


def test_component_node_expands_variable_ports_and_persists_counts(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        lambda *args, **kwargs: _variable_ports(),
    )

    node = ComponentNodeItem(_component())

    assert [port.name for port in node.ports] == ["port0", "port1", "ctrl"]
    assert node.variable_port_counts == {"port": 2}
    assert node.add_ports_button is not None

    ok, message = node.set_variable_port_count("port", 4)

    assert ok is True
    assert message == ""
    assert node.expanded_port_names() == ["port0", "port1", "port2", "port3", "ctrl"]
    assert {port.name for port in node.ports} == {"port0", "port1", "port2", "port3", "ctrl"}
    assert node.variable_port_counts == {"port": 4}


def test_component_node_refuses_to_remove_connected_variable_port(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        lambda *args, **kwargs: _variable_ports(),
    )

    scene = ModelScene()
    router = ComponentNodeItem(_component(), instance_name="router0")
    peer = ComponentNodeItem(
        ComponentDefinition(plugin_id="core", element="test", name="Peer"),
        instance_name="peer0",
    )
    router.setPos(QPointF(0, 0))
    peer.setPos(QPointF(400, 0))
    scene.addItem(router)
    scene.addItem(peer)

    source = next(port for port in router.ports if port.name == "port1")
    target = next(port for port in peer.ports if port.name == "port0")
    link = ModelLink(
        link_id=1,
        name="link_router_peer",
        source_node_id=router.node_id,
        source_component_name="router0",
        source_port="port1",
        target_node_id=peer.node_id,
        target_component_name="peer0",
        target_port="port0",
    )
    scene.links.append(link)
    scene.addItem(ConnectionItem(link, source, target))

    ok, message = router.set_variable_port_count("port", 1)

    assert ok is False
    assert "port1" in message
    assert router.expanded_port_names() == ["port0", "port1", "ctrl"]
    assert {port.name for port in router.ports} == {"port0", "port1", "ctrl"}


def test_sst_component_with_no_declared_ports_does_not_get_fallback_ports(monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda *args, **kwargs: [],
    )

    sst_node = ComponentNodeItem(_component(plugin_id="sst"))
    core_node = ComponentNodeItem(_component(plugin_id="core"))

    assert sst_node.ports == []
    assert [port.name for port in core_node.ports] == ["in", "out"]
