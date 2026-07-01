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


def _mem_controller() -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        element="memHierarchy",
        name="MemController",
    )


def test_memcontroller_memory_file_na_default_is_omitted():
    node = FakeNode(
        1,
        "mc0",
        _mem_controller(),
        {
            "clock": "1GHz",
            "addr_range_start": 0,
            "addr_range_end": 2147483647,
            "memory_file": "N/A",
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert params["clock"] == "1GHz"
    assert params["addr_range_start"] == "0"
    assert params["addr_range_end"] == "2147483647"
    assert "memory_file" not in params


def test_memcontroller_real_memory_file_value_is_preserved():
    node = FakeNode(
        1,
        "mc0",
        _mem_controller(),
        {
            "clock": "1GHz",
            "memory_file": "memory.bin",
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert params["memory_file"] == "memory.bin"
