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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from fuse.core.model.models import SCHEMA_VERSION


FORMAT_ID = "fuse.project"
SERIALIZER_VERSION = 1


@dataclass(frozen=True)
class ProjectFileValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


class ProjectFileValidationError(ValueError):
    def __init__(self, issues: list[ProjectFileValidationIssue]):
        self.issues = issues
        preview = "; ".join(str(issue) for issue in issues[:5])
        if len(issues) > 5:
            preview += f"; ...and {len(issues) - 5} more issue(s)"
        super().__init__(f"Invalid project file: {preview}")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_serialization_metadata(project: dict[str, Any]) -> dict[str, Any]:
    components = project.get("components", []) if isinstance(project, dict) else []
    links = project.get("links", []) if isinstance(project, dict) else []
    attachments = project.get("subcompAttachments", []) if isinstance(project, dict) else []

    plugin_ids = sorted(
        {
            str(component.get("pluginId") or component.get("plugin_id") or "core")
            for component in components
            if isinstance(component, dict)
        }
    )

    return {
        "format": FORMAT_ID,
        "schemaVersion": SCHEMA_VERSION,
        "serializerVersion": SERIALIZER_VERSION,
        "generatedBy": "FUSE",
        "generatedAt": now_iso(),
        "modelCounts": {
            "components": len(components) if isinstance(components, list) else 0,
            "links": len(links) if isinstance(links, list) else 0,
            "subcompAttachments": len(attachments) if isinstance(attachments, list) else 0,
        },
        "plugins": plugin_ids,
    }


def finalize_project_dict(project: dict[str, Any]) -> dict[str, Any]:
    """Add non-authoritative serialization metadata before saving.

    The metadata intentionally duplicates information that is already present in
    the canonical model sections. It helps humans and future loaders identify the
    file without becoming required for backward compatibility.
    """
    project["serialization"] = build_serialization_metadata(project)
    return project


def _issue(issues: list[ProjectFileValidationIssue], path: str, message: str) -> None:
    issues.append(ProjectFileValidationIssue(path, message))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _expect_object(issues: list[ProjectFileValidationIssue], value: Any, path: str) -> bool:
    if not isinstance(value, dict):
        _issue(issues, path, "must be an object")
        return False
    return True


def _expect_list(issues: list[ProjectFileValidationIssue], value: Any, path: str) -> bool:
    if not isinstance(value, list):
        _issue(issues, path, "must be a list")
        return False
    return True


def _expect_stringish(issues: list[ProjectFileValidationIssue], value: Any, path: str) -> None:
    if value is None:
        _issue(issues, path, "is required")
        return
    if not isinstance(value, (str, int)):
        _issue(issues, path, "must be a string or integer")


