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
"""SST JSON export and validation helpers.

This module converts a FUSE scene, including flattened composite scenes, into
the SST JSON structure consumed by SST's Python input layer. It also performs
export-readiness checks so users get actionable validation errors before a file
is written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any


DEFAULT_LINK_LATENCY = "1ns"
SST_EXPORT_FORMAT = "sst.json"
SST_EXPORT_SCHEMA_VERSION = "0.5.0"


class SSTJsonExportError(RuntimeError):
    """Raised when a model cannot be converted to valid SST JSON."""


@dataclass
class SSTExportReport:
    """Structured readiness report for SST JSON export."""

    errors: list[Any] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)

    @property
    def can_export(self) -> bool:
        """Return true when no blocking export errors are present."""
        return not self.errors

    @property
    def issues(self) -> list[Any]:
        """Return errors followed by warnings for display/reporting."""
        return [*self.errors, *self.warnings]

    def raise_for_errors(self) -> None:
        """Raise :class:`SSTJsonExportError` when blocking errors exist."""
        if not self.errors:
            return

        lines = ["FUSE model is not ready for SST JSON export:", ""]
        for issue in self.errors[:25]:
            object_name = getattr(issue, "object_name", "Project") or "Project"
            message = getattr(issue, "message", str(issue))
            lines.append(f"- {object_name}: {message}")

        if len(self.errors) > 25:
            lines.append(f"...and {len(self.errors) - 25} more error(s).")

        raise SSTJsonExportError("\n".join(lines))


def validation_issue(
    issue_type: str,
    object_name: str,
    message: str,
    *,
    severity: str = "error",
    node_id: int | None = None,
    link_id: int | None = None,
    attachment_id: int | None = None,
    parameter_name: str | None = None,
):
    """Create a core validation issue from SST exporter context."""
    from fuse.core.model.validation import ValidationIssue

    return ValidationIssue(
        issue_type=issue_type,
        object_name=object_name,
        message=message,
        node_id=node_id,
        link_id=link_id,
        attachment_id=attachment_id,
        parameter_name=parameter_name,
        severity=severity,
    )


def clean_value(value: Any) -> Any:
    """
    Keep SST parameter values simple and JSON-safe.

    Most SST parameters are strings in practice, but JSON can safely carry
    booleans, numbers, strings, arrays, and objects if FUSE later supports
    typed parameter editors.
    """
    if value is None:
        return ""

    return value


def non_empty_params(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return parameters after dropping empty string/None values."""
    result: dict[str, Any] = {}

    for key, value in sorted(parameters.items(), key=lambda item: str(item[0])):
        if key is None:
            continue

        key_text = str(key).strip()

        if not key_text:
            continue

        cleaned = clean_value(value)

        if cleaned is None:
            continue

        if isinstance(cleaned, str) and cleaned.strip() == "":
            continue

        result[key_text] = cleaned

    return result


def sst_component_type_for_node(node) -> str:
    """
    Convert a FUSE component node into an SST component type.

    SST component types are normally:
        element.component

    Example:
        memHierarchy.Cache
        merlin.hr_router
    """
    element = getattr(node.component, "element", "") or ""
    name = getattr(node.component, "name", "") or ""

    element = str(element).strip()
    name = str(name).strip()

    if not name:
        raise SSTJsonExportError(
            f"Component instance '{node.instance_name}' has no component type name."
        )

    if not element:
        return name

    return f"{element}.{name}"


def build_partition(node) -> dict[str, int] | None:
    """
    Optional SST partition metadata.

    FUSE does not need to emit this yet unless you later add rank/thread fields
    to the properties panel. This function already supports common attribute
    names so future UI additions do not require rewriting the exporter.
    """
    rank = getattr(node, "rank", None)
    thread = getattr(node, "thread", None)

    if rank is None and thread is None:
        return None

    return {
        "rank": int(rank or 0),
        "thread": int(thread or 0),
    }


