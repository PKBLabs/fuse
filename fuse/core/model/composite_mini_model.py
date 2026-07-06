# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Normalization helpers for composite component mini-model payloads.

Composite definitions store embedded model fragments. These helpers remap ids and references so copied or nested fragments remain internally consistent."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fuse.core.model.composite import CompositePortMapping
from fuse.core.model.name_generation import (
    has_name_index_token,
    next_name_from_template,
    render_name_template,
    template_for_source_name,
)


def next_available_integer(used_values: set[int], preferred_value: int, fallback_value: int) -> int:
    """Return and reserve the next unused positive integer id."""
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
    """Remap a serialized link endpoint to a normalized component id."""
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
    """Remap a serialized subcomponent endpoint to a normalized component id."""
    remap_link_endpoint(endpoint, component_id_map, component_id_name_map)


def normalize_port_mapping_ids(
    port_mappings: list[Any],
    component_id_map: dict[int, int],
    component_names_by_id: dict[int, str] | None = None,
) -> list[CompositePortMapping]:
    """Normalize composite port mappings after component ids are remapped.

    Port mappings persist both an internal node id and the component name that
    was displayed when the mapping was created. The id is authoritative. Keeping
    the stored component name synchronized with the normalized mini-model avoids
    first-open editor passes from treating an exposed port as unrelated to the
    current internal node and clearing the exposure state.
    """
    names_by_id = component_names_by_id or {}
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
        if int(mapping.internal_node_id) in names_by_id:
            mapping.internal_component_name = names_by_id[int(mapping.internal_node_id)]
        normalized.append(mapping)
    return normalized


