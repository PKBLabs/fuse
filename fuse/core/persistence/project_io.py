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

from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.model.models import ComponentDefinition, ModelLink, SCHEMA_VERSION


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def component_node_to_save_dict(node: ComponentNodeItem) -> dict:
    position = node.pos()

    return {
        "id": node.node_id,
        "element": node.component.element,
        "name": node.component.name,
        "pluginId": node.component.plugin_id,
        "componentId": node.component.component_id,
        "isSubcomponent": node.component.is_subcomp,
        "category": node.component.category,
        "iconPath": node.icon_path,
        "interface": node.component.iface,
        "instanceName": node.instance_name,
        "parameters": node.parameters,
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


def build_project_dict(scene: ModelScene, model_view: ModelView, project_name: str) -> dict:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "project": {
            "name": project_name or "Untitled SST Model",
            "updatedAt": now_iso(),
        },
        "components": [
            component_node_to_save_dict(node)
            for node in scene.component_items()
        ],
        "links": [
            model_link_to_save_dict(link)
            for link in sorted(scene.links, key=lambda item: item.link_id)
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
            component_id=component_data.get("componentId"),
            element=component_data.get("element", ""),
            name=component_data.get("name", ""),
            is_subcomp=int(component_data.get("isSubcomponent", 0)),
            category=component_data.get("category", ""),
            iface=component_data.get("interface", ""),
            icon_path=icon_path,
        )

        node_id = int(component_data["id"])
        node = ComponentNodeItem(
            component,
            node_id=node_id,
            parameters=component_data.get("parameters", {}),
            instance_name=component_data.get("instanceName"),
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

        link = ModelLink(
            link_id=link_id,
            name=link_data.get("name", f"link_{link_id}"),
            latency=link_data.get("latency", "1ns"),
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
            link_type=link_data.get("type", "point_to_point"),
        )

        scene.links.append(link)
        connection = ConnectionItem(link, source_port, target_port)
        scene.addItem(connection)
        connection.update_position()

    scene._next_link_id = max_link_id + 1
    scene.reroute_all_links()