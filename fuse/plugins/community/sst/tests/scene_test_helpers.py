# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Small in-memory scene helpers for SST export/runtime tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fuse.core.model.models import ComponentDefinition


@dataclass
class FakeNode:
    node_id: int
    instance_name: str
    component: ComponentDefinition
    parameters: dict[str, Any] = field(default_factory=dict)


class FakeScene:
    def __init__(self, nodes=None, links=None, attachments=None):
        self._nodes = list(nodes or [])
        self.links = list(links or [])
        self.subcomp_attachments = list(attachments or [])

    def component_items(self):
        return list(self._nodes)


def make_sst_component(
    element: str,
    name: str,
    *,
    target_id: int | str = "",
    target_label: str = "",
    framework_version: str = "16.0.0",
    component_id: int | str | None = None,
    is_subcomp: int = 0,
    plugin_id: str = "sst",
) -> ComponentDefinition:
    return ComponentDefinition(
        component_id=str(component_id or ""),
        plugin_id=plugin_id,
        target_id=str(target_id or ""),
        target_label=target_label or (f"SST target {target_id}" if target_id else ""),
        framework_version=framework_version,
        element=element,
        name=name,
        is_subcomp=is_subcomp,
        display_name_override=f"{element}.{name}",
    )


def make_node(
    node_id: int,
    instance_name: str,
    element: str,
    name: str,
    *,
    target_id: int | str = "",
    parameters: dict[str, Any] | None = None,
    is_subcomp: int = 0,
) -> FakeNode:
    return FakeNode(
        node_id=node_id,
        instance_name=instance_name,
        component=make_sst_component(
            element,
            name,
            target_id=target_id,
            is_subcomp=is_subcomp,
        ),
        parameters=dict(parameters or {}),
    )


def scene_with_nodes(*nodes: FakeNode) -> FakeScene:
    return FakeScene(nodes)
