# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from copy import deepcopy
from typing import Any

from fuse.core.model.composite import CompositePortMapping


def next_available_integer(used_values: set[int], preferred_value: int, fallback_value: int) -> int:
    candidate = preferred_value if preferred_value > 0 else fallback_value
    if candidate <= 0:
        candidate = 1
    while candidate in used_values:
        candidate += 1
    used_values.add(candidate)
    return candidate


def remap_link_endpoint(
    endpoint: dict[str, Any],
    component_id_map: dict[int, int],
    component_id_name_map: dict[tuple[int, str], int],
) -> None:
    if not isinstance(endpoint, dict):
        return
    try:
        old_node_id = int(endpoint.get("nodeId", 0) or 0)
    except (TypeError, ValueError):
        return

    component_name = str(endpoint.get("componentName", "") or "")
    name_specific_id = component_id_name_map.get((old_node_id, component_name))
    if name_specific_id is not None:
        endpoint["nodeId"] = name_specific_id
    elif old_node_id in component_id_map:
        endpoint["nodeId"] = component_id_map[old_node_id]


def remap_subcomp_endpoint(
    endpoint: dict[str, Any],
    component_id_map: dict[int, int],
    component_id_name_map: dict[tuple[int, str], int],
) -> None:
    remap_link_endpoint(endpoint, component_id_map, component_id_name_map)


def normalize_port_mapping_ids(
    port_mappings: list[Any],
    component_id_map: dict[int, int],
) -> list[CompositePortMapping]:
    normalized: list[CompositePortMapping] = []
    for mapping_data in port_mappings or []:
        if isinstance(mapping_data, CompositePortMapping):
            mapping = deepcopy(mapping_data)
        elif isinstance(mapping_data, dict):
            mapping = CompositePortMapping.from_dict(mapping_data)
        else:
            continue
        mapping.internal_node_id = component_id_map.get(
            int(mapping.internal_node_id),
            int(mapping.internal_node_id),
        )
        normalized.append(mapping)
    return normalized


def normalize_serialized_port_mapping_ids(
    port_mappings: list[Any],
    component_id_map: dict[int, int],
) -> list[dict[str, Any]]:
    return [
        mapping.to_dict()
        for mapping in normalize_port_mapping_ids(port_mappings, component_id_map)
    ]


def normalize_composite_instance_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}

    normalized_payload = deepcopy(payload)
    mini_model = normalized_payload.get("miniModel", {}) or {}
    port_mappings = normalized_payload.get("portMappings", []) or []
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        mini_model,
        port_mappings,
    )
    normalized_payload["miniModel"] = normalized_model
    normalized_payload["portMappings"] = [mapping.to_dict() for mapping in normalized_mappings]
    return normalized_payload


def normalize_mini_model_and_port_mappings(
    mini_model: dict[str, Any],
    port_mappings: list[Any] | None = None,
) -> tuple[dict[str, Any], list[CompositePortMapping]]:
    """Return a mini-model whose component/link/attachment ids are unique.

    Composite mini-models can be assembled from copied component fragments. Nested
    composite instances may therefore carry ids that were valid in their original
    scene but collide inside the new mini-model. The editor and serializer expect
    a mini-model to look like a valid project fragment, so ids and all references
    are normalized before the fragment is loaded, saved, or flattened.
    """
    normalized_model = deepcopy(mini_model or {})
    components = normalized_model.get("components", []) or []
    links = normalized_model.get("links", []) or []
    attachments = normalized_model.get("subcompAttachments", []) or []

    used_component_ids: set[int] = set()
    component_id_map: dict[int, int] = {}
    component_id_name_map: dict[tuple[int, str], int] = {}
    next_component_id = 1

    for component in components:
        if not isinstance(component, dict):
            continue
        try:
            old_id = int(component.get("id", 0) or 0)
        except (TypeError, ValueError):
            old_id = 0
        new_id = next_available_integer(used_component_ids, old_id, next_component_id)
        component["id"] = new_id
        component_id_map.setdefault(old_id, new_id)
        instance_name = str(component.get("instanceName") or component.get("name") or "")
        if instance_name:
            component_id_name_map[(old_id, instance_name)] = new_id
        next_component_id = max(next_component_id, new_id + 1)

        composite_instance = component.get("compositeInstance", {}) or {}
        if isinstance(composite_instance, dict) and composite_instance:
            component["compositeInstance"] = normalize_composite_instance_payload(composite_instance)

    used_link_ids: set[int] = set()
    next_link_id = 1
    for link in links:
        if not isinstance(link, dict):
            continue
        try:
            old_link_id = int(link.get("id", 0) or 0)
        except (TypeError, ValueError):
            old_link_id = 0
        new_link_id = next_available_integer(used_link_ids, old_link_id, next_link_id)
        link["id"] = new_link_id
        next_link_id = max(next_link_id, new_link_id + 1)
        remap_link_endpoint(link.get("source", {}) or {}, component_id_map, component_id_name_map)
        remap_link_endpoint(link.get("target", {}) or {}, component_id_map, component_id_name_map)

    used_attachment_ids: set[int] = set()
    next_attachment_id = 1
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        try:
            old_attachment_id = int(attachment.get("id", 0) or 0)
        except (TypeError, ValueError):
            old_attachment_id = 0
        new_attachment_id = next_available_integer(
            used_attachment_ids,
            old_attachment_id,
            next_attachment_id,
        )
        attachment["id"] = new_attachment_id
        next_attachment_id = max(next_attachment_id, new_attachment_id + 1)
        remap_subcomp_endpoint(attachment.get("parent", {}) or {}, component_id_map, component_id_name_map)
        remap_subcomp_endpoint(attachment.get("child", {}) or {}, component_id_map, component_id_name_map)

    normalized_model["components"] = components
    normalized_model["links"] = links
    normalized_model["subcompAttachments"] = attachments
    normalized_mappings = normalize_port_mapping_ids(port_mappings or [], component_id_map)
    return normalized_model, normalized_mappings


def normalize_mini_model(mini_model: dict[str, Any]) -> dict[str, Any]:
    normalized_model, ignored_mappings = normalize_mini_model_and_port_mappings(mini_model, [])
    return normalized_model
