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
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment
from fuse.core.persistence.composite_components import get_composite_component_definition
from fuse.core.model.composite import CompositePortMapping
from fuse.core.model.composite_mini_model import normalize_mini_model_and_port_mappings


@dataclass(frozen=True)
class FlattenedEndpoint:
    node_id: int
    component_name: str
    port_name: str


@dataclass
class FlattenedPort:
    name: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlattenedComponentNode:
    component: ComponentDefinition
    node_id: int
    instance_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    variable_port_counts: dict[str, int] = field(default_factory=dict)
    ports: list[FlattenedPort] = field(default_factory=list)

    def expanded_port_names(self) -> list[str]:
        if self.ports:
            return [port.name for port in self.ports]

        from fuse.core.persistence.db_access import load_port_metadata_for_component

        metadata = load_port_metadata_for_component(
            self.component.plugin_id,
            self.component.component_id,
            self.component.target_id,
        )
        names: list[str] = []

        for template in metadata:
            if bool(template.get("is_variable")):
                base_name = template.get("base_name", "") or template.get("name", "")
                count = int(self.variable_port_counts.get(base_name, template.get("default_count", 1)) or 0)
                names.extend(f"{base_name}{index}" for index in range(max(0, count)))
            else:
                name = template.get("name", "")
                if name:
                    names.append(str(name))

        return names


@dataclass
class FlattenedScene:
    nodes: list[FlattenedComponentNode]
    links: list[ModelLink]
    subcomp_attachments: list[ModelSubcompAttachment]
    active_plugin_id: str = ""

    def component_items(self) -> list[FlattenedComponentNode]:
        return sorted(self.nodes, key=lambda node: int(node.node_id))


@dataclass
class CompositeExpansion:
    nodes: list[FlattenedComponentNode] = field(default_factory=list)
    links: list[ModelLink] = field(default_factory=list)
    subcomp_attachments: list[ModelSubcompAttachment] = field(default_factory=list)
    external_endpoints: dict[str, FlattenedEndpoint] = field(default_factory=dict)


class CompositeExpansionState:
    def __init__(self, scene) -> None:
        self.next_node_id = max([int(getattr(node, "node_id", 0)) for node in scene.component_items()] + [0]) + 1
        self.next_link_id = max([int(getattr(link, "link_id", 0)) for link in getattr(scene, "links", [])] + [0]) + 1
        self.next_attachment_id = max(
            [int(getattr(attachment, "attachment_id", 0)) for attachment in getattr(scene, "subcomp_attachments", [])]
            + [0]
        ) + 1
        self.composite_instance_index = 0
        self.used_component_names = {
            str(getattr(node, "instance_name", "") or "")
            for node in scene.component_items()
            if not component_is_composite(node)
        }

    def allocate_node_id(self) -> int:
        node_id = self.next_node_id
        self.next_node_id += 1
        return node_id

    def allocate_link_id(self) -> int:
        link_id = self.next_link_id
        self.next_link_id += 1
        return link_id

    def allocate_attachment_id(self) -> int:
        attachment_id = self.next_attachment_id
        self.next_attachment_id += 1
        return attachment_id

    def next_composite_suffix(self) -> str:
        self.composite_instance_index += 1
        return f"mc{self.composite_instance_index}"

    def unique_component_name(self, base_name: str) -> str:
        candidate = base_name
        index = 2
        while candidate in self.used_component_names:
            candidate = f"{base_name}_{index}"
            index += 1
        self.used_component_names.add(candidate)
        return candidate


def component_is_composite(node) -> bool:
    component = getattr(node, "component", None)
    return bool(int(getattr(component, "is_composite", 0) or 0))


