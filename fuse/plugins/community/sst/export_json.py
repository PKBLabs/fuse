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


def _link_latency(link) -> str:
    latency = getattr(link, "latency", "") or DEFAULT_LINK_LATENCY
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
    latency = _link_latency(link)

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
            "latency": latency,
        },
        "right": {
            "component": target_component,
            "port": target_port,
            "latency": latency,
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
    components = [
        build_sst_component(node)
        for node in scene.component_items()
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