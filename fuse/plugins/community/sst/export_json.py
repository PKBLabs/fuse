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
# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_LINK_LATENCY = "1ns"


class SSTJsonExportError(RuntimeError):
    pass


def _clean_value(value: Any) -> Any:
    """
    Keep SST parameter values simple and JSON-safe.

    Most SST parameters are strings in practice, but JSON can safely carry
    booleans, numbers, strings, arrays, and objects if FUSE later supports
    typed parameter editors.
    """
    if value is None:
        return ""

    return value


def _non_empty_params(parameters: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}

    for key, value in parameters.items():
        if key is None:
            continue

        key_text = str(key).strip()

        if not key_text:
            continue

        cleaned = _clean_value(value)

        if cleaned is None:
            continue

        if isinstance(cleaned, str) and cleaned.strip() == "":
            continue

        result[key_text] = cleaned

    return result


def sst_component_type_for_node(node) -> str:
    """
    Convert a FUSE component node into an SST component type.

    SST component types are normally:
        element.component

    Example:
        memHierarchy.Cache
        merlin.hr_router
    """
    element = getattr(node.component, "element", "") or ""
    name = getattr(node.component, "name", "") or ""

    element = str(element).strip()
    name = str(name).strip()

    if not name:
        raise SSTJsonExportError(
            f"Component instance '{node.instance_name}' has no component type name."
        )

    if not element:
        return name

    return f"{element}.{name}"


def _build_partition(node) -> dict[str, int] | None:
    """
    Optional SST partition metadata.

    FUSE does not need to emit this yet unless you later add rank/thread fields
    to the properties panel. This function already supports common attribute
    names so future UI additions do not require rewriting the exporter.
    """
    rank = getattr(node, "rank", None)
    thread = getattr(node, "thread", None)

    if rank is None and thread is None:
        return None

    return {
        "rank": int(rank or 0),
        "thread": int(thread or 0),
    }


def build_sst_component(node) -> dict[str, Any]:
    """
    Build one SST JSON component object.

    Field order matters for readability and is also safer for SST's streaming
    reader behavior: name and type are emitted first.
    """
    component: dict[str, Any] = {
        "name": node.instance_name,
        "type": sst_component_type_for_node(node),
    }

    params = _non_empty_params(getattr(node, "parameters", {}) or {})

    if params:
        component["params"] = params

    partition = _build_partition(node)

    if partition is not None:
        component["partition"] = partition

    return component


def build_sst_component_tree(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """
    Build a component/subcomponent tree for SST JSON export.

    Attached child subcomponents are nested under their parent with the slot
    name that should be used by SST's subcomponent assignment mechanism.
    """
    component = build_sst_component(node)
    children = []

    for attachment in attachments_by_parent_id.get(node.node_id, []):
        child = nodes_by_id.get(attachment.child_node_id)
        if child is None:
            raise SSTJsonExportError(
                f"Cannot export subcomponent attachment '{attachment.name}': "
                f"missing child node {attachment.child_node_id}."
            )

        child_json = build_sst_component_tree(
            child,
            attachments_by_parent_id,
            nodes_by_id,
        )
        child_json["slot_name"] = attachment.slot_name
        children.append(child_json)

    if children:
        component["subcomponents"] = children

    return component


def _source_link_latency(link) -> str:
    latency = (
        getattr(link, "source_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def _target_link_latency(link) -> str:
    latency = (
        getattr(link, "target_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def build_sst_link(link) -> dict[str, Any]:
    """
    Build one SST JSON link object.

    This assumes FUSE links are point-to-point for the initial exporter. If
    FUSE later supports multi-endpoint bus-style links, those should either be
    expanded into point-to-point SST links or handled by a plugin-specific
    bus/export rule.
    """
    name = getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}"
    source_latency = _source_link_latency(link)
    target_latency = _target_link_latency(link)

    source_component = getattr(link, "source_component_name", "") or ""
    source_port = getattr(link, "source_port", "") or ""
    target_component = getattr(link, "target_component_name", "") or ""
    target_port = getattr(link, "target_port", "") or ""

    missing = []

    if not source_component:
        missing.append("source component")
    if not source_port:
        missing.append("source port")
    if not target_component:
        missing.append("target component")
    if not target_port:
        missing.append("target port")

    if missing:
        raise SSTJsonExportError(
            f"Cannot export link '{name}': missing {', '.join(missing)}."
        )

    return {
        "name": name,
        "noCut": bool(getattr(link, "no_cut", False)),
        "nonlocal": bool(getattr(link, "nonlocal_link", False)),
        "left": {
            "component": source_component,
            "port": source_port,
            "latency": source_latency,
        },
        "right": {
            "component": target_component,
            "port": target_port,
            "latency": target_latency,
        },
    }


def build_sst_json_dict(
    scene,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Build the SST JSON configuration dictionary from the current FUSE scene.

    This is intentionally separate from writing the file so tests can assert
    on the generated dictionary directly.
    """
    nodes = scene.component_items()
    nodes_by_id = {node.node_id: node for node in nodes}

    attachments = list(getattr(scene, "subcomp_attachments", []))
    attached_child_ids = {attachment.child_node_id for attachment in attachments}
    attachments_by_parent_id: dict[int, list] = {}

    for attachment in attachments:
        attachments_by_parent_id.setdefault(
            attachment.parent_node_id,
            [],
        ).append(attachment)

    components = [
        build_sst_component_tree(node, attachments_by_parent_id, nodes_by_id)
        for node in nodes
        if node.node_id not in attached_child_ids
    ]

    links = [
        build_sst_link(link)
        for link in getattr(scene, "links", [])
    ]

    return {
        "program_options": program_options or {},
        "shared_params": shared_params or [],
        "statistics_options": statistics_options or {},
        "components": components,
        "statistics_group": statistics_group or [],
        "links": links,
    }


def export_sst_json(
    scene,
    output_path: str | Path,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
) -> Path:
    """
    Export the current FUSE scene to an SST JSON configuration file.
    """
    output_path = Path(output_path)

    data = build_sst_json_dict(
        scene=scene,
        program_options=program_options,
        statistics_options=statistics_options,
        shared_params=shared_params,
        statistics_group=statistics_group,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    return output_path