def component_definition_from_save_dict(data: dict[str, Any]) -> ComponentDefinition:
    return ComponentDefinition(
        plugin_id=data.get("pluginId", data.get("plugin_id", "core")),
        target_id=data.get("targetId", data.get("target_id", "")),
        target_label=data.get("targetLabel", ""),
        framework_version=data.get("frameworkVersion", ""),
        component_id=data.get("componentId"),
        element=data.get("element", ""),
        name=data.get("name", ""),
        is_subcomp=int(data.get("isSubcomponent", data.get("is_subcomp", 0)) or 0),
        category=data.get("category", ""),
        functionality=data.get("functionality", ""),
        description=data.get("description", ""),
        iface=data.get("interface", data.get("iface", "")),
        icon_path=data.get("iconPath", data.get("icon_path", "")),
        display_name_override=data.get("displayNameOverride", ""),
        is_composite=int(data.get("isComposite", 0) or 0),
        composite_id=data.get("compositeId", "") or "",
    )


def flattened_ports_for_node(component: ComponentDefinition, variable_port_counts: dict[str, int]) -> list[FlattenedPort]:
    if int(getattr(component, "is_composite", 0) or 0):
        return []

    try:
        from fuse.core.persistence.db_access import load_port_metadata_for_component

        templates = load_port_metadata_for_component(
            component.plugin_id,
            component.component_id,
            component.target_id,
        )
    except Exception:
        templates = []

    ports: list[FlattenedPort] = []
    for template in templates:
        if bool(template.get("is_variable")):
            base_name = template.get("base_name", "") or template.get("name", "")
            count = int(variable_port_counts.get(base_name, template.get("default_count", 1)) or 0)
            for index in range(max(0, count)):
                ports.append(FlattenedPort(f"{base_name}{index}", dict(template)))
        else:
            name = str(template.get("name", "") or "")
            if name:
                ports.append(FlattenedPort(name, dict(template)))
    return ports


def copied_existing_node(node) -> FlattenedComponentNode:
    component = getattr(node, "component")
    ports = [
        FlattenedPort(
            str(getattr(port, "name", "") or ""),
            dict(getattr(port, "metadata", {}) or {}),
        )
        for port in getattr(node, "ports", [])
        if str(getattr(port, "name", "") or "")
    ]
    return FlattenedComponentNode(
        component=component,
        node_id=int(getattr(node, "node_id")),
        instance_name=str(getattr(node, "instance_name", "") or ""),
        parameters=dict(getattr(node, "parameters", {}) or {}),
        variable_port_counts=dict(getattr(node, "variable_port_counts", {}) or {}),
        ports=ports,
    )


def endpoint_for_component_port(
    original_node_id: int,
    port_name: str,
    direct_endpoints: dict[tuple[int, str], FlattenedEndpoint],
    composite_endpoints: dict[tuple[int, str], FlattenedEndpoint],
) -> FlattenedEndpoint:
    composite_endpoint = composite_endpoints.get((int(original_node_id), port_name))
    if composite_endpoint is not None:
        return composite_endpoint

    direct_endpoint = direct_endpoints.get((int(original_node_id), port_name))
    if direct_endpoint is not None:
        return direct_endpoint

    raise ValueError(
        f"Could not resolve composite endpoint {original_node_id}.{port_name}."
    )


def model_link_from_dict(data: dict[str, Any]) -> ModelLink:
    source = data.get("source", {}) or {}
    target = data.get("target", {}) or {}
    compatibility = data.get("compatibility", {}) or {}
    legacy_latency = data.get("latency", "1ns")
    return ModelLink(
        link_id=int(data.get("id", 0) or 0),
        name=str(data.get("name", "") or ""),
        source_node_id=int(source.get("nodeId", 0) or 0),
        source_component_name=str(source.get("componentName", "") or ""),
        source_port=str(source.get("port", "") or ""),
        target_node_id=int(target.get("nodeId", 0) or 0),
        target_component_name=str(target.get("componentName", "") or ""),
        target_port=str(target.get("port", "") or ""),
        source_latency=str(data.get("sourceLatency", legacy_latency) or "1ns"),
        target_latency=str(data.get("targetLatency", legacy_latency) or "1ns"),
        link_type=str(data.get("type", "point_to_point") or "point_to_point"),
        plugin_id=str(data.get("pluginId", "") or ""),
        compatibility_severity=str(compatibility.get("severity", "ok") or "ok"),
        compatibility_code=str(compatibility.get("code", "") or ""),
        compatibility_message=str(compatibility.get("message", "") or ""),
        plugin_metadata=data.get("pluginMetadata", {}) or {},
    )


