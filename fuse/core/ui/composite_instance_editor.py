# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Editors for composite component instances and templates.

Composite editing uses a nested ``ModelScene``/``ModelView`` pair to present
the mini-model stored inside a composite. Instance editors update a single
placed node, while template editors update the reusable composite definition in
the component database and may be applied to existing instances by the main
window.

The helper functions in this module translate between canvas nodes, serialized
mini-model dictionaries, and ``CompositePortMapping`` objects that describe
which internal ports are exposed on the composite boundary.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QMessageBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from fuse.core.model.composite import CompositeComponentDefinition, CompositePortMapping
from fuse.core.model.composite_mini_model import normalize_mini_model_and_port_mappings
from fuse.core.persistence.composite_components import (
    get_composite_component_definition,
    save_composite_component_definition,
)
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
    """Load the reusable composite definition referenced by a node, if any."""
    component = getattr(node, "component", None)
    composite_id = getattr(component, "composite_id", "") or getattr(component, "component_id", "") or ""
    if not composite_id:
        return None
    return get_composite_component_definition(str(composite_id))


def mini_model_has_components(mini_model: dict[str, Any]) -> bool:
    """Return whether a serialized mini-model contains component entries."""
    return isinstance(mini_model, dict) and bool(mini_model.get("components") or [])


def composite_instance_mini_model(node) -> dict[str, Any]:
    """Return the mini-model currently used by a composite node.

    Instance-local edits take precedence over the reusable template. If the
    instance has not diverged, the template definition is loaded and normalized.
    """
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
    """Return normalized exposed-port mappings for a composite node."""
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


def port_mapping_matches_port(mapping: CompositePortMapping, port) -> bool:
    """Return whether a mapping refers to the given internal node/port pair.

    The internal node id is authoritative. Older copied composite instances may
    carry stale ``internal_component_name`` text until their mini-model is
    normalized; matching by id and port keeps exposure state stable through the
    first edit/open cycle and lets normalization repair the stored name.
    """
    return (
        int(mapping.internal_node_id) == int(port.node.node_id)
        and str(mapping.internal_port_name) == str(port.name)
    )


def set_exposed_state_for_port_mapping(
    mappings: list[CompositePortMapping],
    port,
    exposed: bool,
) -> bool:
    """Set the exposed/hidden state for one internal port mapping."""
    for mapping in mappings:
        if port_mapping_matches_port(mapping, port):
            mapping.internal_component_name = str(port.node.instance_name)
            mapping.exposed = bool(exposed)
            return True
    return False


def port_is_exposed_in_mappings(
    mappings: list[CompositePortMapping],
    port,
) -> bool:
    """Return whether a given internal port is currently exposed."""
    for mapping in mappings:
        if port_mapping_matches_port(mapping, port):
            return bool(getattr(mapping, "exposed", True))
    return False


def update_editor_port_exposure_visuals(
    scene: ModelScene,
    mappings: list[CompositePortMapping],
) -> None:
    """Refresh port highlighting for a composite editor scene."""
    for node in scene.component_items():
        for port in getattr(node, "ports", []) or []:
            exposed = port_is_exposed_in_mappings(mappings, port)
            port.is_composite_exposed_port = exposed
            port.update_connection_state()


def project_dict_for_mini_model(mini_model: dict[str, Any]) -> dict[str, Any]:
    """Wrap a composite mini-model in the minimal project dictionary shape."""
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
    """Serialize the contents of a composite editor scene into a mini-model."""
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


def preserve_exposed_state(
    new_mappings: list[CompositePortMapping],
    existing_mappings: list[CompositePortMapping],
) -> list[CompositePortMapping]:
    """Carry existing exposed/hidden choices onto refreshed port mappings."""
    existing_by_internal_port = {
        (
            int(mapping.internal_node_id),
            str(mapping.internal_component_name),
            str(mapping.internal_port_name),
        ): bool(getattr(mapping, "exposed", True))
        for mapping in existing_mappings
    }
    existing_by_node_and_port = {
        (
            int(mapping.internal_node_id),
            str(mapping.internal_port_name),
        ): bool(getattr(mapping, "exposed", True))
        for mapping in existing_mappings
    }
    existing_by_name = {
        str(mapping.external_port_name): bool(getattr(mapping, "exposed", True))
        for mapping in existing_mappings
    }

    for mapping in new_mappings:
        key = (
            int(mapping.internal_node_id),
            str(mapping.internal_component_name),
            str(mapping.internal_port_name),
        )
        node_port_key = (
            int(mapping.internal_node_id),
            str(mapping.internal_port_name),
        )
        if key in existing_by_internal_port:
            mapping.exposed = existing_by_internal_port[key]
        elif node_port_key in existing_by_node_and_port:
            mapping.exposed = existing_by_node_and_port[node_port_key]
        elif str(mapping.external_port_name) in existing_by_name:
            mapping.exposed = existing_by_name[str(mapping.external_port_name)]
    return new_mappings


