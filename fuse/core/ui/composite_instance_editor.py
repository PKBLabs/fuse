# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSplitter,
    QVBoxLayout,
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
from fuse.core.ui.properties_panel import PropertiesPanel
from fuse.core.model.models import SCHEMA_VERSION


def composite_definition_for_node(node) -> CompositeComponentDefinition | None:
    component = getattr(node, "component", None)
    composite_id = getattr(component, "composite_id", "") or getattr(component, "component_id", "") or ""
    if not composite_id:
        return None
    return get_composite_component_definition(str(composite_id))


def composite_instance_mini_model(node) -> dict[str, Any]:
    instance_model = getattr(node, "composite_instance_model", {}) or {}
    if isinstance(instance_model, dict) and instance_model.get("components") is not None:
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
    if mappings:
        normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
            getattr(node, "composite_instance_model", {}) or {},
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


class CompositeInstanceEditorDialog(QDialog):
    def __init__(self, node, parent=None):
        super().__init__(parent)
        self.node = node
        self.setWindowTitle(f"Edit Composite Instance: {getattr(node, 'instance_name', 'Composite')}")
        self.resize(980, 640)

        layout = QVBoxLayout(self)
        help_label = QLabel(
            "Edit the internal mini-model for this composite instance. "
            "Changes apply only to the selected instance, not the global composite template."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        splitter = QSplitter(Qt.Horizontal, self)
        self.editor_scene = ModelScene()
        self.editor_scene.active_plugin_id = getattr(getattr(node, "scene", lambda: None)(), "active_plugin_id", "") or ""
        self.editor_view = ModelView(self.editor_scene)
        self.editor_properties = PropertiesPanel()
        self.editor_scene.properties_panel = self.editor_properties
        self.editor_properties.property_changed_callback = self.editor_scene.notify_model_changed

        splitter.addWidget(self.editor_view)
        splitter.addWidget(self.editor_properties)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_instance_model()

    def load_instance_model(self) -> None:
        mini_model = composite_instance_mini_model(self.node)
        if not mini_model:
            return
        load_project_into_scene(project_dict_for_mini_model(mini_model), self.editor_scene)
        self.editor_scene.clearSelection()
        self.editor_properties.show_empty()

    def edited_mini_model(self) -> dict[str, Any]:
        return mini_model_from_scene(self.editor_scene)

    def edited_port_mappings(self) -> list[CompositePortMapping]:
        return port_mappings_from_scene(self.editor_scene)
