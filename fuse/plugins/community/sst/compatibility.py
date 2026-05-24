# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fuse.core.persistence.database import get_connection
from fuse.plugin_api.interfaces import CompatibilityIssue, CompatibilityReport
from fuse.plugins.community.sst.db_utils import get_component_details


@dataclass(frozen=True)
class TargetComponentMatch:
    component_id: int
    framework_version_id: int
    element_name: str
    component_name: str
    is_subcomp: int
    category: str
    iface: str
    icon_path: str
    framework_version: str
    target_label: str


def _node_identity(node) -> tuple[str, str, int]:
    component = node.component
    return (
        str(getattr(component, "element", "") or ""),
        str(getattr(component, "name", "") or ""),
        int(getattr(component, "is_subcomp", 0) or 0),
    )


def _issue(
    severity: str,
    node,
    message: str,
    parameter_name: str | None = None,
    fix_kind: str = "",
    fix_data: dict | None = None,
) -> CompatibilityIssue:
    return CompatibilityIssue(
        severity=severity,
        object_name=getattr(node, "instance_name", "<unknown>"),
        node_id=getattr(node, "node_id", None),
        parameter_name=parameter_name,
        message=message,
        fix_kind=fix_kind,
        fix_data=fix_data or {},
    )


def _link_issue(severity: str, link, message: str) -> CompatibilityIssue:
    return CompatibilityIssue(
        severity=severity,
        object_name=getattr(link, "name", "<unknown link>"),
        link_id=getattr(link, "link_id", None),
        message=message,
    )