def model_subcomp_attachment_from_dict(data: dict[str, Any]) -> ModelSubcompAttachment:
    parent = data.get("parent", {}) or {}
    child = data.get("child", {}) or {}
    compatibility = data.get("compatibility", {}) or {}
    return ModelSubcompAttachment(
        attachment_id=int(data.get("id", 0) or 0),
        name=str(data.get("name", "") or ""),
        parent_node_id=int(parent.get("nodeId", 0) or 0),
        parent_component_name=str(parent.get("componentName", "") or ""),
        slot_name=str(parent.get("slotName", "") or ""),
        child_node_id=int(child.get("nodeId", 0) or 0),
        child_component_name=str(child.get("componentName", "") or ""),
        required_interface=str(data.get("requiredInterface", "") or ""),
        provided_interface=str(data.get("providedInterface", "") or ""),
        plugin_id=str(data.get("pluginId", "") or ""),
        compatibility_severity=str(compatibility.get("severity", "ok") or "ok"),
        compatibility_code=str(compatibility.get("code", "") or ""),
        compatibility_message=str(compatibility.get("message", "") or ""),
        plugin_metadata=data.get("pluginMetadata", {}) or {},
    )


def expand_composite_instance(
    node,
    state: CompositeExpansionState,
    expansion_stack: list[str] | None = None,
) -> CompositeExpansion:
    expansion_stack = list(expansion_stack or [])
    component = getattr(node, "component")
    composite_id = getattr(component, "composite_id", "") or getattr(component, "component_id", "") or ""

    if not composite_id:
        raise ValueError(f"Composite instance '{getattr(node, 'instance_name', '<unnamed>')}' has no composite template id.")

    if composite_id in expansion_stack:
        cycle = " -> ".join(expansion_stack + [composite_id])
        raise ValueError(f"Composite expansion cycle detected: {cycle}")

    definition = get_composite_component_definition(str(composite_id))
    if definition is None:
        raise ValueError(f"Composite definition '{composite_id}' was not found in local storage.")

    raw_mini_model = getattr(node, "composite_instance_model", {}) or definition.mini_model or {}
    instance_mappings = getattr(node, "composite_port_mappings", []) or []
    raw_port_mappings = instance_mappings if instance_mappings else definition.port_mappings
    mini_model, port_mappings = normalize_mini_model_and_port_mappings(
        raw_mini_model,
        raw_port_mappings,
    )

    suffix = state.next_composite_suffix()
    direct_endpoints: dict[tuple[int, str], FlattenedEndpoint] = {}
    composite_endpoints: dict[tuple[int, str], FlattenedEndpoint] = {}
    original_node_to_expanded_node: dict[int, FlattenedComponentNode] = {}
    expansion = CompositeExpansion()

    for component_data in sorted(mini_model.get("components", []) or [], key=lambda item: int(item.get("id", 0) or 0)):
        original_node_id = int(component_data.get("id", 0) or 0)
        component_definition = component_definition_from_save_dict(component_data)
        base_instance_name = str(component_data.get("instanceName", component_data.get("name", "Component")) or "Component")
        instance_name = state.unique_component_name(f"{base_instance_name}_{suffix}")

        child_node = FlattenedComponentNode(
            component=component_definition,
            node_id=state.allocate_node_id(),
            instance_name=instance_name,
            parameters=dict(component_data.get("parameters", {}) or {}),
            variable_port_counts=dict(component_data.get("variablePortCounts", {}) or {}),
            ports=[],
        )

        if int(getattr(component_definition, "is_composite", 0) or 0):
            nested_expansion = expand_composite_instance(
                child_node,
                state,
                expansion_stack + [str(composite_id)],
            )
            expansion.nodes.extend(nested_expansion.nodes)
            expansion.links.extend(nested_expansion.links)
            expansion.subcomp_attachments.extend(nested_expansion.subcomp_attachments)
            for port_name, endpoint in nested_expansion.external_endpoints.items():
                composite_endpoints[(original_node_id, port_name)] = endpoint
        else:
            child_node.ports = flattened_ports_for_node(
                component_definition,
                child_node.variable_port_counts,
            )
            expansion.nodes.append(child_node)
            original_node_to_expanded_node[original_node_id] = child_node
            for port_name in child_node.expanded_port_names():
                direct_endpoints[(original_node_id, port_name)] = FlattenedEndpoint(
                    child_node.node_id,
                    child_node.instance_name,
                    port_name,
                )

    for link_data in sorted(mini_model.get("links", []) or [], key=lambda item: int(item.get("id", 0) or 0)):
        link = model_link_from_dict(link_data)
        source_endpoint = endpoint_for_component_port(
            link.source_node_id,
            link.source_port,
            direct_endpoints,
            composite_endpoints,
        )
        target_endpoint = endpoint_for_component_port(
            link.target_node_id,
            link.target_port,
            direct_endpoints,
            composite_endpoints,
        )
        expansion.links.append(
            ModelLink(
                link_id=state.allocate_link_id(),
                name=str(link.name or f"link_{source_endpoint.component_name}_{target_endpoint.component_name}"),
                source_node_id=source_endpoint.node_id,
                source_component_name=source_endpoint.component_name,
                source_port=source_endpoint.port_name,
                target_node_id=target_endpoint.node_id,
                target_component_name=target_endpoint.component_name,
                target_port=target_endpoint.port_name,
                source_latency=link.source_latency,
                target_latency=link.target_latency,
                link_type=link.link_type,
                plugin_id=link.plugin_id,
                compatibility_severity=link.compatibility_severity,
                compatibility_code=link.compatibility_code,
                compatibility_message=link.compatibility_message,
                plugin_metadata=dict(link.plugin_metadata or {}),
            )
        )

    for attachment_data in sorted(mini_model.get("subcompAttachments", []) or [], key=lambda item: int(item.get("id", 0) or 0)):
        attachment = model_subcomp_attachment_from_dict(attachment_data)
        parent = original_node_to_expanded_node.get(attachment.parent_node_id)
        child = original_node_to_expanded_node.get(attachment.child_node_id)
        if parent is None or child is None:
            raise ValueError(
                f"Composite subcomponent attachment '{attachment.name}' references a nested composite or missing node."
            )
        expansion.subcomp_attachments.append(
            ModelSubcompAttachment(
                attachment_id=state.allocate_attachment_id(),
                name=attachment.name,
                parent_node_id=parent.node_id,
                parent_component_name=parent.instance_name,
                slot_name=attachment.slot_name,
                child_node_id=child.node_id,
                child_component_name=child.instance_name,
                required_interface=attachment.required_interface,
                provided_interface=attachment.provided_interface,
                plugin_id=attachment.plugin_id,
                compatibility_severity=attachment.compatibility_severity,
                compatibility_code=attachment.compatibility_code,
                compatibility_message=attachment.compatibility_message,
                plugin_metadata=dict(attachment.plugin_metadata or {}),
            )
        )

    for mapping in port_mappings:
        expansion.external_endpoints[mapping.external_port_name] = endpoint_for_component_port(
            mapping.internal_node_id,
            mapping.internal_port_name,
            direct_endpoints,
            composite_endpoints,
        )

    return expansion


