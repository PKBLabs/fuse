# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Selection helper functions shared by scene and composite UI code."""

from __future__ import annotations

from typing import Callable

from fuse.core.ui.graphics_items import (
    ComponentNodeItem,
    ConnectionItem,
    SubcompAttachmentItem,
)


def ensure_scene_selection_state(scene) -> None:
    """Ensure a scene exposes the selection attributes expected by helper functions."""
    if not hasattr(scene, "selected_component"):
        scene.selected_component = None
    if not hasattr(scene, "selected_connection"):
        scene.selected_connection = None
    if not hasattr(scene, "selected_subcomp_attachment"):
        scene.selected_subcomp_attachment = None



def selected_component_items(scene) -> list[ComponentNodeItem]:
    """Return selected component graphics items in stable node-id order."""
    selected = [
        item
        for item in scene.selectedItems()
        if isinstance(item, ComponentNodeItem)
    ]
    return sorted(selected, key=lambda item: item.node_id)


def internal_connection_items_for_components(
    scene,
    components: list[ComponentNodeItem],
) -> list[ConnectionItem]:
    """Return links whose endpoints are both inside a component selection."""
    component_set = set(components)
    return [
        connection
        for connection in scene.connection_items()
        if connection.source_port.node in component_set
        and connection.target_port.node in component_set
    ]


def internal_subcomp_attachment_items_for_components(
    scene,
    components: list[ComponentNodeItem],
) -> list[SubcompAttachmentItem]:
    """Return subcomponent attachments fully contained in a component selection."""
    component_set = set(components)
    return [
        attachment
        for attachment in scene.subcomp_attachment_items()
        if attachment.source_connector.node in component_set
        and attachment.target_connector.node in component_set
    ]


def selected_internal_connection_items(scene) -> list[ConnectionItem]:
    """Return selected links that are internal to the selected components."""
    return internal_connection_items_for_components(scene, selected_component_items(scene))


def selected_internal_subcomp_attachment_items(scene) -> list[SubcompAttachmentItem]:
    """Return selected subcomponent attachments internal to the selected components."""
    return internal_subcomp_attachment_items_for_components(scene, selected_component_items(scene))


def can_create_composite_from_selection(scene) -> bool:
    """Return whether the current selection can form a composite component."""
    return len(selected_component_items(scene)) >= 2


def is_internal_selected_connection(scene, connection: ConnectionItem) -> bool:
    """Return whether a link is internal to the current component selection."""
    return connection in selected_internal_connection_items(scene)


def request_composite_from_selection(scene, callback: Callable | None = None) -> None:
    """Invoke the composite creation callback for the current valid selection."""
    if not can_create_composite_from_selection(scene):
        return

    if callback is not None:
        callback(
            selected_component_items(scene),
            selected_internal_connection_items(scene),
            selected_internal_subcomp_attachment_items(scene),
        )


def update_selection_dependent_highlights(scene, selection_callback=None, properties_panel=None) -> None:
    """Refresh selection-dependent highlighting on links and attachments."""
    ensure_scene_selection_state(scene)
    components = selected_component_items(scene)

    if len(components) > 1:
        internal_connections = set(internal_connection_items_for_components(scene, components))
        internal_attachments = set(internal_subcomp_attachment_items_for_components(scene, components))

        for connection in scene.connection_items():
            connection.set_highlighted(connection in internal_connections)

        for attachment in scene.subcomp_attachment_items():
            attachment.set_highlighted(attachment in internal_attachments)

        scene.selected_component = None
        scene.selected_connection = None
        scene.selected_subcomp_attachment = None

        if selection_callback is not None:
            selection_callback(None)
        return

    if len(components) == 1:
        node = components[0]
        scene.selected_component = node
        scene.selected_connection = None
        scene.selected_subcomp_attachment = None
        scene.highlight_links_for_node(node)

        panel = properties_panel if properties_panel is not None else getattr(scene, "properties_panel", None)
        if panel is not None:
            panel.show_component(node)

        if selection_callback is not None:
            selection_callback(node)
        return

    if scene.selected_connection is None and scene.selected_subcomp_attachment is None:
        clear_highlights = getattr(scene, "clear_all_selection_highlights", None)
        if clear_highlights is not None:
            clear_highlights()
        scene.selected_component = None

        if selection_callback is not None:
            selection_callback(None)
