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
import json
from datetime import datetime, timezone
from pathlib import Path

from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, SubcompAttachmentItem
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment, SCHEMA_VERSION
from fuse.core.model.project_settings import ProjectSettings


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def component_node_to_save_dict(node: ComponentNodeItem) -> dict:
    position = node.pos()

    return {
        "id": node.node_id,
        "element": node.component.element,
        "name": node.component.name,
        "pluginId": node.component.plugin_id,
        "targetId": node.component.target_id,
        "targetLabel": node.component.target_label,
        "frameworkVersion": node.component.framework_version,
        "componentId": node.component.component_id,
        "isSubcomponent": node.component.is_subcomp,
        "category": node.component.category,
        "functionality": node.component.functionality,
        "description": node.component.description,
        "iconPath": node.icon_path,
        "interface": node.component.iface,
        "displayNameOverride": node.component.display_name_override,
        "instanceName": node.instance_name,
        "parameters": node.parameters,
        "variablePortCounts": getattr(node, "variable_port_counts", {}),
        "position": {
            "x": position.x(),
            "y": position.y(),
        },
    }


def model_link_to_save_dict(link: ModelLink) -> dict:
    return {
        "id": link.link_id,
        "name": link.name,
        "latency": link.latency,
        "sourceLatency": getattr(link, "source_latency", link.latency),
        "targetLatency": getattr(link, "target_latency", link.latency),
        "pluginId": getattr(link, "plugin_id", ""),
        "compatibility": {
            "severity": getattr(link, "compatibility_severity", "ok"),
            "code": getattr(link, "compatibility_code", ""),
            "message": getattr(link, "compatibility_message", ""),
        },
        "pluginMetadata": getattr(link, "plugin_metadata", {}) or {},
        "type": link.link_type,
        "source": {
            "nodeId": link.source_node_id,
            "componentName": link.source_component_name,
            "port": link.source_port,
        },
        "target": {
            "nodeId": link.target_node_id,
            "componentName": link.target_component_name,
            "port": link.target_port,
        },
    }


def subcomp_attachment_to_save_dict(attachment: ModelSubcompAttachment) -> dict:
    return {
        "id": attachment.attachment_id,
        "name": attachment.name,
        "pluginId": getattr(attachment, "plugin_id", ""),
        "parent": {
            "nodeId": attachment.parent_node_id,
            "componentName": attachment.parent_component_name,
            "slotName": attachment.slot_name,
        },
        "child": {
            "nodeId": attachment.child_node_id,
            "componentName": attachment.child_component_name,
        },
        "requiredInterface": attachment.required_interface,
        "providedInterface": attachment.provided_interface,
        "compatibility": {
            "severity": attachment.compatibility_severity,
            "code": attachment.compatibility_code,
            "message": attachment.compatibility_message,
        },
        "pluginMetadata": getattr(attachment, "plugin_metadata", {}) or {},
    }


def build_project_dict(
    scene: ModelScene,
    model_view: ModelView,
    project_name: str,
    active_plugin_id: str | None = None,
    active_target_id: str | None = None,
    project_settings: ProjectSettings | None = None,
) -> dict:
    if project_settings is not None:
        active_plugin_id = project_settings.active_plugin_id
        active_settings = project_settings.active_plugin_settings()
        active_target_id = active_settings.target_id if active_settings else ""

    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": {
            "name": project_name or "Untitled FUSE Model",
            "updatedAt": now_iso(),
        },
        "projectSettings": (
            project_settings.to_dict()
            if project_settings is not None
            else ProjectSettings(
                project_name=project_name or "Untitled FUSE Model",
                active_plugin_id=active_plugin_id or "",
            ).to_dict()
        ),
        "pluginSettings": (
            project_settings.to_dict().get("plugins", {})
            if project_settings is not None
            else {}
        ),
        "activeTarget": {
            "pluginId": active_plugin_id or "",
            "targetId": active_target_id or "",
        },
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
        "editor": {
            "sceneRect": {
                "x": scene.sceneRect().x(),
                "y": scene.sceneRect().y(),
                "width": scene.sceneRect().width(),
                "height": scene.sceneRect().height(),
            },
            "viewCenter": {
                "x": model_view.mapToScene(model_view.viewport().rect().center()).x(),
                "y": model_view.mapToScene(model_view.viewport().rect().center()).y(),
            },
        },
    }


def validate_project_dict(project: dict) -> None:
    if not isinstance(project, dict):
        raise ValueError("Invalid project file: root must be a JSON object.")

    if project.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported project schemaVersion: {project.get('schemaVersion')!r}"
        )

    if not isinstance(project.get("components"), list):
        raise ValueError("Invalid project file: missing components list.")

    if not isinstance(project.get("links"), list):
        raise ValueError("Invalid project file: missing links list.")


def load_project_file(file_path: str | Path) -> dict:
    with Path(file_path).open("r", encoding="utf-8") as file:
        project = json.load(file)

    validate_project_dict(project)
    return project


def save_project_file(project: dict, file_path: str | Path) -> None:
    with Path(file_path).open("w", encoding="utf-8") as file:
        json.dump(project, file, indent=2)
        file.write("\n")


