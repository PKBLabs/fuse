# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Build composite component definitions from canvas selections.

This module converts selected ``ComponentNodeItem`` objects and their internal
connections into reusable ``CompositeComponentDefinition`` records. It is used
by the main editor when the user groups part of a model into a composite and
needs to replace that selection with a single composite instance.

The builder works at the UI/model boundary: it reads selected Qt graphics items,
serializes them into the same mini-model shape used by persistence, derives
boundary port mappings, and constructs the component definition shown in the
palette.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QPointF

from fuse.core.model.composite import (
    COMPOSITE_CATEGORY,
    COMPOSITE_ELEMENT,
    COMPOSITE_PLUGIN_ID,
    COMPOSITE_TARGET_ID,
    CompositeComponentDefinition,
    CompositePortMapping,
)
from fuse.core.model.models import ComponentDefinition
from fuse.core.model.composite_mini_model import normalize_mini_model_and_port_mappings
from fuse.core.persistence.project_io import (
    component_node_to_save_dict,
    model_link_to_save_dict,
    subcomp_attachment_to_save_dict,
)
from fuse.core.ui.graphics_items import (
    ComponentNodeItem,
    ConnectionItem,
    SubcompAttachmentItem,
)


@dataclass(frozen=True)
class CompositeSelectionBoundaryReport:
    """Summary of selected items that still connect to the outside model.

    A selection with boundary connections cannot be naively replaced by a
    composite without either exposing boundary ports or removing those external
    relationships. The report lets the UI warn the user before conversion.
    """
    boundary_connections: list[ConnectionItem]
    boundary_attachments: list[SubcompAttachmentItem]

    @property
    def has_boundary_items(self) -> bool:
        return bool(self.boundary_connections or self.boundary_attachments)


@dataclass(frozen=True)
class CompositeSelectionFragment:
    """Serialized mini-model produced from a selected set of components.

    The fragment contains the normalized internal model, derived composite port
    mappings, and the original canvas origin used to position the replacement
    composite instance.
    """
    mini_model: dict[str, Any]
    port_mappings: list[CompositePortMapping]
    origin: QPointF


def selection_boundary_report(
    scene,
    components: list[ComponentNodeItem],
    internal_connections: list[ConnectionItem],
    internal_attachments: list[SubcompAttachmentItem],
) -> CompositeSelectionBoundaryReport:
    """Identify external links or attachments touching a component selection.

    Args:
        scene: Scene containing the selected items.
        components: Component nodes selected for conversion.
        internal_connections: Connections fully contained in the selection.
        internal_attachments: Subcomponent attachments fully contained in the selection.

    Returns:
        Report listing selected-boundary relationships that would be affected
        by composite creation.
    """
    component_set = set(components)
    internal_connection_set = set(internal_connections)
    internal_attachment_set = set(internal_attachments)

    boundary_connections = [
        connection
        for connection in scene.connection_items()
        if connection not in internal_connection_set
        and (
            connection.source_port.node in component_set
            or connection.target_port.node in component_set
        )
    ]

    boundary_attachments = [
        attachment
        for attachment in scene.subcomp_attachment_items()
        if attachment not in internal_attachment_set
        and (
            attachment.source_connector.node in component_set
            or attachment.target_connector.node in component_set
        )
    ]

    return CompositeSelectionBoundaryReport(
        boundary_connections=boundary_connections,
        boundary_attachments=boundary_attachments,
    )


def selected_fragment_origin(components: list[ComponentNodeItem]) -> QPointF:
    """Return the upper-left origin used to normalize selected node positions."""
    if not components:
        return QPointF(0.0, 0.0)

    return QPointF(
        min(component.pos().x() for component in components),
        min(component.pos().y() for component in components),
    )


def normalized_component_dict(
    component: ComponentNodeItem,
    origin: QPointF,
) -> dict[str, Any]:
    """Serialize a selected component relative to the composite fragment origin."""
    saved = component_node_to_save_dict(component)
    position = saved.setdefault("position", {})
    position["x"] = float(position.get("x", 0.0)) - origin.x()
    position["y"] = float(position.get("y", 0.0)) - origin.y()
    return saved


def external_port_name(
    component: ComponentNodeItem,
    port_name: str,
    used_names: set[str],
) -> str:
    """Generate the public composite port name for an internal port mapping."""
    base = f"{component.instance_name}.{port_name}"
    candidate = base
    index = 2

    while candidate in used_names:
        candidate = f"{base}_{index}"
        index += 1

    used_names.add(candidate)
    return candidate