def copied_existing_link(link: ModelLink) -> ModelLink:
    return ModelLink(
        link_id=int(link.link_id),
        name=link.name,
        source_node_id=int(link.source_node_id),
        source_component_name=link.source_component_name,
        source_port=link.source_port,
        target_node_id=int(link.target_node_id),
        target_component_name=link.target_component_name,
        target_port=link.target_port,
        source_latency=link.source_latency,
        target_latency=link.target_latency,
        link_type=link.link_type,
        plugin_id=link.plugin_id,
        compatibility_severity=link.compatibility_severity,
        compatibility_code=link.compatibility_code,
        compatibility_message=link.compatibility_message,
        plugin_metadata=dict(link.plugin_metadata or {}),
    )


def copied_existing_attachment(attachment: ModelSubcompAttachment) -> ModelSubcompAttachment:
    return ModelSubcompAttachment(
        attachment_id=int(attachment.attachment_id),
        name=attachment.name,
        parent_node_id=int(attachment.parent_node_id),
        parent_component_name=attachment.parent_component_name,
        slot_name=attachment.slot_name,
        child_node_id=int(attachment.child_node_id),
        child_component_name=attachment.child_component_name,
        required_interface=attachment.required_interface,
        provided_interface=attachment.provided_interface,
        plugin_id=attachment.plugin_id,
        compatibility_severity=attachment.compatibility_severity,
        compatibility_code=attachment.compatibility_code,
        compatibility_message=attachment.compatibility_message,
        plugin_metadata=dict(attachment.plugin_metadata or {}),
    )


