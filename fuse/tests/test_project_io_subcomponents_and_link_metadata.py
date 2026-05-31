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

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.core.persistence.project_io import build_project_dict, load_project_into_scene
from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, SubcompAttachmentItem
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView


class _DummyView(ModelView):
    pass


def _component(name, *, is_subcomp=0, iface=""):
    return ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        target_label="SST 15.0.0",
        framework_version="15.0.0",
        component_id=name,
        element="testElement",
        name=name,
        is_subcomp=is_subcomp,
        iface=iface,
    )


def _port_metadata(plugin_id, component_id, target_id=None):
    if component_id == "CPU":
        return [{"name": "cache", "base_name": "cache", "is_variable": False, "default_count": 1}]
    if component_id == "Cache":
        return [{"name": "cpu", "base_name": "cpu", "is_variable": False, "default_count": 1}]
    return []


def _subcomp_metadata(plugin_id, component_id, target_id=None):
    if component_id == "CPU":
        return [
            {
                "name": "mmu",
                "role": "slot",
                "required_interface": "SST::MMU",
                "provided_interface": "",
                "interface": "SST::MMU",
                "iface": "SST::MMU",
            }
        ]
    if component_id == "MMU":
        return [
            {
                "name": "interface",
                "role": "interface",
                "required_interface": "",
                "provided_interface": "SST::MMU",
                "interface": "SST::MMU",
                "iface": "SST::MMU",
            }
        ]
    return []


def _add_node(scene, component, name, x, y, parameters=None, variable_port_counts=None):
    node = ComponentNodeItem(
        component,
        instance_name=name,
        parameters=parameters or {},
        variable_port_counts=variable_port_counts or {},
    )
    node.setPos(QPointF(x, y))
    scene.addItem(node)
    return node


def test_project_io_round_trips_link_endpoint_latencies_and_subcomponent_attachments(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        _port_metadata,
    )
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_subcomp_connector_metadata_for_component",
        _subcomp_metadata,
    )

    scene = ModelScene()
    view = _DummyView(scene)
    qtbot.addWidget(view)

    cpu = _add_node(scene, _component("CPU"), "cpu0", 10, 20, {"clock": "2GHz"})
    cache = _add_node(scene, _component("Cache"), "cache0", 320, 20, {"size": "32KiB"})
    mmu = _add_node(scene, _component("MMU", is_subcomp=1, iface="SST::MMU"), "mmu0", 10, 280)

    cpu_cache = ModelLink(
        link_id=1,
        name="link_cpu_cache",
        source_node_id=cpu.node_id,
        source_component_name="cpu0",
        source_port="cache",
        target_node_id=cache.node_id,
        target_component_name="cache0",
        target_port="cpu",
        source_latency="250ps",
        target_latency="1ns",
        plugin_id="sst",
        compatibility_severity="warning",
        compatibility_code="test.warning",
        compatibility_message="test warning",
        plugin_metadata={"source": "unit-test"},
    )
    scene.links.append(cpu_cache)
    scene.addItem(
        ConnectionItem(
            cpu_cache,
            next(port for port in cpu.ports if port.name == "cache"),
            next(port for port in cache.ports if port.name == "cpu"),
        )
    )

    attachment = ModelSubcompAttachment(
        attachment_id=1,
        name="subcomp_cpu0_mmu_mmu0",
        parent_node_id=cpu.node_id,
        parent_component_name="cpu0",
        slot_name="mmu",
        child_node_id=mmu.node_id,
        child_component_name="mmu0",
        required_interface="SST::MMU",
        provided_interface="SST::MMU",
        compatibility_severity="ok",
        plugin_id="sst",
        plugin_metadata={"source": "unit-test"},
    )
    scene.subcomp_attachments.append(attachment)
    scene.addItem(
        SubcompAttachmentItem(
            attachment,
            next(connector for connector in cpu.subcomp_connectors if connector.name == "mmu"),
            next(connector for connector in mmu.subcomp_connectors if connector.name == "interface"),
        )
    )

    project = build_project_dict(scene, view, "metadata round trip", active_plugin_id="sst", active_target_id="1")

    assert project["links"][0]["sourceLatency"] == "250ps"
    assert project["links"][0]["targetLatency"] == "1ns"
    assert project["links"][0]["compatibility"]["code"] == "test.warning"
    assert project["links"][0]["pluginMetadata"] == {"source": "unit-test"}
    assert project["subcompAttachments"][0]["requiredInterface"] == "SST::MMU"

    restored = ModelScene()
    load_project_into_scene(project, restored)

    assert len(restored.component_items()) == 3
    assert len(restored.links) == 1
    assert len(restored.subcomp_attachments) == 1
    assert len(restored.connection_items()) == 1
    assert len(restored.subcomp_attachment_items()) == 1

    restored_link = restored.links[0]
    assert restored_link.source_latency == "250ps"
    assert restored_link.target_latency == "1ns"
    assert restored_link.compatibility_severity == "warning"
    assert restored_link.compatibility_code == "test.warning"
    assert restored_link.plugin_metadata == {"source": "unit-test"}

    restored_attachment = restored.subcomp_attachments[0]
    assert restored_attachment.parent_component_name == "cpu0"
    assert restored_attachment.child_component_name == "mmu0"
    assert restored_attachment.slot_name == "mmu"
    assert restored_attachment.required_interface == "SST::MMU"
    assert restored_attachment.provided_interface == "SST::MMU"
    assert restored_attachment.plugin_metadata == {"source": "unit-test"}


def test_project_io_loads_legacy_single_latency_links(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_metadata_for_component",
        _port_metadata,
    )
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_subcomp_connector_metadata_for_component",
        lambda *args, **kwargs: [],
    )

    project = {
        "schemaVersion": "0.1.0",
        "project": {"name": "legacy"},
        "components": [
            {
                "id": 1,
                "pluginId": "sst",
                "targetId": "1",
                "componentId": "CPU",
                "element": "testElement",
                "name": "CPU",
                "instanceName": "cpu0",
                "position": {"x": 0, "y": 0},
            },
            {
                "id": 2,
                "pluginId": "sst",
                "targetId": "1",
                "componentId": "Cache",
                "element": "testElement",
                "name": "Cache",
                "instanceName": "cache0",
                "position": {"x": 300, "y": 0},
            },
        ],
        "links": [
            {
                "id": 1,
                "name": "legacy_link",
                "latency": "5ns",
                "source": {"nodeId": 1, "componentName": "cpu0", "port": "cache"},
                "target": {"nodeId": 2, "componentName": "cache0", "port": "cpu"},
            }
        ],
    }

    scene = ModelScene()
    load_project_into_scene(project, scene)

    assert scene.links[0].source_latency == "5ns"
    assert scene.links[0].target_latency == "5ns"
    assert scene.links[0].latency == "5ns"