def normalize_serialized_port_mapping_ids(
    port_mappings: list[Any],
    component_id_map: dict[int, int],
    component_names_by_id: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize serialized port mappings and return dictionaries."""
    return [
        mapping.to_dict()
        for mapping in normalize_port_mapping_ids(
            port_mappings,
            component_id_map,
            component_names_by_id,
        )
    ]


def normalize_composite_instance_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a serialized composite-instance payload."""
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
    component_names_by_new_id: dict[int, str] = {}
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
            component_names_by_new_id[new_id] = instance_name
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
    normalized_mappings = normalize_port_mapping_ids(
        port_mappings or [],
        component_id_map,
        component_names_by_new_id,
    )
    return normalized_model, normalized_mappings



def component_instance_name(component: dict[str, Any]) -> str:
    """Return the persisted instance name for a mini-model component."""
    return str(component.get("instanceName") or component.get("name") or "Component")


def collect_mini_model_component_names(mini_model: dict[str, Any]) -> set[str]:
    """Return all component instance names contained in a mini-model tree."""
    names: set[str] = set()
    if not isinstance(mini_model, dict):
        return names

    for component in mini_model.get("components", []) or []:
        if not isinstance(component, dict):
            continue
        instance_name = component_instance_name(component)
        if instance_name:
            names.add(instance_name)
        composite_instance = component.get("compositeInstance", {}) or {}
        if isinstance(composite_instance, dict):
            nested_model = composite_instance.get("miniModel", {}) or {}
            names.update(collect_mini_model_component_names(nested_model))
    return names


def _set_endpoint_component_name(
    endpoint: dict[str, Any],
    names_by_node_id: dict[int, str],
) -> None:
    """Update a serialized endpoint's componentName from its node id."""
    if not isinstance(endpoint, dict):
        return
    try:
        node_id = int(endpoint.get("nodeId", endpoint.get("node_id", 0)) or 0)
    except (TypeError, ValueError):
        return
    if node_id in names_by_node_id:
        endpoint["componentName"] = names_by_node_id[node_id]
        endpoint["component_name"] = names_by_node_id[node_id]


def _set_flat_endpoint_component_name(
    owner: dict[str, Any],
    prefix: str,
    names_by_node_id: dict[int, str],
) -> None:
    """Update older flat endpoint fields if a mini-model still contains them."""
    if not isinstance(owner, dict):
        return

    node_keys = (
        f"{prefix}NodeId",
        f"{prefix}_node_id",
        f"{prefix}ComponentId",
        f"{prefix}_component_id",
    )
    try:
        node_id = 0
        for key in node_keys:
            if key in owner:
                node_id = int(owner.get(key, 0) or 0)
                break
    except (TypeError, ValueError):
        return

    if node_id not in names_by_node_id:
        return

    for key in (
        f"{prefix}ComponentName",
        f"{prefix}_component_name",
    ):
        if key in owner:
            owner[key] = names_by_node_id[node_id]


def _replace_component_names_in_text(text: Any, replacements: dict[str, str]) -> Any:
    """Replace component-name fragments in human-facing link/attachment names."""
    if not isinstance(text, str) or not text or not replacements:
        return text

    result = text
    for old_name, new_name in sorted(
        replacements.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if old_name and new_name and old_name != new_name:
            result = result.replace(old_name, new_name)
    return result


def uniquify_mini_model_component_names(
    mini_model: dict[str, Any],
    port_mappings: list[Any] | None = None,
    used_names: set[str] | None = None,
) -> tuple[dict[str, Any], list[CompositePortMapping]]:
    """Return a mini-model whose component instance names are globally unique.

    This is used when placing or copying composite instances. It preserves a
    template's original internal names where possible, honors explicit ``%d``
    name patterns, and otherwise falls back to the core implicit ``_%d`` pattern
    when a name would collide with another component or another composite
    instance's internals.
    """
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        mini_model or {},
        port_mappings or [],
    )
    used = used_names if used_names is not None else set()
    components = normalized_model.get("components", []) or []
    names_by_node_id: dict[int, str] = {}
    renamed_component_names: dict[str, str] = {}

    for component in components:
        if not isinstance(component, dict):
            continue
        try:
            node_id = int(component.get("id", 0) or 0)
        except (TypeError, ValueError):
            node_id = 0

        old_name = component_instance_name(component)
        template = str(component.get("nameTemplate") or "")
        if not template:
            template = old_name if has_name_index_token(old_name) else template_for_source_name(old_name)

        if has_name_index_token(old_name):
            template = old_name

        # Keep explicit non-token internal names when they do not collide. If
        # they do collide, or a user supplied a token/template, generate from the
        # corresponding pattern.
        if (
            not has_name_index_token(old_name)
            and "nameTemplate" not in component
            and old_name not in used
        ):
            new_name = old_name
        else:
            start_index = 0 if old_name == render_name_template(template, 0) else 1
            new_name, _index = next_name_from_template(
                template,
                used,
                start_index=start_index,
            )

        used.add(new_name)
        component["instanceName"] = new_name
        component["nameTemplate"] = template_for_source_name(template)
        if old_name and old_name != new_name:
            renamed_component_names[old_name] = new_name
        if node_id:
            names_by_node_id[node_id] = new_name

        composite_instance = component.get("compositeInstance", {}) or {}
        if isinstance(composite_instance, dict) and composite_instance:
            nested_model = composite_instance.get("miniModel", {}) or {}
            nested_mappings = composite_instance.get("portMappings", []) or []
            nested_model, nested_mappings = uniquify_mini_model_component_names(
                nested_model,
                nested_mappings,
                used,
            )
            composite_instance["miniModel"] = nested_model
            composite_instance["portMappings"] = [
                mapping.to_dict() for mapping in nested_mappings
            ]
            component["compositeInstance"] = composite_instance

    for link in normalized_model.get("links", []) or []:
        if not isinstance(link, dict):
            continue
        _set_endpoint_component_name(link.get("source", {}) or {}, names_by_node_id)
        _set_endpoint_component_name(link.get("target", {}) or {}, names_by_node_id)
        _set_flat_endpoint_component_name(link, "source", names_by_node_id)
        _set_flat_endpoint_component_name(link, "target", names_by_node_id)
        link["name"] = _replace_component_names_in_text(
            link.get("name", ""),
            renamed_component_names,
        )

    for attachment in normalized_model.get("subcompAttachments", []) or []:
        if not isinstance(attachment, dict):
            continue
        _set_endpoint_component_name(attachment.get("parent", {}) or {}, names_by_node_id)
        _set_endpoint_component_name(attachment.get("child", {}) or {}, names_by_node_id)
        _set_flat_endpoint_component_name(attachment, "parent", names_by_node_id)
        _set_flat_endpoint_component_name(attachment, "child", names_by_node_id)
        attachment["name"] = _replace_component_names_in_text(
            attachment.get("name", ""),
            renamed_component_names,
        )

    for mapping in normalized_mappings:
        if int(mapping.internal_node_id) in names_by_node_id:
            mapping.internal_component_name = names_by_node_id[int(mapping.internal_node_id)]

    return normalized_model, normalized_mappings


def normalize_mini_model(mini_model: dict[str, Any]) -> dict[str, Any]:
    """Normalize a mini-model payload and return only the normalized model dictionary."""
    normalized_model, ignored_mappings = normalize_mini_model_and_port_mappings(mini_model, [])
    return normalized_model