def find_target_component(
    target_id: str | int,
    element_name: str,
    component_name: str,
    is_subcomp: int,
) -> TargetComponentMatch | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                c.id AS component_id,
                c.framework_version_id,
                e.name AS element_name,
                c.name AS component_name,
                c.is_subcomp,
                c.category,
                c.iface,
                c.icon_path,
                fv.version AS framework_version,
                fv.label AS target_label
            FROM sst_components c
            JOIN sst_elements e ON c.parent_id = e.id
            JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
            WHERE c.framework_version_id = ?
              AND e.framework_version_id = ?
              AND e.name = ?
              AND c.name = ?
              AND c.is_subcomp = ?
            LIMIT 1
            """,
            (int(target_id), int(target_id), element_name, component_name, int(is_subcomp)),
        ).fetchone()

    if row is None:
        return None

    return TargetComponentMatch(
        component_id=int(row["component_id"]),
        framework_version_id=int(row["framework_version_id"]),
        element_name=row["element_name"] or "",
        component_name=row["component_name"] or "",
        is_subcomp=int(row["is_subcomp"] or 0),
        category=row["category"] or "",
        iface=row["iface"] or "",
        icon_path=row["icon_path"] or "",
        framework_version=row["framework_version"] or "",
        target_label=row["target_label"] or f"SST {row['framework_version']}",
    )


def _parameters_by_name(details: dict[str, Any]) -> dict[str, dict]:
    return {str(parameter.get("name", "")): parameter for parameter in details.get("parameters", [])}


def _ports_by_name(details: dict[str, Any]) -> dict[str, dict]:
    return {str(port.get("name", "")): port for port in details.get("ports", [])}


def _component_items_for_plugin(scene, plugin_id: str):
    return [
        node
        for node in scene.component_items()
        if getattr(node.component, "plugin_id", "") == plugin_id
    ]


def validate_scene_for_target(scene, target_id: str, plugin_id: str = "sst") -> CompatibilityReport:
    """
    Validate whether the current scene can be represented using one SST target.

    This does not mutate the model. It answers: "Would this model work against
    the destination SST catalog?"
    """
    source_target_ids = {
        str(getattr(node.component, "target_id", "") or "")
        for node in _component_items_for_plugin(scene, plugin_id)
    }
    source_target_ids.discard("")
    source_target_id = ",".join(sorted(source_target_ids)) if source_target_ids else ""

    report = CompatibilityReport(
        plugin_id=plugin_id,
        source_target_id=source_target_id,
        destination_target_id=str(target_id),
    )

    node_target_details: dict[int, dict[str, Any]] = {}

    for node in _component_items_for_plugin(scene, plugin_id):
        element_name, component_name, is_subcomp = _node_identity(node)

        if not element_name or not component_name:
            report.issues.append(
                _issue(
                    "error",
                    node,
                    "Component identity is incomplete, so it cannot be matched to the selected SST target.",
                )
            )
            continue

        match = find_target_component(target_id, element_name, component_name, is_subcomp)

        if match is None:
            kind = "subcomponent" if is_subcomp else "component"
            report.issues.append(
                _issue(
                    "error",
                    node,
                    f"SST {kind} '{element_name}.{component_name}' is not available in target {target_id}.",
                )
            )
            continue

        details = get_component_details(match.component_id, target_id)
        if not details:
            report.issues.append(
                _issue(
                    "error",
                    node,
                    f"Could not load target metadata for '{element_name}.{component_name}'.",
                )
            )
            continue

        node_target_details[node.node_id] = details
        target_params = _parameters_by_name(details)

        for name, value in sorted(getattr(node, "parameters", {}).items()):
            if name not in target_params:
                report.issues.append(
                    _issue(
                        "warning",
                        node,
                        f"Parameter '{name}' is not defined by the selected SST target and may be ignored or invalid.",
                        parameter_name=name,
                    )
                )

        for name, parameter in sorted(target_params.items()):
            required = bool(parameter.get("required"))
            default_value = str(parameter.get("default_val", "") or "")
            value = str(getattr(node, "parameters", {}).get(name, default_value) or "").strip()

            if value == "<required>":
                value = ""

            if required and not value:
                report.issues.append(
                    _issue(
                        "error",
                        node,
                        f"Required parameter '{name}' has no value for the selected SST target.",
                        parameter_name=name,
                    )
                )

    nodes_by_id = {node.node_id: node for node in scene.component_items()}

    for link in scene.links:
        source_node = nodes_by_id.get(link.source_node_id)
        target_node = nodes_by_id.get(link.target_node_id)

        if source_node is None:
            report.issues.append(_link_issue("error", link, "Source component no longer exists."))
            continue

        if target_node is None:
            report.issues.append(_link_issue("error", link, "Target component no longer exists."))
            continue

        if getattr(source_node.component, "plugin_id", "") != plugin_id:
            continue

        if getattr(target_node.component, "plugin_id", "") != plugin_id:
            continue

        source_details = node_target_details.get(source_node.node_id)
        target_details = node_target_details.get(target_node.node_id)

        if source_details is None or target_details is None:
            # The component-level errors above are more precise.
            continue

        source_ports = _ports_by_name(source_details)
        target_ports = _ports_by_name(target_details)

        if link.source_port not in source_ports:
            report.issues.append(
                _link_issue(
                    "error",
                    link,
                    (
                        f"Source port '{link.source_port}' does not exist on "
                        f"'{source_node.component.element}.{source_node.component.name}' in target {target_id}."
                    ),
                )
            )

        if link.target_port not in target_ports:
            report.issues.append(
                _link_issue(
                    "error",
                    link,
                    (
                        f"Target port '{link.target_port}' does not exist on "
                        f"'{target_node.component.element}.{target_node.component.name}' in target {target_id}."
                    ),
                )
            )

    return report


def format_compatibility_report(report: CompatibilityReport, limit: int = 50) -> str:
    if not report.issues:
        return "The model is compatible with the selected target."

    lines = [
        f"Compatibility check for target {report.destination_target_id}:",
        "",
    ]

    for issue in report.issues[:limit]:
        label = issue.severity.upper()
        lines.append(f"[{label}] {issue.object_name}: {issue.message}")

    if len(report.issues) > limit:
        lines.append("")
        lines.append(f"...and {len(report.issues) - limit} more issue(s).")

    return "\n".join(lines)
