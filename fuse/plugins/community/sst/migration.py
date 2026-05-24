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

from fuse.plugin_api.interfaces import MigrationPlan
from fuse.plugins.community.sst.compatibility import (
    find_target_component,
    validate_scene_for_target,
)
from fuse.plugins.community.sst.db_utils import get_component_details


def _target_parameters(details: dict) -> dict[str, dict]:
    return {str(parameter.get("name", "")): parameter for parameter in details.get("parameters", [])}


def plan_scene_migration(scene, target_id: str, plugin_id: str = "sst") -> MigrationPlan:
    report = validate_scene_for_target(scene, target_id=target_id, plugin_id=plugin_id)
    source_target_ids = {
        str(getattr(node.component, "target_id", "") or "")
        for node in scene.component_items()
        if getattr(node.component, "plugin_id", "") == plugin_id
    }
    source_target_ids.discard("")
    source_target_id = ",".join(sorted(source_target_ids)) if source_target_ids else ""

    plan = MigrationPlan(
        plugin_id=plugin_id,
        source_target_id=source_target_id,
        destination_target_id=str(target_id),
        report=report,
    )

    if report.has_errors:
        return plan

    for node in scene.component_items():
        if getattr(node.component, "plugin_id", "") != plugin_id:
            continue

        match = find_target_component(
            target_id=target_id,
            element_name=node.component.element,
            component_name=node.component.name,
            is_subcomp=int(node.component.is_subcomp or 0),
        )

        if match is None:
            # Should already be covered by report errors.
            continue

        details = get_component_details(match.component_id, target_id) or {}
        target_params = _target_parameters(details)
        current_params = dict(getattr(node, "parameters", {}) or {})
        migrated_params = {}

        for name, parameter in target_params.items():
            default_value = str(parameter.get("default_val", "") or "")

            if name in current_params:
                migrated_params[name] = current_params[name]
            elif default_value and default_value != "<required>":
                migrated_params[name] = default_value

        plan.node_updates.append(
            {
                "node_id": node.node_id,
                "component_id": str(match.component_id),
                "target_id": str(match.framework_version_id),
                "target_label": match.target_label,
                "framework_version": match.framework_version,
                "element": match.element_name,
                "name": match.component_name,
                "is_subcomp": match.is_subcomp,
                "category": match.category,
                "iface": match.iface,
                "icon_path": match.icon_path,
                "parameters": migrated_params,
            }
        )

    return plan


def apply_scene_migration(scene, target_id: str, plugin_id: str = "sst") -> MigrationPlan:
    plan = plan_scene_migration(scene, target_id=target_id, plugin_id=plugin_id)

    if not plan.can_apply:
        return plan

    updates_by_node_id = {update["node_id"]: update for update in plan.node_updates}

    for node in scene.component_items():
        update = updates_by_node_id.get(node.node_id)

        if update is None:
            continue

        node.component.component_id = update["component_id"]
        node.component.target_id = update["target_id"]
        node.component.target_label = update["target_label"]
        node.component.framework_version = update["framework_version"]
        node.component.element = update["element"]
        node.component.name = update["name"]
        node.component.is_subcomp = update["is_subcomp"]
        node.component.category = update["category"]
        node.component.iface = update["iface"]
        node.component.icon_path = update["icon_path"]
        node.parameters = update["parameters"]

        if update["icon_path"] and hasattr(node, "set_icon_path"):
            node.set_icon_path(update["icon_path"])

        # Existing ports are preserved. The compatibility report guarantees that
        # all currently connected ports still exist in the destination target.
        # A future enhancement can rebuild unconnected port decorations to show
        # newly added ports immediately after migration.

    if hasattr(scene, "reroute_all_links"):
        scene.reroute_all_links()

    return plan
