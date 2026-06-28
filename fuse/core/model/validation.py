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
"""Core model validation routines.

This module performs simulator-neutral validation for FUSE models. It checks
component names, required parameters, links, subcomponent attachments, and
plugin-provided compatibility before save/export operations."""

from dataclasses import dataclass
from typing import Optional
from fuse.core.persistence.db_access import get_component_details
from fuse.core.model.subcomponents import is_visual_subcomponent_connection_parameter
from fuse.core.plugin_runtime.manager import get_plugin_by_id

@dataclass
class ValidationIssue:
    """Validation warning or error associated with a model object."""
    issue_type: str
    object_name: str
    message: str
    node_id: Optional[int] = None
    link_id: Optional[int] = None
    attachment_id: Optional[int] = None
    parameter_name: Optional[str] = None
    severity: str = "error"


def normalize_default_value(value) -> str:
    """Normalize database default-value placeholders into editable FUSE values."""
    if value is None:
        return ""

    value = str(value)

    if value == "<required>":
        return ""

    return value


def effective_parameter_value(node, parameter: dict) -> str:
    """Return the user value for a parameter, falling back to metadata defaults."""
    name = parameter.get("name", "")
    default_value = normalize_default_value(parameter.get("default_val", ""))

    value = node.parameters.get(name, default_value)

    if value is None:
        return ""

    return str(value).strip()


def validate_unique_names(scene) -> list[ValidationIssue]:
    """Report duplicate or missing component instance names."""
    issues: list[ValidationIssue] = []
    used: dict[str, list[tuple[str, int | None]]] = {}

    for node in scene.component_items():
        name = node.instance_name.strip()
        used.setdefault(name, []).append(("component", node.node_id))

        if not name:
            issues.append(
                ValidationIssue(
                    issue_type="component_name",
                    object_name="<unnamed component>",
                    node_id=node.node_id,
                    parameter_name="name",
                    message="Component name cannot be empty.",
                )
            )

    for link in scene.links:
        name = link.name.strip()
        used.setdefault(name, []).append(("link", link.link_id))

        if not name:
            issues.append(
                ValidationIssue(
                    issue_type="link_name",
                    object_name="<unnamed link>",
                    link_id=link.link_id,
                    parameter_name="name",
                    message="Link name cannot be empty.",
                )
            )

    for name, users in used.items():
        if not name or len(users) <= 1:
            continue

        for object_type, object_id in users:
            if object_type == "component":
                issues.append(
                    ValidationIssue(
                        issue_type="component_name",
                        object_name=name,
                        node_id=object_id,
                        parameter_name="name",
                        message=f"Name '{name}' is already used. Names must be unique.",
                    )
                )
            else:
                issues.append(
                    ValidationIssue(
                        issue_type="link_name",
                        object_name=name,
                        link_id=object_id,
                        parameter_name="name",
                        message=f"Name '{name}' is already used. Names must be unique.",
                    )
                )

    return issues


def validate_required_component_parameters(scene) -> list[ValidationIssue]:
    """Validate required component parameters against plugin metadata."""
    issues: list[ValidationIssue] = []

    for node in scene.component_items():
        component_id = node.component.component_id
        plugin_id = getattr(node.component, "plugin_id", "core")

        if component_id is None:
            continue

        try:
            target_id = getattr(node.component, "target_id", "")
            try:
                details = get_component_details(plugin_id, component_id, target_id)
            except TypeError:
                # Backward compatibility for tests that monkeypatch a two-argument
                # get_component_details callable.
                details = get_component_details(plugin_id, component_id)
        except Exception:
            continue

        for parameter in details.get("parameters", []):
            name = parameter.get("name", "")
            required = bool(parameter.get("required"))

            if is_visual_subcomponent_connection_parameter(
                parameter,
                component_is_subcomponent=bool(int(getattr(node.component, "is_subcomp", 0) or 0)),
            ):
                required = False

            if not required:
                continue

            value = effective_parameter_value(node, parameter)

            if not value:
                issues.append(
                    ValidationIssue(
                        issue_type="component_parameter",
                        object_name=node.instance_name,
                        node_id=node.node_id,
                        parameter_name=name,
                        message=f"Required parameter '{name}' has no value.",
                    )
                )

    return issues


def validate_links(scene) -> list[ValidationIssue]:
    """Validate model links against component port metadata and variable-port rules."""
    issues: list[ValidationIssue] = []

    for link in scene.links:
        if not getattr(link, "source_latency", link.latency).strip():
            issues.append(
                ValidationIssue(
                    issue_type="link_parameter",
                    object_name=link.name,
                    link_id=link.link_id,
                    parameter_name="source_latency",
                    message="Source endpoint latency is required.",
                )
            )

        if not getattr(link, "target_latency", link.latency).strip():
            issues.append(
                ValidationIssue(
                    issue_type="link_parameter",
                    object_name=link.name,
                    link_id=link.link_id,
                    parameter_name="target_latency",
                    message="Target endpoint latency is required.",
                )
            )

    return issues

