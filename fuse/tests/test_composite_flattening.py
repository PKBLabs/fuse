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
from dataclasses import dataclass, field


@dataclass
class FakePort:
    name: str
    metadata: dict = field(default_factory=dict)


@dataclass
class FakeNode:
    component: object
    node_id: int
    instance_name: str
    parameters: dict = field(default_factory=dict)
    variable_port_counts: dict = field(default_factory=dict)
    ports: list[FakePort] = field(default_factory=list)

    def expanded_port_names(self):
        return [port.name for port in self.ports]


@dataclass
class FakeScene:
    nodes: list[FakeNode]
    links: list
    subcomp_attachments: list = field(default_factory=list)
    active_plugin_id: str = "sst"

    def component_items(self):
        return self.nodes


def sst_component(component_id: str, name: str):
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="sst",
        target_id="sst-test",
        component_id=component_id,
        element="memHierarchy",
        name=name,
    )


def composite_component(composite_id: str, name: str):
    from fuse.core.model.composite import (
        COMPOSITE_CATEGORY,
        COMPOSITE_ELEMENT,
        COMPOSITE_PLUGIN_ID,
        COMPOSITE_TARGET_ID,
    )
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id=COMPOSITE_PLUGIN_ID,
        target_id=COMPOSITE_TARGET_ID,
        component_id=composite_id,
        element=COMPOSITE_ELEMENT,
        name=name,
        category=COMPOSITE_CATEGORY,
        display_name_override=f"{name} (Composite)",
        is_composite=1,
        composite_id=composite_id,
    )


def save_cache_pair_composite(composite_id="flatten-cache-pair"):
    from fuse.core.model.composite import (
        CompositeComponentDefinition,
        CompositePortMapping,
    )
    from fuse.core.persistence.composite_components import save_composite_component_definition

    definition = CompositeComponentDefinition.make(
        composite_id=composite_id,
        name="Cache Pair",
        mini_model={
            "schemaVersion": "0.1.0",
            "kind": "fuse.composite-mini-model",
            "components": [
                {
                    "id": 1,
                    "element": "memHierarchy",
                    "name": "Cache",
                    "pluginId": "sst",
                    "targetId": "sst-test",
                    "componentId": "cache-type",
                    "instanceName": "cache_a",
                    "parameters": {"cache_size": "4KiB"},
                    "variablePortCounts": {},
                    "position": {"x": 0.0, "y": 0.0},
                },
                {
                    "id": 2,
                    "element": "memHierarchy",
                    "name": "Cache",
                    "pluginId": "sst",
                    "targetId": "sst-test",
                    "componentId": "cache-type",
                    "instanceName": "cache_b",
                    "parameters": {"cache_size": "8KiB"},
                    "variablePortCounts": {},
                    "position": {"x": 160.0, "y": 0.0},
                },
            ],
            "links": [
                {
                    "id": 1,
                    "name": "internal_cache_link",
                    "sourceLatency": "250ps",
                    "targetLatency": "250ps",
                    "pluginId": "sst",
                    "source": {
                        "nodeId": 1,
                        "componentName": "cache_a",
                        "port": "mem",
                    },
                    "target": {
                        "nodeId": 2,
                        "componentName": "cache_b",
                        "port": "cpu",
                    },
                }
            ],
            "subcompAttachments": [],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.cpu",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="cpu",
                iface="memHierarchy.memEvent",
                exposed=True,
            ),
            CompositePortMapping(
                external_port_name="cache_b.mem",
                internal_node_id=2,
                internal_component_name="cache_b",
                internal_port_name="mem",
                iface="memHierarchy.memEvent",
                exposed=True,
            ),
        ],
    )
    return save_composite_component_definition(definition)


def patch_port_metadata(monkeypatch):
    def load_metadata(plugin_id, component_id, target_id=None):
        if component_id in {"cache-type", "cpu-type"}:
            return [
                {"name": "cpu", "iface": "memHierarchy.memEvent", "is_variable": False},
                {"name": "mem", "iface": "memHierarchy.memEvent", "is_variable": False},
            ]
        return []

    monkeypatch.setattr(
        "fuse.core.persistence.db_access.load_port_metadata_for_component",
        load_metadata,
    )