def build_sst_component(node) -> dict[str, Any]:
    """
    Build one SST JSON component object.

    Field order matters for readability and is also safer for SST's streaming
    reader behavior: name and type are emitted first.
    """
    component: dict[str, Any] = {
        "name": node.instance_name,
        "type": sst_component_type_for_node(node),
    }

    params = non_empty_params(getattr(node, "parameters", {}) or {})

    if params:
        component["params"] = params

    partition = build_partition(node)

    if partition is not None:
        component["partition"] = partition

    return component


def build_sst_component_tree(
    node,
    attachments_by_parent_id: dict[int, list],
    nodes_by_id: dict[int, object],
) -> dict[str, Any]:
    """
    Build a component/subcomponent tree for SST JSON export.

    Attached child subcomponents are nested under their parent with the slot
    name that should be used by SST's subcomponent assignment mechanism.
    """
    component = build_sst_component(node)
    children = []

    for attachment in sorted(
        attachments_by_parent_id.get(node.node_id, []),
        key=lambda item: (str(item.slot_name), str(item.name), int(item.attachment_id)),
    ):
        child = nodes_by_id.get(attachment.child_node_id)
        if child is None:
            raise SSTJsonExportError(
                f"Cannot export subcomponent attachment '{attachment.name}': "
                f"missing child node {attachment.child_node_id}."
            )

        child_json = build_sst_component_tree(
            child,
            attachments_by_parent_id,
            nodes_by_id,
        )
        child_json["slot_name"] = attachment.slot_name
        children.append(child_json)

    if children:
        component["subcomponents"] = children

    return component