def _expect_numeric_mapping(issues: list[ProjectFileValidationIssue], value: Any, path: str, keys: tuple[str, ...]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        _issue(issues, path, "must be an object")
        return
    for key in keys:
        if key in value and not _is_number(value[key]):
            _issue(issues, f"{path}.{key}", "must be numeric")


def _node_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def validate_serialized_project(project: Any, *, strict_references: bool = True) -> None:
    """Validate a serialized .fse project at the file-structure level.

    This is intentionally independent of Qt scene objects and plugin databases.
    It verifies that the saved file has the sections and references needed to
    reconstruct a FUSE model before the loader starts creating graphics items.
    Plugin-specific export validity remains the responsibility of model/export
    validation.
    """
    issues: list[ProjectFileValidationIssue] = []

    if not isinstance(project, dict):
        raise ProjectFileValidationError([
            ProjectFileValidationIssue("$", "root must be a JSON object"),
        ])

    if project.get("schemaVersion") != SCHEMA_VERSION:
        _issue(
            issues,
            "schemaVersion",
            f"unsupported value {project.get('schemaVersion')!r}; expected {SCHEMA_VERSION!r}",
        )

    if "project" in project and _expect_object(issues, project.get("project"), "project"):
        name = project.get("project", {}).get("name")
        if name is not None and not isinstance(name, str):
            _issue(issues, "project.name", "must be a string")

    components = project.get("components")
    links = project.get("links")
    attachments = project.get("subcompAttachments", [])

    if not _expect_list(issues, components, "components"):
        components = []
    if not _expect_list(issues, links, "links"):
        links = []
    if attachments is not None and not _expect_list(issues, attachments, "subcompAttachments"):
        attachments = []

    component_ids: set[int] = set()
    component_names: dict[int, str] = {}

    for index, component in enumerate(components):
        path = f"components[{index}]"
        if not isinstance(component, dict):
            _issue(issues, path, "must be an object")
            continue

        node_id = _node_id(component.get("id"))
        if node_id is None:
            _issue(issues, f"{path}.id", "must be an integer")
        elif node_id in component_ids:
            _issue(issues, f"{path}.id", f"duplicates component id {node_id}")
        else:
            component_ids.add(node_id)
            component_names[node_id] = str(component.get("instanceName") or component.get("name") or node_id)

        _expect_stringish(issues, component.get("name"), f"{path}.name")
        _expect_stringish(issues, component.get("instanceName", component.get("name")), f"{path}.instanceName")
        _expect_numeric_mapping(issues, component.get("position"), f"{path}.position", ("x", "y"))

        parameters = component.get("parameters", {})
        if parameters is not None and not isinstance(parameters, dict):
            _issue(issues, f"{path}.parameters", "must be an object")

        variable_counts = component.get("variablePortCounts", {})
        if variable_counts is not None and not isinstance(variable_counts, dict):
            _issue(issues, f"{path}.variablePortCounts", "must be an object")

        composite_instance = component.get("compositeInstance", {})
        if composite_instance is not None and composite_instance != {}:
            if _expect_object(issues, composite_instance, f"{path}.compositeInstance"):
                mini_model = composite_instance.get("miniModel", {})
                if mini_model is not None and not isinstance(mini_model, dict):
                    _issue(issues, f"{path}.compositeInstance.miniModel", "must be an object")
                port_mappings = composite_instance.get("portMappings", [])
                if port_mappings is not None and not isinstance(port_mappings, list):
                    _issue(issues, f"{path}.compositeInstance.portMappings", "must be a list")

    link_ids: set[int] = set()

    for index, link in enumerate(links):
        path = f"links[{index}]"
        if not isinstance(link, dict):
            _issue(issues, path, "must be an object")
            continue

        link_id = _node_id(link.get("id"))
        if link_id is None:
            _issue(issues, f"{path}.id", "must be an integer")
        elif link_id in link_ids:
            _issue(issues, f"{path}.id", f"duplicates link id {link_id}")
        else:
            link_ids.add(link_id)

        source = link.get("source")
        target = link.get("target")
        if _expect_object(issues, source, f"{path}.source"):
            source_node_id = _node_id(source.get("nodeId"))
            if source_node_id is None:
                _issue(issues, f"{path}.source.nodeId", "must be an integer")
            elif strict_references and source_node_id not in component_ids:
                _issue(issues, f"{path}.source.nodeId", f"references missing component id {source_node_id}")
            _expect_stringish(issues, source.get("port"), f"{path}.source.port")

        if _expect_object(issues, target, f"{path}.target"):
            target_node_id = _node_id(target.get("nodeId"))
            if target_node_id is None:
                _issue(issues, f"{path}.target.nodeId", "must be an integer")
            elif strict_references and target_node_id not in component_ids:
                _issue(issues, f"{path}.target.nodeId", f"references missing component id {target_node_id}")
            _expect_stringish(issues, target.get("port"), f"{path}.target.port")

        compatibility = link.get("compatibility", {})
        if compatibility is not None and not isinstance(compatibility, dict):
            _issue(issues, f"{path}.compatibility", "must be an object")
        plugin_metadata = link.get("pluginMetadata", {})
        if plugin_metadata is not None and not isinstance(plugin_metadata, dict):
            _issue(issues, f"{path}.pluginMetadata", "must be an object")

    attachment_ids: set[int] = set()

    for index, attachment in enumerate(attachments or []):
        path = f"subcompAttachments[{index}]"
        if not isinstance(attachment, dict):
            _issue(issues, path, "must be an object")
            continue

        attachment_id = _node_id(attachment.get("id"))
        if attachment_id is None:
            _issue(issues, f"{path}.id", "must be an integer")
        elif attachment_id in attachment_ids:
            _issue(issues, f"{path}.id", f"duplicates subcomponent attachment id {attachment_id}")
        else:
            attachment_ids.add(attachment_id)

        parent = attachment.get("parent")
        child = attachment.get("child")
        if _expect_object(issues, parent, f"{path}.parent"):
            parent_node_id = _node_id(parent.get("nodeId"))
            if parent_node_id is None:
                _issue(issues, f"{path}.parent.nodeId", "must be an integer")
            elif strict_references and parent_node_id not in component_ids:
                _issue(issues, f"{path}.parent.nodeId", f"references missing component id {parent_node_id}")
            _expect_stringish(issues, parent.get("slotName"), f"{path}.parent.slotName")

        if _expect_object(issues, child, f"{path}.child"):
            child_node_id = _node_id(child.get("nodeId"))
            if child_node_id is None:
                _issue(issues, f"{path}.child.nodeId", "must be an integer")
            elif strict_references and child_node_id not in component_ids:
                _issue(issues, f"{path}.child.nodeId", f"references missing component id {child_node_id}")

        compatibility = attachment.get("compatibility", {})
        if compatibility is not None and not isinstance(compatibility, dict):
            _issue(issues, f"{path}.compatibility", "must be an object")
        plugin_metadata = attachment.get("pluginMetadata", {})
        if plugin_metadata is not None and not isinstance(plugin_metadata, dict):
            _issue(issues, f"{path}.pluginMetadata", "must be an object")

    editor = project.get("editor", {})
    if editor is not None and _expect_object(issues, editor, "editor"):
        _expect_numeric_mapping(issues, editor.get("sceneRect"), "editor.sceneRect", ("x", "y", "width", "height"))
        _expect_numeric_mapping(issues, editor.get("viewCenter"), "editor.viewCenter", ("x", "y"))
        if "zoomPercent" in editor and not isinstance(editor.get("zoomPercent"), (int, float)):
            _issue(issues, "editor.zoomPercent", "must be numeric")
        if "mode" in editor:
            _expect_stringish(issues, editor.get("mode"), "editor.mode")
        if "toolbarPosition" in editor:
            _expect_numeric_mapping(issues, editor.get("toolbarPosition"), "editor.toolbarPosition", ("x", "y"))

    project_settings = project.get("projectSettings", {})
    if project_settings is not None and not isinstance(project_settings, dict):
        _issue(issues, "projectSettings", "must be an object")

    plugin_settings = project.get("pluginSettings", {})
    if plugin_settings is not None and not isinstance(plugin_settings, dict):
        _issue(issues, "pluginSettings", "must be an object")

    serialization = project.get("serialization", {})
    if serialization:
        if not isinstance(serialization, dict):
            _issue(issues, "serialization", "must be an object")
        else:
            if serialization.get("format") not in (None, FORMAT_ID):
                _issue(issues, "serialization.format", f"must be {FORMAT_ID!r}")
            if serialization.get("schemaVersion") not in (None, SCHEMA_VERSION):
                _issue(issues, "serialization.schemaVersion", f"must be {SCHEMA_VERSION!r}")

    if issues:
        raise ProjectFileValidationError(issues)
