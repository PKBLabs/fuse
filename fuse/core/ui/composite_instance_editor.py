# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QVBoxLayout,
    QWidget,
)

from fuse.core.model.composite import CompositeComponentDefinition, CompositePortMapping
from fuse.core.model.composite_mini_model import normalize_mini_model_and_port_mappings
from fuse.core.persistence.composite_components import get_composite_component_definition
from fuse.core.persistence.project_io import (
    component_node_to_save_dict,
    load_project_into_scene,
    model_link_to_save_dict,
    subcomp_attachment_to_save_dict,
)
from fuse.core.ui.composite_builder import composite_port_mappings_for_fragment
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.model.models import SCHEMA_VERSION


def composite_definition_for_node(node) -> CompositeComponentDefinition | None:
    component = getattr(node, "component", None)
    composite_id = getattr(component, "composite_id", "") or getattr(component, "component_id", "") or ""
    if not composite_id:
        return None
    return get_composite_component_definition(str(composite_id))


def mini_model_has_components(mini_model: dict[str, Any]) -> bool:
    return isinstance(mini_model, dict) and bool(mini_model.get("components") or [])


def composite_instance_mini_model(node) -> dict[str, Any]:
    instance_model = getattr(node, "composite_instance_model", {}) or {}
    if mini_model_has_components(instance_model):
        normalized_model, ignored_mappings = normalize_mini_model_and_port_mappings(
            instance_model,
            getattr(node, "composite_port_mappings", []) or [],
        )
        return normalized_model

    definition = composite_definition_for_node(node)
    if definition is None:
        return {}
    normalized_model, ignored_mappings = normalize_mini_model_and_port_mappings(
        definition.mini_model or {},
        definition.port_mappings,
    )
    return normalized_model


def composite_instance_port_mappings(node) -> list[CompositePortMapping]:
    mappings = getattr(node, "composite_port_mappings", None)
    instance_model = getattr(node, "composite_instance_model", {}) or {}
    if mappings and mini_model_has_components(instance_model):
        normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
            instance_model,
            mappings,
        )
        return normalized_mappings

    definition = composite_definition_for_node(node)
    if definition is None:
        return []
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        definition.mini_model or {},
        definition.port_mappings,
    )
    return normalized_mappings


def project_dict_for_mini_model(mini_model: dict[str, Any]) -> dict[str, Any]:
    normalized_model, ignored_mappings = normalize_mini_model_and_port_mappings(mini_model, [])
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": {"name": "Composite instance mini-model"},
        "projectSettings": {},
        "pluginSettings": {},
        "activeTarget": {"pluginId": "", "targetId": ""},
        "components": deepcopy(normalized_model.get("components", []) or []),
        "links": deepcopy(normalized_model.get("links", []) or []),
        "subcompAttachments": deepcopy(normalized_model.get("subcompAttachments", []) or []),
        "editor": {},
    }


def mini_model_from_scene(scene: ModelScene) -> dict[str, Any]:
    return {
        "schemaVersion": "0.1.0",
        "kind": "fuse.composite-mini-model",
        "origin": {"x": 0.0, "y": 0.0},
        "components": [
            component_node_to_save_dict(node)
            for node in scene.component_items()
        ],
        "links": [
            model_link_to_save_dict(link)
            for link in sorted(scene.links, key=lambda item: item.link_id)
        ],
        "subcompAttachments": [
            subcomp_attachment_to_save_dict(attachment)
            for attachment in sorted(
                getattr(scene, "subcomp_attachments", []),
                key=lambda item: item.attachment_id,
            )
        ],
    }


def port_mappings_from_scene(scene: ModelScene) -> list[CompositePortMapping]:
    return composite_port_mappings_for_fragment(
        scene.component_items(),
        scene.connection_items(),
    )


def apply_composite_instance_edit(
    node,
    mini_model: dict[str, Any],
    port_mappings: list[CompositePortMapping],
) -> None:
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        mini_model,
        port_mappings,
    )
    node.composite_instance_model = normalized_model
    node.composite_port_mappings = [deepcopy(mapping) for mapping in normalized_mappings]


class CompositeInstanceEditorWidget(QWidget):
    def __init__(
        self,
        node,
        parent=None,
        nested_edit_requested_callback=None,
        instance_changed_callback=None,
    ):
        super().__init__(parent)
        self.node = node
        self.nested_edit_requested_callback = nested_edit_requested_callback
        self.instance_changed_callback = instance_changed_callback
        self.loading_model = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        help_label = QLabel(
            "Edit the internal mini-model for this composite instance. "
            "Changes apply only to this placed instance, not the global composite template."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.editor_scene = ModelScene()
        self.editor_scene.active_plugin_id = getattr(getattr(node, "scene", lambda: None)(), "active_plugin_id", "") or ""
        self.editor_view = ModelView(self.editor_scene)
        self.editor_scene.model_changed_callback = self.on_editor_scene_changed
        self.editor_scene.composite_instance_edit_requested_callback = self.request_nested_composite_edit

        layout.addWidget(self.editor_view, 1)

        self.load_instance_model()

    def load_instance_model(self) -> None:
        mini_model = composite_instance_mini_model(self.node)
        if not mini_model:
            return

        self.loading_model = True
        try:
            load_project_into_scene(project_dict_for_mini_model(mini_model), self.editor_scene)
            self.editor_scene.clearSelection()
            if self.editor_scene.properties_panel is not None:
                self.editor_scene.properties_panel.show_empty()
        finally:
            self.loading_model = False

    def edited_mini_model(self) -> dict[str, Any]:
        return mini_model_from_scene(self.editor_scene)

    def edited_port_mappings(self) -> list[CompositePortMapping]:
        return port_mappings_from_scene(self.editor_scene)

    def apply_current_edit_to_node(self) -> None:
        apply_composite_instance_edit(
            self.node,
            self.edited_mini_model(),
            self.edited_port_mappings(),
        )

    def on_editor_scene_changed(self) -> None:
        if self.loading_model:
            return

        self.apply_current_edit_to_node()
        if self.instance_changed_callback is not None:
            self.instance_changed_callback(self)

    def request_nested_composite_edit(self, nested_node) -> None:
        self.apply_current_edit_to_node()
        if self.nested_edit_requested_callback is not None:
            self.nested_edit_requested_callback(nested_node, self)