def source_link_latency(link) -> str:
    """Return the SST source latency for a link, including legacy fallback."""
    latency = (
        getattr(link, "source_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def target_link_latency(link) -> str:
    """Return the SST target latency for a link, including legacy fallback."""
    latency = (
        getattr(link, "target_latency", "")
        or getattr(link, "latency", "")
        or DEFAULT_LINK_LATENCY
    )
    return str(latency).strip() or DEFAULT_LINK_LATENCY


def has_explicit_source_latency(link) -> bool:
    """Return whether a link explicitly defines source latency."""
    return bool(str(getattr(link, "source_latency", "") or "").strip())


def has_explicit_target_latency(link) -> bool:
    """Return whether a link explicitly defines target latency."""
    return bool(str(getattr(link, "target_latency", "") or "").strip())


def current_node_name(nodes_by_id: dict[int, object] | None, node_id: int, fallback: str) -> str:
    """Resolve a node id to its current instance name for link export."""
    if nodes_by_id is None:
        return fallback

    node = nodes_by_id.get(node_id)
    if node is None:
        return fallback

    return getattr(node, "instance_name", "") or fallback


def build_sst_link(link, nodes_by_id: dict[int, object] | None = None) -> dict[str, Any]:
    """
    Build one SST JSON link object.

    If nodes_by_id is provided, endpoint component names are resolved from the
    current component instances. This prevents stale serialized link endpoint
    names from leaking into the generated SST JSON after a user renames a
    component.
    """
    name = getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}"
    source_latency = source_link_latency(link)
    target_latency = target_link_latency(link)

    source_component = current_node_name(
        nodes_by_id,
        getattr(link, "source_node_id", None),
        getattr(link, "source_component_name", "") or "",
    )
    source_port = getattr(link, "source_port", "") or ""
    target_component = current_node_name(
        nodes_by_id,
        getattr(link, "target_node_id", None),
        getattr(link, "target_component_name", "") or "",
    )
    target_port = getattr(link, "target_port", "") or ""

    missing = []

    if not source_component:
        missing.append("source component")
    if not source_port:
        missing.append("source port")
    if not target_component:
        missing.append("target component")
    if not target_port:
        missing.append("target port")

    if missing:
        raise SSTJsonExportError(
            f"Cannot export link '{name}': missing {', '.join(missing)}."
        )

    return {
        "name": name,
        "noCut": bool(getattr(link, "no_cut", False)),
        "nonlocal": bool(getattr(link, "nonlocal_link", False)),
        "left": {
            "component": source_component,
            "port": source_port,
            "latency": source_latency,
        },
        "right": {
            "component": target_component,
            "port": target_port,
            "latency": target_latency,
        },
    }


def port_names_for_node(node) -> set[str]:
    """Return concrete port names available on a node."""
    names = set()

    if hasattr(node, "expanded_port_names"):
        try:
            names.update(str(name) for name in node.expanded_port_names())
        except Exception:
            pass

    for port in getattr(node, "ports", []) or []:
        name = getattr(port, "name", "")
        if name:
            names.add(str(name))

    return names


def node_is_sst(node) -> bool:
    """Return true when a node belongs to the SST plugin."""
    return (getattr(node.component, "plugin_id", "") or "core") == "sst"


def node_is_subcomponent(node) -> bool:
    """Return true when a node represents an SST SubComponent."""
    return bool(int(getattr(node.component, "is_subcomp", 0) or 0))


def validate_sst_json_export(scene) -> SSTExportReport:
    """Validate that a scene can be exported to SST JSON without repair."""
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    scene = flatten_scene_for_export(scene)
    report = SSTExportReport()
    nodes = list(scene.component_items())
    links = list(getattr(scene, "links", []) or [])
    attachments = list(getattr(scene, "subcomp_attachments", []) or [])
    nodes_by_id = {node.node_id: node for node in nodes}
    attached_child_ids = {attachment.child_node_id for attachment in attachments}

    def add_issue(issue):
        if getattr(issue, "severity", "error") == "warning":
            report.warnings.append(issue)
        else:
            report.errors.append(issue)

    if not nodes:
        add_issue(
            validation_issue(
                "sst_export",
                "Project",
                "There are no components to export to SST JSON.",
            )
        )

    target_ids = {
        str(getattr(node.component, "target_id", "") or "")
        for node in nodes
        if str(getattr(node.component, "target_id", "") or "")
    }
    if len(target_ids) > 1:
        add_issue(
            validation_issue(
                "sst_export",
                "Project",
                "SST JSON export requires all SST components to use the same target/version; "
                f"found {', '.join(sorted(target_ids))}.",
            )
        )

    seen_names: dict[str, int] = {}
    for node in nodes:
        name = str(getattr(node, "instance_name", "") or "").strip()
        if not name:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    "<unnamed component>",
                    "SST JSON export requires every component instance to have a name.",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="name",
                )
            )
        elif name in seen_names:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name,
                    "SST JSON export requires component instance names to be unique.",
                    node_id=getattr(node, "node_id", None),
                    parameter_name="name",
                )
            )
        else:
            seen_names[name] = getattr(node, "node_id", None)

        if not node_is_sst(node):
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name or "<unnamed component>",
                    "SST JSON export can only include SST components. Remove non-SST components or choose another exporter.",
                    node_id=getattr(node, "node_id", None),
                )
            )

        try:
            sst_component_type_for_node(node)
        except SSTJsonExportError as exc:
            add_issue(
                validation_issue(
                    "sst_export_component",
                    name or "<unnamed component>",
                    str(exc),
                    node_id=getattr(node, "node_id", None),
                )
            )

        if node_is_subcomponent(node) and node.node_id not in attached_child_ids:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    name or "<unnamed subcomponent>",
                    "SST SubComponent instances must be attached to a parent slot before export.",
                    node_id=getattr(node, "node_id", None),
                )
            )

    for attachment in attachments:
        parent = nodes_by_id.get(attachment.parent_node_id)
        child = nodes_by_id.get(attachment.child_node_id)
        object_name = getattr(attachment, "name", "SubComponent attachment")

        if parent is None:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment parent node is missing.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                )
            )
        if child is None:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment child node is missing.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                )
            )
            continue

        if child is not None and not node_is_subcomponent(child):
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "Only SST SubComponent instances can be exported as subcomponent attachments.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                    node_id=getattr(child, "node_id", None),
                )
            )

        if not str(getattr(attachment, "slot_name", "") or "").strip():
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    "SubComponent attachment is missing the parent slot name.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                    parameter_name="slot_name",
                )
            )

        required = str(getattr(attachment, "required_interface", "") or "").strip()
        provided = str(getattr(attachment, "provided_interface", "") or "").strip()
        if required and provided and required != provided:
            add_issue(
                validation_issue(
                    "sst_export_subcomponent",
                    object_name,
                    f"SubComponent interface mismatch: slot requires {required}, but subcomponent provides {provided}.",
                    attachment_id=getattr(attachment, "attachment_id", None),
                    parameter_name="slot_name",
                )
            )
        elif not required or not provided:
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    "SubComponent interface compatibility could not be fully verified from metadata.",
                    severity="warning",
                    attachment_id=getattr(attachment, "attachment_id", None),
                )
            )

    seen_link_names: dict[str, int] = {}
    for link in links:
        object_name = getattr(link, "name", "") or f"link_{getattr(link, 'link_id', '')}"
        link_name = str(getattr(link, "name", "") or "").strip()
        if not link_name:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "SST JSON export requires every link to have a stable name.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="name",
                )
            )
        elif link_name in seen_link_names:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "SST JSON export requires link names to be unique.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="name",
                )
            )
        else:
            seen_link_names[link_name] = getattr(link, "link_id", None)

        source = nodes_by_id.get(getattr(link, "source_node_id", None))
        target = nodes_by_id.get(getattr(link, "target_node_id", None))

        if source is None:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source component no longer exists.",
                    link_id=getattr(link, "link_id", None),
                )
            )
        if target is None:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target component no longer exists.",
                    link_id=getattr(link, "link_id", None),
                )
            )

        if source is not None and not node_is_sst(source):
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source is not an SST component.",
                    link_id=getattr(link, "link_id", None),
                    node_id=getattr(source, "node_id", None),
                )
            )
        if target is not None and not node_is_sst(target):
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target is not an SST component.",
                    link_id=getattr(link, "link_id", None),
                    node_id=getattr(target, "node_id", None),
                )
            )

        source_port = str(getattr(link, "source_port", "") or "").strip()
        target_port = str(getattr(link, "target_port", "") or "").strip()
        if not source_port:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link source port is required for SST JSON export.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="source_port",
                )
            )
        if not target_port:
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    "Link target port is required for SST JSON export.",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="target_port",
                )
            )

        if not has_explicit_source_latency(link):
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    f"Link source latency was not set; exporter will use the default {DEFAULT_LINK_LATENCY} latency.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="source_latency",
                )
            )
        if not has_explicit_target_latency(link):
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    f"Link target latency was not set; exporter will use the default {DEFAULT_LINK_LATENCY} latency.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                    parameter_name="target_latency",
                )
            )

        if source is not None and source_port:
            ports = port_names_for_node(source)
            if ports and source_port not in ports:
                add_issue(
                    validation_issue(
                        "sst_export_warning",
                        object_name,
                        f"Source port '{source_port}' was not found in the source component metadata.",
                        severity="warning",
                        link_id=getattr(link, "link_id", None),
                        node_id=getattr(source, "node_id", None),
                        parameter_name="source_port",
                    )
                )
        if target is not None and target_port:
            ports = port_names_for_node(target)
            if ports and target_port not in ports:
                add_issue(
                    validation_issue(
                        "sst_export_warning",
                        object_name,
                        f"Target port '{target_port}' was not found in the target component metadata.",
                        severity="warning",
                        link_id=getattr(link, "link_id", None),
                        node_id=getattr(target, "node_id", None),
                        parameter_name="target_port",
                    )
                )

        if getattr(link, "compatibility_severity", "ok") == "warning":
            add_issue(
                validation_issue(
                    "sst_export_warning",
                    object_name,
                    getattr(link, "compatibility_message", "") or "Link compatibility is uncertain.",
                    severity="warning",
                    link_id=getattr(link, "link_id", None),
                )
            )
        elif getattr(link, "compatibility_severity", "ok") == "error":
            add_issue(
                validation_issue(
                    "sst_export_link",
                    object_name,
                    getattr(link, "compatibility_message", "") or "Link compatibility failed.",
                    link_id=getattr(link, "link_id", None),
                )
            )

    return report