def validate_subcomp_attachments(scene) -> list[ValidationIssue]:
    """Validate subcomponent attachments against component slot metadata."""
    issues: list[ValidationIssue] = []
    seen_slots: dict[tuple[int, str], str] = {}
    seen_children: dict[int, str] = {}
    node_ids = {node.node_id for node in scene.component_items()}

    for attachment in getattr(scene, "subcomp_attachments", []):
        if attachment.parent_node_id not in node_ids:
            issues.append(
                ValidationIssue(
                    issue_type="subcomp_attachment",
                    object_name=attachment.name,
                    attachment_id=attachment.attachment_id,
                    message="SubComponent attachment parent node does not exist.",
                )
            )

        if attachment.child_node_id not in node_ids:
            issues.append(
                ValidationIssue(
                    issue_type="subcomp_attachment",
                    object_name=attachment.name,
                    attachment_id=attachment.attachment_id,
                    message="SubComponent attachment child node does not exist.",
                )
            )

        slot_key = (attachment.parent_node_id, attachment.slot_name)
        if slot_key in seen_slots:
            issues.append(
                ValidationIssue(
                    issue_type="subcomp_attachment",
                    object_name=attachment.name,
                    node_id=attachment.parent_node_id,
                    attachment_id=attachment.attachment_id,
                    parameter_name=attachment.slot_name,
                    message=(
                        f"SubComponent slot '{attachment.slot_name}' is assigned more "
                        "than once."
                    ),
                )
            )
        else:
            seen_slots[slot_key] = attachment.name

        if attachment.child_node_id in seen_children:
            issues.append(
                ValidationIssue(
                    issue_type="subcomp_attachment",
                    object_name=attachment.name,
                    node_id=attachment.child_node_id,
                    attachment_id=attachment.attachment_id,
                    message="This SubComponent is assigned to more than one parent slot.",
                )
            )
        else:
            seen_children[attachment.child_node_id] = attachment.name

        if attachment.required_interface and attachment.provided_interface:
            if attachment.required_interface != attachment.provided_interface:
                issues.append(
                    ValidationIssue(
                        issue_type="subcomp_attachment",
                        object_name=attachment.name,
                        attachment_id=attachment.attachment_id,
                        severity="warning",
                        message=(
                            "SubComponent interface mismatch: slot metadata declares "
                            f"{attachment.required_interface}, but subcomponent declares "
                            f"{attachment.provided_interface}. "
                            "FUSE will use the visual parent/slot attachment for export."
                        ),
                    )
                )

    return issues


def validate_plugin_links(scene) -> list[ValidationIssue]:
    """Ask simulator plugins to validate framework-specific link compatibility."""
    plugin_ids = {getattr(scene, "active_plugin_id", "") or ""}

    try:
        for node in scene.component_items():
            plugin_ids.add(getattr(node.component, "plugin_id", "") or "")
    except Exception:
        pass

    issues: list[ValidationIssue] = []

    for plugin_id in sorted(item for item in plugin_ids if item):
        try:
            plugin = get_plugin_by_id(plugin_id)
        except Exception:
            continue

        if not hasattr(plugin, "validate_links"):
            continue

        issues.extend(plugin.validate_links(scene))

    return issues

def validate_model(scene) -> list[ValidationIssue]:
    """Run the core validation suite for the provided model."""
    issues: list[ValidationIssue] = []
    issues.extend(validate_unique_names(scene))
    issues.extend(validate_required_component_parameters(scene))
    issues.extend(validate_links(scene))
    issues.extend(validate_subcomp_attachments(scene))
    issues.extend(validate_plugin_links(scene))
    return issues

def model_plugin_ids(scene) -> set[str]:
    """Return plugin identifiers used by components in the model."""
    return {
        (getattr(node.component, "plugin_id", "") or "core").strip()
        for node in scene.component_items()
    }


def validate_model_for_export(scene, plugin_id: str | None = None) -> list[ValidationIssue]:
    """Validate that the current model is ready to export for one simulator.

    This intentionally extends, rather than replaces, normal FUSE model
    validation. A graph may be internally valid but not exportable to a
    particular simulator/plugin. Mixed-plugin models are allowed as editable
    FUSE projects, but export validation currently requires all components to
    belong to the requested plugin until a hybrid exporter exists. Composite
    components are a FUSE editor abstraction, so export validation runs against
    the flattened simulator-facing graph.
    """
    issues = validate_model(scene)
    plugin_id = (plugin_id or getattr(scene, "active_plugin_id", "") or "").strip()

    if not plugin_id:
        issues.append(
            ValidationIssue(
                issue_type="export_target",
                object_name="Project",
                message="No active simulator target is selected for export validation.",
            )
        )
        return issues

    try:
        from fuse.core.model.composite_flattening import flatten_scene_for_export

        export_scene = flatten_scene_for_export(scene)
    except Exception as exc:
        issues.append(
            ValidationIssue(
                issue_type="export_composite",
                object_name="Project",
                message=f"Composite component expansion failed: {exc}",
            )
        )
        return issues

    present_plugin_ids = {item for item in model_plugin_ids(export_scene) if item}
    unsupported = sorted(item for item in present_plugin_ids if item != plugin_id)

    if unsupported:
        issues.append(
            ValidationIssue(
                issue_type="export_target",
                object_name="Project",
                message=(
                    f"Export target '{plugin_id}' cannot currently export components "
                    f"from: {', '.join(unsupported)}. Mixed-plugin FUSE models can be "
                    "saved and edited, but need a hybrid exporter before export."
                ),
            )
        )

    try:
        plugin = get_plugin_by_id(plugin_id)
    except Exception:
        return issues

    if hasattr(plugin, "validate_export"):
        try:
            issues.extend(plugin.validate_export(export_scene))
        except Exception as exc:
            issues.append(
                ValidationIssue(
                    issue_type="export_plugin",
                    object_name=plugin_id,
                    message=f"Plugin export validation failed: {exc}",
                )
            )

    return issues