def load_project_into_scene(project: dict, scene: ModelScene) -> None:
    validate_project_dict(project)
    scene.clear_model()

    nodes_by_id: dict[int, ComponentNodeItem] = {}

    for component_data in project["components"]:
        icon_path = component_data.get("iconPath", "") or component_data.get("icon_path", "")

        component = ComponentDefinition(
            plugin_id=component_data.get("pluginId", component_data.get("plugin_id", "core")),
            target_id=component_data.get("targetId", component_data.get("target_id", "")),
            target_label=component_data.get("targetLabel", ""),
            framework_version=component_data.get("frameworkVersion", ""),
            component_id=component_data.get("componentId"),
            element=component_data.get("element", ""),
            name=component_data.get("name", ""),
            is_subcomp=int(component_data.get("isSubcomponent", 0)),
            category=component_data.get("category", ""),
            functionality=component_data.get("functionality", ""),
            description=component_data.get("description", ""),
            iface=component_data.get("interface", ""),
            icon_path=icon_path,
            display_name_override=component_data.get("displayNameOverride", ""),
        )

        node_id = int(component_data["id"])
        node = ComponentNodeItem(
            component,
            node_id=node_id,
            parameters=component_data.get("parameters", {}),
            instance_name=component_data.get("instanceName"),
            variable_port_counts=component_data.get("variablePortCounts", {}),
        )

        position = component_data.get("position", {})
        node.setPos(float(position.get("x", 0)), float(position.get("y", 0)))

        scene.addItem(node)
        nodes_by_id[node_id] = node

    max_link_id = 0

    for link_data in project["links"]:
        source = link_data.get("source", {})
        target = link_data.get("target", {})

        source_node_id = int(source["nodeId"])
        target_node_id = int(target["nodeId"])
        source_port_name = source["port"]
        target_port_name = target["port"]

        source_port = scene.find_port(source_node_id, source_port_name)
        target_port = scene.find_port(target_node_id, target_port_name)

        if source_port is None:
            raise ValueError(
                f"Could not restore link {link_data.get('name')}: "
                f"missing source port {source_node_id}.{source_port_name}"
            )

        if target_port is None:
            raise ValueError(
                f"Could not restore link {link_data.get('name')}: "
                f"missing target port {target_node_id}.{target_port_name}"
            )

        link_id = int(link_data["id"])
        max_link_id = max(max_link_id, link_id)

        legacy_latency = link_data.get("latency", "1ns")
        compatibility = link_data.get("compatibility", {}) or {}

        link = ModelLink(
            link_id=link_id,
            name=link_data.get("name", f"link_{link_id}"),
            source_node_id=source_node_id,
            source_component_name=source.get(
                "componentName",
                nodes_by_id[source_node_id].instance_name,
            ),
            source_port=source_port_name,
            target_node_id=target_node_id,
            target_component_name=target.get(
                "componentName",
                nodes_by_id[target_node_id].instance_name,
            ),
            target_port=target_port_name,
            source_latency=link_data.get("sourceLatency", legacy_latency),
            target_latency=link_data.get("targetLatency", legacy_latency),
            link_type=link_data.get("type", "point_to_point"),
            plugin_id=link_data.get("pluginId", ""),
            compatibility_severity=compatibility.get("severity", "ok"),
            compatibility_code=compatibility.get("code", ""),
            compatibility_message=compatibility.get("message", ""),
            plugin_metadata=link_data.get("pluginMetadata", {}) or {},
        )

        scene.links.append(link)
        connection = ConnectionItem(link, source_port, target_port)
        scene.addItem(connection)
        connection.update_position()

    scene._next_link_id = max_link_id + 1

    max_attachment_id = 0

    for attachment_data in project.get("subcompAttachments", []):
        parent = attachment_data.get("parent", {})
        child = attachment_data.get("child", {})

        parent_node_id = int(parent["nodeId"])
        child_node_id = int(child["nodeId"])
        slot_name = parent["slotName"]

        slot_connector = scene.find_subcomp_connector(
            parent_node_id,
            slot_name,
            role="slot",
        )
        interface_connector = scene.find_subcomp_connector(
            child_node_id,
            child.get("connectorName", ""),
            role="interface",
        )

        if interface_connector is None:
            for candidate in getattr(nodes_by_id[child_node_id], "subcomp_connectors", []):
                if getattr(candidate, "role", "") == "interface":
                    interface_connector = candidate
                    break

        if slot_connector is None:
            raise ValueError(
                f"Could not restore subcomponent attachment {attachment_data.get('name')}: "
                f"missing parent slot {parent_node_id}.{slot_name}"
            )

        if interface_connector is None:
            raise ValueError(
                f"Could not restore subcomponent attachment {attachment_data.get('name')}: "
                f"missing child interface connector for node {child_node_id}"
            )

        attachment_id = int(attachment_data["id"])
        max_attachment_id = max(max_attachment_id, attachment_id)
        compatibility = attachment_data.get("compatibility", {}) or {}

        attachment = ModelSubcompAttachment(
            attachment_id=attachment_id,
            name=attachment_data.get("name", f"subcomp_attachment_{attachment_id}"),
            parent_node_id=parent_node_id,
            parent_component_name=parent.get(
                "componentName",
                nodes_by_id[parent_node_id].instance_name,
            ),
            slot_name=slot_name,
            child_node_id=child_node_id,
            child_component_name=child.get(
                "componentName",
                nodes_by_id[child_node_id].instance_name,
            ),
            required_interface=attachment_data.get("requiredInterface", ""),
            provided_interface=attachment_data.get("providedInterface", ""),
            compatibility_severity=compatibility.get("severity", "ok"),
            compatibility_code=compatibility.get("code", ""),
            compatibility_message=compatibility.get("message", ""),
            plugin_id=attachment_data.get("pluginId", ""),
            plugin_metadata=attachment_data.get("pluginMetadata", {}) or {},
        )

        scene.subcomp_attachments.append(attachment)
        item = SubcompAttachmentItem(attachment, slot_connector, interface_connector)
        scene.addItem(item)
        item.update_position()

    scene._next_subcomp_attachment_id = max_attachment_id + 1
    scene.reroute_all_links()