def build_sst_json_dict(
    scene,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
    include_metadata: bool = False,
) -> dict[str, Any]:
    """
    Build the SST JSON configuration dictionary from the current FUSE scene.

    This is intentionally separate from writing the file so tests can assert
    on the generated dictionary directly.
    """
    from fuse.core.model.composite_flattening import flatten_scene_for_export

    scene = flatten_scene_for_export(scene)
    nodes = sorted(scene.component_items(), key=lambda node: (str(node.instance_name), int(node.node_id)))
    nodes_by_id = {node.node_id: node for node in nodes}

    attachments = sorted(
        list(getattr(scene, "subcomp_attachments", []) or []),
        key=lambda item: (int(item.parent_node_id), str(item.slot_name), str(item.name), int(item.attachment_id)),
    )
    attached_child_ids = {attachment.child_node_id for attachment in attachments}
    attachments_by_parent_id: dict[int, list] = {}

    for attachment in attachments:
        attachments_by_parent_id.setdefault(
            attachment.parent_node_id,
            [],
        ).append(attachment)

    components = [
        build_sst_component_tree(node, attachments_by_parent_id, nodes_by_id)
        for node in nodes
        if node.node_id not in attached_child_ids
    ]

    links = [
        build_sst_link(link, nodes_by_id=nodes_by_id)
        for link in sorted(getattr(scene, "links", []) or [], key=lambda item: (str(item.name), int(item.link_id)))
    ]

    data: dict[str, Any] = {
        "program_options": program_options or {},
    }

    if shared_params:
        data["shared_params"] = shared_params

    data.update(
        {
            "statistics_options": statistics_options or {},
            "components": components,
            "statistics_group": statistics_group or [],
            "links": links,
        }
    )

    if include_metadata:
        data["metadata"] = {
            "generator": "FUSE",
            "format": SST_EXPORT_FORMAT,
            "schema_version": SST_EXPORT_SCHEMA_VERSION,
            "component_count": len(components),
            "link_count": len(links),
        }

    return data