def port_mappings_from_scene(
    scene: ModelScene,
    existing_mappings: list[CompositePortMapping] | None = None,
) -> list[CompositePortMapping]:
    """Recompute composite port mappings from the current editor scene."""
    mappings = composite_port_mappings_for_fragment(
        scene.component_items(),
        scene.connection_items(),
    )
    return preserve_exposed_state(mappings, list(existing_mappings or []))


def apply_composite_instance_edit(
    node,
    mini_model: dict[str, Any],
    port_mappings: list[CompositePortMapping],
) -> None:
    """Write a composite editor mini-model and mappings back to a node."""
    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
        mini_model,
        port_mappings,
    )
    node.composite_instance_model = normalized_model
    node.composite_port_mappings = [deepcopy(mapping) for mapping in normalized_mappings]
    if hasattr(node, "sync_composite_ports_from_mappings"):
        node.sync_composite_ports_from_mappings()


class CompositeInstanceEditorWidget(QWidget):
    """Editor widget for a single placed composite component instance.

    Changes made through this widget update the selected node's instance-local
    mini-model and port mappings. The reusable composite template is not
    modified by this editor.
    """
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
            "Changes apply only to this placed instance, not the global composite template. "
            "Use the Expose Ports toolbar mode or right-click a port to toggle whether "
            "an unlinked internal port appears on this composite instance."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.editor_scene = ModelScene()
        self.editor_scene.active_plugin_id = getattr(getattr(node, "scene", lambda: None)(), "active_plugin_id", "") or ""
        self.editor_view = ModelView(self.editor_scene)
        self.editor_scene.model_changed_callback = self.on_editor_scene_changed
        self.editor_scene.composite_instance_edit_requested_callback = self.request_nested_composite_edit
        self.editor_scene.composite_port_exposure_requested_callback = self.set_port_exposed
        self.editor_scene.composite_port_exposure_state_callback = self.port_is_exposed
        self.editor_view.set_port_exposure_tools_available(True)

        layout.addWidget(self.editor_view, 1)

        self.load_instance_model()

    def load_instance_model(self) -> None:
        mini_model = composite_instance_mini_model(self.node)
        if not mini_model:
            return

        # Materialize lazy template-backed instances on first open so subsequent
        # editor scene changes preserve the same port-mapping source of truth
        # instead of falling back to the template and losing exposed-state flags.
        apply_composite_instance_edit(
            self.node,
            mini_model,
            composite_instance_port_mappings(self.node),
        )
        mini_model = getattr(self.node, "composite_instance_model", {}) or {}

        self.loading_model = True
        try:
            load_project_into_scene(project_dict_for_mini_model(mini_model), self.editor_scene)
            self.editor_scene.clearSelection()
            if self.editor_scene.properties_panel is not None:
                self.editor_scene.properties_panel.show_empty()
            self.refresh_port_exposure_visuals()
        finally:
            self.loading_model = False

    def edited_mini_model(self) -> dict[str, Any]:
        return mini_model_from_scene(self.editor_scene)

    def edited_port_mappings(self) -> list[CompositePortMapping]:
        return port_mappings_from_scene(
            self.editor_scene,
            composite_instance_port_mappings(self.node),
        )

    def refresh_port_exposure_visuals(self) -> None:
        update_editor_port_exposure_visuals(self.editor_scene, self.edited_port_mappings())

    def apply_current_edit_to_node(self) -> None:
        apply_composite_instance_edit(
            self.node,
            self.edited_mini_model(),
            self.edited_port_mappings(),
        )
        self.refresh_port_exposure_visuals()

    def port_is_exposed(self, port) -> bool:
        return port_is_exposed_in_mappings(self.edited_port_mappings(), port)

    def set_port_exposed(self, port, exposed: bool) -> bool:
        if bool(exposed) and port.is_connected():
            QMessageBox.warning(
                self,
                "Expose Composite Port",
                "Only unlinked internal ports can be exposed on the composite boundary.",
            )
            return False

        mappings = self.edited_port_mappings()
        if not set_exposed_state_for_port_mapping(mappings, port, bool(exposed)):
            return False

        apply_composite_instance_edit(self.node, self.edited_mini_model(), mappings)
        self.refresh_port_exposure_visuals()
        if self.instance_changed_callback is not None:
            self.instance_changed_callback(self)
        return True

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


