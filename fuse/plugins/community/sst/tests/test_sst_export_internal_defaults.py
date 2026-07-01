# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any


@dataclass
class FakeNode:
    node_id: int
    instance_name: str
    component: Any
    parameters: dict[str, Any] = field(default_factory=dict)
    ports: list[Any] = field(default_factory=list)


class FakeScene:
    def __init__(self, nodes, links=None, attachments=None):
        self._nodes = list(nodes)
        self.links = list(links or [])
        self.subcomp_attachments = list(attachments or [])

    def component_items(self):
        return list(self._nodes)


def make_component(element: str, name: str, *, is_subcomp: int = 0):
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="sst",
        target_id="test-target",
        target_label="SST 99.9.9",
        framework_version="99.9.9",
        component_id=f"{element}.{name}",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
    )


def test_export_omits_sst_internal_type_placeholder_defaults(monkeypatch):
    from fuse.plugins.community.sst import export_json
    from fuse.plugins.community.sst.policy import runtime

    metadata = {
        "cache_size": {
            "description": "(string) Cache size",
            "default_val": "",
            "required": True,
        },
        "associativity": {
            "description": "(uint) Associativity",
            "default_val": "",
            "required": True,
        },
        "debug": {
            "description": "(uint) Debug level",
            "default_val": "0",
            "required": False,
        },
        "coherence_protocol": {
            "description": "(string) Coherence protocol",
            "default_val": "MESI",
            "required": False,
        },
        "prefetcher": {
            "description": "Prefetcher implementation",
            "default_val": "SST::MemHierarchy::CacheListener",
            "required": False,
        },
        "replacement": {
            "description": "Replacement policy implementation",
            "default_val": "SST::MemHierarchy::ReplacementPolicy",
            "required": False,
        },
        "backendConvertor": {
            "description": "Backend convertor implementation",
            "default_val": "memHierarchy.simpleMembackendConvertor",
            "required": False,
        },
        "trace_file": {
            "description": "Trace filename",
            "default_val": "mapFile.txt",
            "required": False,
        },
    }

    monkeypatch.setattr(runtime, "parameter_metadata_for_node", lambda node: metadata)
    monkeypatch.setattr(export_json, "parameter_metadata_for_node", lambda node: metadata)

    cache = FakeNode(
        1,
        "cache0",
        make_component("memHierarchy", "Cache"),
        {
            "cache_size": "32KiB",
            "associativity": "8",
        },
        [SimpleNamespace(name="highlink"), SimpleNamespace(name="lowlink")],
    )

    data = export_json.build_sst_json_dict(FakeScene([cache]))
    params = data["components"][0]["params"]

    assert params["cache_size"] == "32KiB"
    assert params["associativity"] == "8"
    assert params["debug"] == "0"
    assert params["coherence_protocol"] == "MESI"
    assert params["trace_file"] == "mapFile.txt"
    assert "prefetcher" not in params
    assert "replacement" not in params
    assert "backendConvertor" not in params


def test_attached_subcomponent_suppresses_parent_slot_params():
    from fuse.core.model.models import ModelSubcompAttachment
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    parent = FakeNode(
        1,
        "mc0",
        make_component("memHierarchy", "MemController"),
        {
            "clock": "1GHz",
            "backend": "SST::MemHierarchy::MemBackend",
            "backend.access_time": "100ns",
        },
        [SimpleNamespace(name="highlink")],
    )
    child = FakeNode(
        2,
        "simpleMem0",
        make_component("memHierarchy", "simpleMem", is_subcomp=1),
        {"access_time": "100ns"},
        [],
    )
    attachment = ModelSubcompAttachment(
        1,
        "attach_backend",
        1,
        "mc0",
        "backend",
        2,
        "simpleMem0",
        "SST::MemHierarchy::MemBackend",
        "SST::MemHierarchy::MemBackend",
    )

    data = build_sst_json_dict(FakeScene([parent, child], attachments=[attachment]))
    exported_parent = data["components"][0]

    assert exported_parent["params"] == {"clock": "1GHz"}
    assert exported_parent["subcomponents"] == [
        {
            "slot_name": "backend",
            "type": "memHierarchy.simpleMem",
            "params": {"access_time": "100ns"},
        }
    ]


def test_symbolic_catalog_defaults_are_not_injected_even_if_policy_marks_literal(monkeypatch):
    from fuse.plugins.community.sst import export_json
    from fuse.plugins.community.sst.policy import runtime

    stale_policy = {
        "params": {
            "addr_range_end": {
                "default_kind": "literal",
                "default_value": "uint64_t-1",
                "export_default": True,
                "kind": "unknown",
                "missing_severity": "silent",
                "required": False,
            },
            "addr_range_start": {
                "default_kind": "literal",
                "default_value": "0",
                "export_default": True,
                "kind": "unknown",
                "missing_severity": "silent",
                "required": False,
            },
        }
    }

    def fake_component_policy(version, component_type):
        assert component_type == "memHierarchy.DirectoryController"
        return stale_policy

    def fake_param_policy_override(version, component_type, param_name):
        return stale_policy["params"].get(param_name, {})

    monkeypatch.setattr(runtime, "component_policy", fake_component_policy)
    monkeypatch.setattr(runtime, "param_policy_override", fake_param_policy_override)
    monkeypatch.setattr(runtime, "parameter_metadata_for_node", lambda node: {})
    monkeypatch.setattr(export_json, "parameter_metadata_for_node", lambda node: {})

    directory = FakeNode(
        1,
        "dc",
        make_component("memHierarchy", "DirectoryController"),
    )

    data = export_json.build_sst_json_dict(FakeScene([directory]))
    params = data["components"][0]["params"]

    assert params == {"addr_range_start": "0"}
    assert "addr_range_end" not in params


def test_explicit_symbolic_uint64_max_param_is_exported_as_numeric_string():
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    directory = FakeNode(
        1,
        "dc",
        make_component("memHierarchy", "DirectoryController"),
        {
            "addr_range_end": "uint64_t-1",
        },
    )

    data = build_sst_json_dict(FakeScene([directory]))
    params = data["components"][0]["params"]

    assert params["addr_range_end"] == "18446744073709551615"