def export_sst_json(
    scene,
    output_path: str | Path,
    program_options: dict[str, Any] | None = None,
    statistics_options: dict[str, Any] | None = None,
    shared_params: list[dict[str, Any]] | None = None,
    statistics_group: list[dict[str, Any]] | None = None,
    validate: bool = True,
    report_path: str | Path | None = None,
) -> Path:
    """
    Export the current FUSE scene to an SST JSON configuration file.
    """
    output_path = Path(output_path)

    report = validate_sst_json_export(scene)
    if validate:
        report.raise_for_errors()

    data = build_sst_json_dict(
        scene=scene,
        program_options=program_options,
        statistics_options=statistics_options,
        shared_params=shared_params,
        statistics_group=statistics_group,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        json.dumps(data, indent=2) + "\n",
        encoding="utf-8",
    )

    if report_path is not None:
        export_sst_report(report, report_path)

    return output_path


def export_sst_report(report: SSTExportReport, output_path: str | Path) -> Path:
    """Write an SST export validation report beside the exported artifact."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def issue_to_dict(issue) -> dict[str, Any]:
        return {
            "severity": getattr(issue, "severity", "error"),
            "type": getattr(issue, "issue_type", ""),
            "object": getattr(issue, "object_name", ""),
            "message": getattr(issue, "message", ""),
            "nodeId": getattr(issue, "node_id", None),
            "linkId": getattr(issue, "link_id", None),
            "attachmentId": getattr(issue, "attachment_id", None),
            "parameter": getattr(issue, "parameter_name", None),
        }

    data = {
        "canExport": report.can_export,
        "errors": [issue_to_dict(issue) for issue in report.errors],
        "warnings": [issue_to_dict(issue) for issue in report.warnings],
    }
    output_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return output_path