def composite_port_mappings_for_fragment(
    components: list[ComponentNodeItem],
    internal_connections: list[ConnectionItem],
) -> list[CompositePortMapping]:
    """Create composite boundary-port mappings for a selected mini-model.

    The mappings describe which internal component ports should be exposed on
    the composite boundary and preserve enough identity information to reconnect
    the composite during editing and export flattening.
    """
    internally_connected_ports = set()

    for connection in internal_connections:
        internally_connected_ports.add(connection.source_port)
        internally_connected_ports.add(connection.target_port)

    mappings: list[CompositePortMapping] = []
    used_external_names: set[str] = set()

    for component in sorted(components, key=lambda item: item.node_id):
        for port in component.ports:
            if port in internally_connected_ports:
                continue

            metadata = getattr(port, "metadata", {}) or {}
            mappings.append(
                CompositePortMapping(
                    external_port_name=external_port_name(component, port.name, used_external_names),
                    internal_node_id=component.node_id,
                    internal_component_name=component.instance_name,
                    internal_port_name=port.name,
                    side=getattr(port, "side", "") or "",
                    iface=(
                        getattr(port, "interface", "")
                        or metadata.get("iface", "")
                        or metadata.get("interface", "")
                        or ""
                    ),
                    description=str(metadata.get("description", "") or ""),
                    exposed=False,
                )
            )

    return mappings


def build_composite_fragment(
    components: list[ComponentNodeItem],
    internal_connections: list[ConnectionItem],
    internal_attachments: list[SubcompAttachmentItem],
) -> CompositeSelectionFragment:
    """Serialize selected canvas items into a normalized composite mini-model."""
    ordered_components = sorted(components, key=lambda item: item.node_id)
    ordered_connections = sorted(internal_connections, key=lambda item: item.link.link_id)
    ordered_attachments = sorted(
        internal_attachments,
        key=lambda item: item.attachment.attachment_id,
    )
    origin = selected_fragment_origin(ordered_components)

    mini_model = {
        "schemaVersion": "0.1.0",
        "kind": "fuse.composite-mini-model",
        "origin": {"x": origin.x(), "y": origin.y()},
        "components": [
            normalized_component_dict(component, origin)
            for component in ordered_components
        ],
        "links": [
            model_link_to_save_dict(connection.link)
            for connection in ordered_connections
        ],
        "subcompAttachments": [
            subcomp_attachment_to_save_dict(attachment.attachment)
            for attachment in ordered_attachments
        ],
    }

    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        mini_model,
        composite_port_mappings_for_fragment(
            ordered_components,
            ordered_connections,
        ),
    )

    return CompositeSelectionFragment(
        mini_model=normalized_model,
        port_mappings=normalized_mappings,
        origin=origin,
    )


def build_composite_definition_from_selection(
    name: str,
    icon_path: str,
    components: list[ComponentNodeItem],
    internal_connections: list[ConnectionItem],
    internal_attachments: list[SubcompAttachmentItem],
    description: str = "",
) -> CompositeComponentDefinition:
    """Create a reusable composite component definition from a canvas selection."""
    fragment = build_composite_fragment(
        components,
        internal_connections,
        internal_attachments,
    )

    return CompositeComponentDefinition.make(
        name=name.strip(),
        description=description.strip(),
        icon_path=icon_path.strip(),
        mini_model=fragment.mini_model,
        port_mappings=fragment.port_mappings,
    )


def component_definition_for_composite(
    definition: CompositeComponentDefinition,
) -> ComponentDefinition:
    """Create the palette/canvas component definition for a composite template."""
    return ComponentDefinition(
        plugin_id=COMPOSITE_PLUGIN_ID,
        target_id=COMPOSITE_TARGET_ID,
        target_label="FUSE Composite Components",
        framework_version=definition.schema_version,
        component_id=definition.composite_id,
        element=COMPOSITE_ELEMENT,
        name=definition.name,
        is_subcomp=0,
        category=COMPOSITE_CATEGORY,
        functionality="Reusable mini-model",
        description=definition.description,
        icon_path=definition.icon_path,
        display_name_override=f"{definition.name} (Composite)",
        is_composite=1,
        composite_id=definition.composite_id,
    )


def replace_selection_with_composite_instance(
    scene,
    definition: CompositeComponentDefinition,
    components: list[ComponentNodeItem],
    internal_connections: list[ConnectionItem],
    internal_attachments: list[SubcompAttachmentItem],
) -> ComponentNodeItem:
    """Replace selected nodes and internal links with one composite instance."""
    origin = selected_fragment_origin(components)

    for connection in list(internal_connections):
        if connection.scene() is scene:
            scene.delete_link(connection)

    for attachment in list(internal_attachments):
        if attachment.scene() is scene:
            scene.delete_subcomp_attachment(attachment)

    for component in sorted(components, key=lambda item: item.node_id):
        if component.scene() is scene:
            scene.delete_component_node(component)

    composite_component = component_definition_for_composite(definition)
    composite_node = scene.create_component_node(composite_component, origin)
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        definition.mini_model or {},
        definition.port_mappings,
    )
    composite_node.composite_instance_model = normalized_model
    composite_node.composite_port_mappings = normalized_mappings
    composite_node.sync_composite_ports_from_mappings()
    composite_node.setSelected(True)
    return composite_node