def test_flatten_scene_expands_composite_and_remaps_external_links(monkeypatch):
    from fuse.core.model.composite_flattening import flatten_scene_for_export
    from fuse.core.model.models import ModelLink

    patch_port_metadata(monkeypatch)
    definition = save_cache_pair_composite()

    cpu = FakeNode(
        sst_component("cpu-type", "standardCPU"),
        10,
        "cpu0",
        ports=[FakePort("mem")],
    )
    composite = FakeNode(
        composite_component(definition.composite_id, definition.name),
        20,
        "Cache Pair_1",
        ports=[FakePort("cache_a.cpu"), FakePort("cache_b.mem")],
    )
    external_link = ModelLink(
        7,
        "cpu_to_pair",
        10,
        "cpu0",
        "mem",
        20,
        "Cache Pair_1",
        "cache_a.cpu",
        plugin_id="sst",
    )

    flattened = flatten_scene_for_export(FakeScene([cpu, composite], [external_link]))

    names = {node.instance_name for node in flattened.component_items()}
    assert "Cache Pair_1" not in names
    assert "cache_a_mc1" in names
    assert "cache_b_mc1" in names
    assert "cpu0" in names
    assert all(not node.component.is_composite for node in flattened.component_items())

    external = next(link for link in flattened.links if link.name == "cpu_to_pair")
    assert external.source_component_name == "cpu0"
    assert external.source_port == "mem"
    assert external.target_component_name == "cache_a_mc1"
    assert external.target_port == "cpu"

    internal = next(link for link in flattened.links if link.name == "internal_cache_link")
    assert internal.source_component_name == "cache_a_mc1"
    assert internal.source_port == "mem"
    assert internal.target_component_name == "cache_b_mc1"
    assert internal.target_port == "cpu"


def test_flatten_scene_generates_unique_internal_names_for_multiple_instances(monkeypatch):
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    patch_port_metadata(monkeypatch)
    definition = save_cache_pair_composite("flatten-cache-pair-multi")
    first = FakeNode(composite_component(definition.composite_id, definition.name), 1, "Pair_1")
    second = FakeNode(composite_component(definition.composite_id, definition.name), 2, "Pair_2")

    flattened = flatten_scene_for_export(FakeScene([first, second], []))
    names = [node.instance_name for node in flattened.component_items()]

    assert len(names) == len(set(names))
    assert {"cache_a_mc1", "cache_b_mc1", "cache_a_mc2", "cache_b_mc2"}.issubset(set(names))


def test_sst_json_export_flattens_composites_before_building_json(monkeypatch):
    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    patch_port_metadata(monkeypatch)
    definition = save_cache_pair_composite("flatten-cache-pair-sst-json")
    cpu = FakeNode(
        sst_component("cpu-type", "standardCPU"),
        10,
        "cpu0",
        ports=[FakePort("mem")],
    )
    composite = FakeNode(
        composite_component(definition.composite_id, definition.name),
        20,
        "Cache Pair_1",
        ports=[FakePort("cache_a.cpu"), FakePort("cache_b.mem")],
    )
    external_link = ModelLink(
        1,
        "cpu_to_pair",
        10,
        "cpu0",
        "mem",
        20,
        "Cache Pair_1",
        "cache_a.cpu",
        plugin_id="sst",
    )

    data = build_sst_json_dict(FakeScene([cpu, composite], [external_link]))

    component_names = {component["name"] for component in data["components"]}
    assert "Cache Pair_1" not in component_names
    assert {"cpu0", "cache_a_mc1", "cache_b_mc1"}.issubset(component_names)

    exported_link = next(link for link in data["links"] if link["name"] == "cpu_to_pair")
    assert exported_link["left"]["component"] == "cpu0"
    assert exported_link["left"]["port"] == "mem"
    assert exported_link["right"]["component"] == "cache_a_mc1"
    assert exported_link["right"]["port"] == "cpu"


def test_flatten_scene_reports_missing_composite_definition():
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    missing = FakeNode(composite_component("missing-template", "Missing"), 1, "Missing_1")

    try:
        flatten_scene_for_export(FakeScene([missing], []))
    except ValueError as exc:
        assert "missing-template" in str(exc)
    else:
        raise AssertionError("missing composite definition should fail flattening")


def test_flatten_scene_rejects_link_to_hidden_composite_port(monkeypatch):
    from fuse.core.model.composite import CompositeComponentDefinition, CompositePortMapping
    from fuse.core.model.composite_flattening import flatten_scene_for_export
    from fuse.core.model.models import ModelLink
    from fuse.core.persistence.composite_components import save_composite_component_definition

    patch_port_metadata(monkeypatch)
    definition = save_cache_pair_composite("flatten-hidden-port")
    definition.port_mappings = [
        CompositePortMapping(
            external_port_name="cache_a.cpu",
            internal_node_id=1,
            internal_component_name="cache_a",
            internal_port_name="cpu",
            iface="memHierarchy.memEvent",
            exposed=False,
        )
    ]
    save_composite_component_definition(definition)

    cpu = FakeNode(
        sst_component("cpu-type", "standardCPU"),
        10,
        "cpu0",
        ports=[FakePort("mem")],
    )
    composite = FakeNode(
        composite_component(definition.composite_id, definition.name),
        20,
        "Cache Pair_1",
        ports=[],
    )
    external_link = ModelLink(
        7,
        "cpu_to_hidden_pair_port",
        10,
        "cpu0",
        "mem",
        20,
        "Cache Pair_1",
        "cache_a.cpu",
        plugin_id="sst",
    )

    try:
        flatten_scene_for_export(FakeScene([cpu, composite], [external_link]))
    except ValueError as exc:
        assert "make sure the port is exposed" in str(exc)
        assert "cpu_to_hidden_pair_port" in str(exc)
    else:
        raise AssertionError("link to hidden composite port should fail flattening")
