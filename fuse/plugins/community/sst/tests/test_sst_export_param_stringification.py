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


def test_component_params_are_stringified_for_sst_json_parser_compatibility():
    node = FakeNode(
        1,
        "bus0",
        _component("memHierarchy", "Bus"),
        {
            "broadcast": False,
            "idle_max": 6,
            "bus_frequency": "2GHz",
            "nested": ["x", 1],
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert params == {
        "broadcast": "false",
        "bus_frequency": "2GHz",
        "idle_max": "6",
        "nested": '["x",1]',
    }
    assert all(isinstance(value, str) for value in params.values())


def test_shared_params_are_stringified_without_mutating_caller_data():
    node = FakeNode(1, "cache0", _component("memHierarchy", "Cache"))
    shared_params = [
        {
            "name": "shared_defaults",
            "params": {
                "enabled": True,
                "count": 4,
                "clock": "2GHz",
            },
        }
    ]

    data = build_sst_json_dict(FakeScene([node]), shared_params=shared_params)

    assert data["shared_params"][0]["params"] == {
        "clock": "2GHz",
        "count": "4",
        "enabled": "true",
    }
    assert shared_params[0]["params"]["enabled"] is True
    assert shared_params[0]["params"]["count"] == 4