def flatten_scene_for_export(scene) -> FlattenedScene:
    if not any(component_is_composite(node) for node in scene.component_items()):
        return FlattenedScene(
            nodes=[copied_existing_node(node) for node in scene.component_items()],
            links=[copied_existing_link(link) for link in getattr(scene, "links", []) or []],
            subcomp_attachments=[
                copied_existing_attachment(attachment)
                for attachment in getattr(scene, "subcomp_attachments", []) or []
            ],
            active_plugin_id=getattr(scene, "active_plugin_id", "") or "",
        )

    state = CompositeExpansionState(scene)
    nodes: list[FlattenedComponentNode] = []
    links: list[ModelLink] = []
    attachments: list[ModelSubcompAttachment] = []
    endpoint_remap: dict[tuple[int, str], FlattenedEndpoint] = {}
    composite_node_ids: set[int] = set()

    for node in scene.component_items():
        if not component_is_composite(node):
            copied = copied_existing_node(node)
            nodes.append(copied)
            for port_name in copied.expanded_port_names():
                endpoint_remap[(copied.node_id, port_name)] = FlattenedEndpoint(
                    copied.node_id,
                    copied.instance_name,
                    port_name,
                )
            continue

        composite_node_ids.add(int(node.node_id))
        expansion = expand_composite_instance(node, state)
        nodes.extend(expansion.nodes)
        links.extend(expansion.links)
        attachments.extend(expansion.subcomp_attachments)
        for external_port_name, endpoint in expansion.external_endpoints.items():
            endpoint_remap[(int(node.node_id), external_port_name)] = endpoint

    for link in getattr(scene, "links", []) or []:
        source_endpoint = endpoint_remap.get((int(link.source_node_id), link.source_port))
        target_endpoint = endpoint_remap.get((int(link.target_node_id), link.target_port))
        if source_endpoint is None or target_endpoint is None:
            raise ValueError(f"Could not resolve link '{link.name}' while flattening composites.")

        if int(link.source_node_id) in composite_node_ids or int(link.target_node_id) in composite_node_ids:
            links.append(
                ModelLink(
                    link_id=state.allocate_link_id(),
                    name=link.name,
                    source_node_id=source_endpoint.node_id,
                    source_component_name=source_endpoint.component_name,
                    source_port=source_endpoint.port_name,
                    target_node_id=target_endpoint.node_id,
                    target_component_name=target_endpoint.component_name,
                    target_port=target_endpoint.port_name,
                    source_latency=link.source_latency,
                    target_latency=link.target_latency,
                    link_type=link.link_type,
                    plugin_id=link.plugin_id,
                    compatibility_severity=link.compatibility_severity,
                    compatibility_code=link.compatibility_code,
                    compatibility_message=link.compatibility_message,
                    plugin_metadata=dict(link.plugin_metadata or {}),
                )
            )
        else:
            links.append(copied_existing_link(link))

    for attachment in getattr(scene, "subcomp_attachments", []) or []:
        if int(attachment.parent_node_id) in composite_node_ids or int(attachment.child_node_id) in composite_node_ids:
            raise ValueError(
                f"Subcomponent attachment '{attachment.name}' cannot attach directly to a composite instance."
            )
        attachments.append(copied_existing_attachment(attachment))

    return FlattenedScene(
        nodes=nodes,
        links=links,
        subcomp_attachments=attachments,
        active_plugin_id=getattr(scene, "active_plugin_id", "") or "",
    )