class CompositeTemplateEditorWidget(QWidget):
    """Editor widget for a reusable composite component template.

    The template editor loads a composite definition from the database, allows
    the user to edit its internal mini-model and exposed ports, and persists
    the updated definition when the user saves template changes.
    """
    def __init__(
        self,
        definition: CompositeComponentDefinition,
        parent=None,
        nested_edit_requested_callback=None,
        template_changed_callback=None,
        template_save_requested_callback=None,
    ):
        super().__init__(parent)
        self.definition = deepcopy(definition)
        self.nested_edit_requested_callback = nested_edit_requested_callback
        self.template_changed_callback = template_changed_callback
        self.template_save_requested_callback = template_save_requested_callback
        self.loading_model = False
        self.template_dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        help_label = QLabel(
            "Edit the global/default configuration for this composite component. "
            "Use Save Template Changes to write changes to the local composite database. "
            "Use the Expose Ports toolbar mode or right-click a port to toggle whether "
            "an unlinked internal port appears on new composite instances."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.save_template_button = QToolButton(self)
        self.save_template_button.setText("Save Template Changes")
        self.save_template_button.setToolTip("Save this composite template configuration to the local database")
        self.save_template_button.clicked.connect(self.request_save_template_changes)
        self.save_template_button.setEnabled(False)
        layout.addWidget(self.save_template_button)

        self.editor_scene = ModelScene()
        self.editor_view = ModelView(self.editor_scene)
        self.editor_scene.model_changed_callback = self.on_editor_scene_changed
        self.editor_scene.composite_instance_edit_requested_callback = self.request_nested_composite_edit
        self.editor_scene.composite_port_exposure_requested_callback = self.set_port_exposed
        self.editor_scene.composite_port_exposure_state_callback = self.port_is_exposed
        self.editor_view.set_port_exposure_tools_available(True)
        layout.addWidget(self.editor_view, 1)

        self.load_template_model()

    def load_template_model(self) -> None:
        if not self.definition.mini_model:
            return

        normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
            self.definition.mini_model or {},
            self.definition.port_mappings,
        )
        self.definition.mini_model = normalized_model
        self.definition.port_mappings = [deepcopy(mapping) for mapping in normalized_mappings]

        self.loading_model = True
        try:
            load_project_into_scene(project_dict_for_mini_model(normalized_model), self.editor_scene)
            self.editor_scene.clearSelection()
            self.refresh_port_exposure_visuals()
        finally:
            self.loading_model = False

    def edited_mini_model(self) -> dict[str, Any]:
        return mini_model_from_scene(self.editor_scene)

    def edited_port_mappings(self) -> list[CompositePortMapping]:
        return port_mappings_from_scene(
            self.editor_scene,
            self.definition.port_mappings,
        )

    def refresh_port_exposure_visuals(self) -> None:
        update_editor_port_exposure_visuals(self.editor_scene, self.edited_port_mappings())

    def update_save_button_state(self) -> None:
        self.save_template_button.setEnabled(bool(self.template_dirty))

    def set_template_dirty(self, dirty: bool = True) -> None:
        self.template_dirty = bool(dirty)
        self.update_save_button_state()

    def request_save_template_changes(self) -> None:
        if self.template_save_requested_callback is not None:
            self.template_save_requested_callback(self)
            return
        self.save_template_changes()

    def apply_current_edit_to_node(self) -> None:
        self.definition.mini_model = self.edited_mini_model()
        self.definition.port_mappings = [deepcopy(mapping) for mapping in self.edited_port_mappings()]
        self.refresh_port_exposure_visuals()

    def save_template_changes(self) -> CompositeComponentDefinition:
        self.apply_current_edit_to_node()
        saved = save_composite_component_definition(self.definition)
        self.definition = deepcopy(saved)
        self.set_template_dirty(False)
        return saved

    def port_is_exposed(self, port) -> bool:
        return port_is_exposed_in_mappings(self.edited_port_mappings(), port)

    def set_port_exposed(self, port, exposed: bool) -> bool:
        if bool(exposed) and port.is_connected():
            QMessageBox.warning(
                self,
                "Expose Composite Port",
                "Only unlinked internal ports can be exposed on the composite boundary.",
            )
            return False

        mappings = self.edited_port_mappings()
        if not set_exposed_state_for_port_mapping(mappings, port, bool(exposed)):
            return False

        self.definition.mini_model = self.edited_mini_model()
        self.definition.port_mappings = [deepcopy(mapping) for mapping in mappings]
        self.set_template_dirty(True)
        self.refresh_port_exposure_visuals()
        if self.template_changed_callback is not None:
            self.template_changed_callback(self)
        return True

    def on_editor_scene_changed(self) -> None:
        if self.loading_model:
            return
        self.apply_current_edit_to_node()
        self.set_template_dirty(True)
        if self.template_changed_callback is not None:
            self.template_changed_callback(self)

    def request_nested_composite_edit(self, nested_node) -> None:
        self.apply_current_edit_to_node()
        if self.nested_edit_requested_callback is not None:
            self.nested_edit_requested_callback(nested_node, self)
