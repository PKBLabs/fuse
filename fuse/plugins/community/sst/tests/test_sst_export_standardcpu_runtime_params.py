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


def _standard_cpu() -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id="sst",
        element="memHierarchy",
        name="standardCPU",
    )


def test_standardcpu_zero_mmio_addr_default_is_omitted_when_mmio_is_disabled():
    node = FakeNode(
        1,
        "cpu0",
        _standard_cpu(),
        {
            "clock": "2GHz",
            "memFreq": 2,
            "memSize": "4GiB",
            "opCount": 20000,
            "read_freq": 88,
            "write_freq": 30,
            "mmio_addr": 0,
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert "mmio_addr" not in params
    assert params["memSize"] == "4GiB"
    assert params["memFreq"] == "2"


def test_standardcpu_nonzero_mmio_addr_is_preserved():
    node = FakeNode(
        1,
        "cpu0",
        _standard_cpu(),
        {
            "memFreq": 2,
            "memSize": "4GiB",
            "opCount": 20000,
            "mmio_freq": 1,
            "mmio_addr": 4294967296,
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert params["mmio_freq"] == "1"
    assert params["mmio_addr"] == "4294967296"


def test_standardcpu_zero_mmio_addr_is_preserved_when_mmio_frequency_is_enabled():
    node = FakeNode(
        1,
        "cpu0",
        _standard_cpu(),
        {
            "memFreq": 2,
            "memSize": "4GiB",
            "opCount": 20000,
            "mmio_freq": 1,
            "mmio_addr": 0,
        },
    )

    data = build_sst_json_dict(FakeScene([node]))
    params = data["components"][0]["params"]

    assert params["mmio_freq"] == "1"
    assert params["mmio_addr"] == "0"
