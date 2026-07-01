# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

from dataclasses import dataclass, field

from fuse.core.model.models import ComponentDefinition
from fuse.plugins.community.sst.export_json import build_sst_json_dict


@dataclass
class FakeNode:
    node_id: int
    instance_name: str
    component: ComponentDefinition
    parameters: dict = field(default_factory=dict)
    ports: list = field(default_factory=list)


class FakeScene:
    links = []
    subcomp_attachments = []

    def __init__(self, nodes):
        self._nodes = list(nodes)

    def component_items(self):
        return list(self._nodes)


def _component(element: str, name: str) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        element=element,
        name=name,
    )


def _component_by_name(data, name: str) -> dict:
    return next(component for component in data["components"] if component["name"] == name)


def test_single_directory_controller_range_matches_aggregate_memory_controller_range():
    directory = FakeNode(
        1,
        "dc",
        _component("memHierarchy", "DirectoryController"),
        {"addr_range_start": "0"},
    )
    mc0 = FakeNode(
        2,
        "mc0",
        _component("memHierarchy", "MemController"),
        {
            "addr_range_start": 0,
            "addr_range_end": 2147483647,
        },
    )
    mc1 = FakeNode(
        3,
        "mc1",
        _component("memHierarchy", "MemController"),
        {
            "addr_range_start": 2147483648,
            "addr_range_end": 4294967295,
        },
    )

    data = build_sst_json_dict(FakeScene([directory, mc0, mc1]))
    dc_params = _component_by_name(data, "dc")["params"]

    assert dc_params["addr_range_start"] == "0"
    assert dc_params["addr_range_end"] == "4294967295"


def test_multiple_directory_controllers_do_not_guess_aggregate_memory_range():
    dc0 = FakeNode(1, "dc0", _component("memHierarchy", "DirectoryController"))
    dc1 = FakeNode(2, "dc1", _component("memHierarchy", "DirectoryController"))
    mc0 = FakeNode(
        3,
        "mc0",
        _component("memHierarchy", "MemController"),
        {
            "addr_range_start": 0,
            "addr_range_end": 2147483647,
        },
    )

    data = build_sst_json_dict(FakeScene([dc0, dc1, mc0]))

    assert "params" not in _component_by_name(data, "dc0")
    assert "params" not in _component_by_name(data, "dc1")
