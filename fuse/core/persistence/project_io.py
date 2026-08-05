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
"""Read and write FUSE ``.fse`` project files.

This module bridges the live Qt scene objects and the JSON project schema. It
converts graphics items into plain dictionaries, validates serialized projects,
performs atomic file writes, and reconstructs a scene when users open a saved
project.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fuse.core.ui.graphics_items import ComponentNodeItem, ConnectionItem, SubcompAttachmentItem
from fuse.core.ui.model_scene import ModelScene
from fuse.core.ui.model_view import ModelView
from fuse.core.model.composite import CompositePortMapping
from fuse.core.model.composite_mini_model import normalize_mini_model_and_port_mappings
from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment, SCHEMA_VERSION
from fuse.core.model.project_settings import ProjectSettings
from fuse.core.persistence.model_serializer import finalize_project_dict, validate_serialized_project
from fuse.core.plugin_runtime.manager import list_all_targets, load_all_palette_items
from fuse.core.diagnostics import active_operation, breadcrumb


def now_iso() -> str:
    """Return the current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _resolve_restored_link_port_name(node: ComponentNodeItem, port_name: str) -> str:
    """Resolve saved link endpoints against current component port metadata."""

    resolver = getattr(node, "resolve_restored_port_name", None)
    if callable(resolver):
        return str(resolver(port_name))

    return str(port_name or "")


def _text(value) -> str:
    """Return a normalized string for project-file matching."""

    return str(value or "").strip()


def _bool_int(value) -> int:
    """Parse stored integer/bool-ish project fields without raising."""

    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _saved_component_definition(component_data: dict) -> ComponentDefinition:
    """Build a component definition from the exact data stored in the project file."""

    icon_path = component_data.get("iconPath", "") or component_data.get("icon_path", "")
    return ComponentDefinition(
        plugin_id=component_data.get("pluginId", component_data.get("plugin_id", "core")),
        target_id=component_data.get("targetId", component_data.get("target_id", "")),
        target_label=component_data.get("targetLabel", ""),
        framework_version=component_data.get("frameworkVersion", ""),
        component_id=component_data.get("componentId"),
        element=component_data.get("element", ""),
        name=component_data.get("name", ""),
        is_subcomp=_bool_int(component_data.get("isSubcomponent", 0)),
        category=component_data.get("category", ""),
        functionality=component_data.get("functionality", ""),
        description=component_data.get("description", ""),
        iface=component_data.get("interface", ""),
        icon_path=icon_path,
        display_name_override=component_data.get("displayNameOverride", ""),
        is_composite=_bool_int(component_data.get("isComposite", 0)),
        composite_id=component_data.get("compositeId", ""),
    )


def _palette_item_is_subcomponent(item) -> int:
    """Return whether a palette item represents a simulator subcomponent."""

    return 1 if _text(getattr(item, "raw_kind", "")).lower() == "subcomponent" else 0


def _candidate_target_ids_for_saved_component(
    component_data: dict,
    targets: list | None = None,
) -> list[str | None]:
    """Return local target ids likely to contain the saved component.

    Project files store database row ids for targets and components. Those ids are
    only reliable on the machine that saved the file. Prefer the saved target id
    first for same-machine loads, then look up a local target with the same
    plugin/framework version for cross-machine loads.

    ``targets`` is supplied by the project loader so opening a model does not
    re-query plugin target metadata for every saved component.
    """

    plugin_id = _text(component_data.get("pluginId", component_data.get("plugin_id", "")))
    saved_target_id = _text(component_data.get("targetId", component_data.get("target_id", "")))
    framework_version = _text(component_data.get("frameworkVersion", ""))

    candidate_ids: list[str | None] = []
    seen: set[str | None] = set()

    def add_candidate(target_id: str | None) -> None:
        key = _text(target_id) if target_id is not None else None
        if key in seen:
            return
        seen.add(key)
        candidate_ids.append(key)

    if saved_target_id:
        add_candidate(saved_target_id)

    if framework_version:
        if targets is None:
            try:
                targets = list_all_targets()
            except Exception:
                targets = []

        for target in targets:
            target_plugin_id = _text(getattr(target, "plugin_id", ""))
            target_version = _text(getattr(target, "framework_version", ""))
            if plugin_id and target_plugin_id != plugin_id:
                continue
            if target_version != framework_version:
                continue
            add_candidate(_text(getattr(target, "target_id", "")))

    # Last chance: let the plugin use its current default target. This helps
    # older project files that did not persist enough target metadata.
    add_candidate(None)
    return candidate_ids


def _load_palette_items_for_target(
    plugin_id: str,
    target_id: str | None,
    palette_cache: dict[tuple[str, str | None], list],
) -> list:
    """Load palette items with a small per-project cache."""

    cache_key = (plugin_id, target_id)
    if cache_key not in palette_cache:
        try:
            palette_cache[cache_key] = load_all_palette_items(
                plugin_id=plugin_id or None,
                target_id=target_id,
            )
        except Exception:
            palette_cache[cache_key] = []

    return palette_cache[cache_key]


def _palette_item_matches_saved_component(item, component_data: dict) -> bool:
    """Match a saved component using stable catalog fields rather than row ids."""

    saved_name = _text(component_data.get("name", ""))
    saved_element = _text(component_data.get("element", ""))
    saved_plugin_id = _text(component_data.get("pluginId", component_data.get("plugin_id", "")))
    saved_framework_version = _text(component_data.get("frameworkVersion", ""))
    saved_is_subcomp = _bool_int(component_data.get("isSubcomponent", 0))

    if saved_plugin_id and _text(getattr(item, "plugin_id", "")) != saved_plugin_id:
        return False
    if saved_name and _text(getattr(item, "type_name", "")) != saved_name:
        return False
    if saved_element and _text(getattr(item, "element_name", "")) != saved_element:
        return False
    if saved_framework_version and _text(getattr(item, "framework_version", "")) != saved_framework_version:
        return False
    if _palette_item_is_subcomponent(item) != saved_is_subcomp:
        return False

    return True



def _palette_lookup_key(
    plugin_id: str,
    element: str,
    name: str,
    framework_version: str,
    is_subcomponent: int,
) -> tuple[str, str, str, str, int]:
    """Return the stable component lookup key used during project restore."""

    return (
        _text(plugin_id),
        _text(element),
        _text(name),
        _text(framework_version),
        int(is_subcomponent or 0),
    )


def _palette_lookup_for_target(
    plugin_id: str,
    target_id: str | None,
    palette_cache: dict[tuple[str, str | None], list],
    lookup_cache: dict[tuple[str, str | None], dict[tuple[str, str, str, str, int], object]],
) -> dict[tuple[str, str, str, str, int], object]:
    """Return an indexed palette lookup for one plugin/target pair."""

    cache_key = (plugin_id, target_id)
    if cache_key in lookup_cache:
        return lookup_cache[cache_key]

    lookup: dict[tuple[str, str, str, str, int], object] = {}
    for item in _load_palette_items_for_target(plugin_id, target_id, palette_cache):
        key = _palette_lookup_key(
            getattr(item, "plugin_id", ""),
            getattr(item, "element_name", ""),
            getattr(item, "type_name", ""),
            getattr(item, "framework_version", ""),
            _palette_item_is_subcomponent(item),
        )
        lookup.setdefault(key, item)

    lookup_cache[cache_key] = lookup
    return lookup


def _component_definition_from_palette_item(item, component_data: dict) -> ComponentDefinition:
    """Build a fresh definition using local catalog ids and saved UI fallbacks."""

    return ComponentDefinition(
        plugin_id=getattr(item, "plugin_id", "") or component_data.get("pluginId", "core"),
        target_id=getattr(item, "target_id", "") or component_data.get("targetId", ""),
        target_label=getattr(item, "target_label", "") or component_data.get("targetLabel", ""),
        framework_version=getattr(item, "framework_version", "") or component_data.get("frameworkVersion", ""),
        component_id=getattr(item, "item_id", None) or component_data.get("componentId"),
        element=getattr(item, "element_name", "") or component_data.get("element", ""),
        name=getattr(item, "type_name", "") or component_data.get("name", ""),
        is_subcomp=_palette_item_is_subcomponent(item),
        category=getattr(item, "category", "") or component_data.get("category", ""),
        functionality=getattr(item, "functionality", "") or component_data.get("functionality", ""),
        description=getattr(item, "description", "") or component_data.get("description", ""),
        iface=getattr(item, "iface", "") or component_data.get("interface", ""),
        icon_path=getattr(item, "icon_path", "") or component_data.get("iconPath", ""),
        display_name_override=getattr(item, "display_name", "") or component_data.get("displayNameOverride", ""),
        is_composite=_bool_int(component_data.get("isComposite", 0)),
        composite_id=component_data.get("compositeId", ""),
    )


def _resolve_saved_component_definition(
    component_data: dict,
    palette_cache: dict[tuple[str, str | None], list],
    palette_lookup_cache: dict[tuple[str, str | None], dict[tuple[str, str, str, str, int], object]] | None = None,
    targets: list | None = None,
) -> ComponentDefinition:
    """Resolve a saved component against the local plugin catalog when possible.

    A ``.fse`` saved on another machine can contain target/component database row
    ids that do not exist locally. If those stale ids are used directly,
    ``ComponentNodeItem`` cannot find SST port metadata and the model opens with
    blank ports and unrestorable links. Resolve through stable fields first and
    fall back to the serialized data if no local catalog match exists.
    """

    fallback = _saved_component_definition(component_data)

    # Composite ids are FUSE-owned stable identifiers rather than simulator
    # catalog row ids, so they should be restored exactly as serialized.
    if _bool_int(component_data.get("isComposite", 0)):
        return fallback

    plugin_id = _text(component_data.get("pluginId", component_data.get("plugin_id", "")))
    if not plugin_id:
        return fallback

    palette_lookup_cache = palette_lookup_cache if palette_lookup_cache is not None else {}
    lookup_key = _palette_lookup_key(
        plugin_id,
        component_data.get("element", ""),
        component_data.get("name", ""),
        component_data.get("frameworkVersion", ""),
        _bool_int(component_data.get("isSubcomponent", 0)),
    )

    for target_id in _candidate_target_ids_for_saved_component(component_data, targets):
        lookup = _palette_lookup_for_target(
            plugin_id,
            target_id,
            palette_cache,
            palette_lookup_cache,
        )
        item = lookup.get(lookup_key)
        if item is not None:
            return _component_definition_from_palette_item(item, component_data)

        # Fallback scan preserves compatibility for older project files that may
        # have partial or non-normalized fields.
        for item in _load_palette_items_for_target(plugin_id, target_id, palette_cache):
            if _palette_item_matches_saved_component(item, component_data):
                return _component_definition_from_palette_item(item, component_data)

    return fallback


def component_node_to_save_dict(node: ComponentNodeItem) -> dict:
    """Convert a component graphics item into the project-file node schema."""
    position = node.pos()

    saved = {
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
        "isComposite": int(getattr(node.component, "is_composite", 0) or 0),
        "compositeId": getattr(node.component, "composite_id", "") or "",
        "instanceName": node.instance_name,
        "nameTemplate": getattr(node, "instance_name_template", ""),
        "parameters": node.parameters,
        "variablePortCounts": getattr(node, "variable_port_counts", {}),
        "position": {
            "x": position.x(),
            "y": position.y(),
        },
    }

    if int(getattr(node.component, "is_composite", 0) or 0):
        instance_model = getattr(node, "composite_instance_model", {}) or {}
        port_mappings = getattr(node, "composite_port_mappings", []) or []
        if isinstance(instance_model, dict) and bool(instance_model.get("components") or []):
            normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
                instance_model,
                port_mappings,
            )
            saved["compositeInstance"] = {
                "miniModel": normalized_model,
                "portMappings": [
                    mapping.to_dict()
                    for mapping in normalized_mappings
                ],
            }

    return saved


def model_link_to_save_dict(link: ModelLink) -> dict:
    """Convert a model link into the project-file link schema."""
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
    """Convert a subcomponent attachment into the project-file schema."""
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
    """Build a complete JSON-serializable project document from a scene."""
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
            "suppressedCompatibilityWarnings": sorted(
                getattr(scene, "suppressed_compatibility_warnings", set())
            ),
            **model_view.editor_state(),
        },
    }


def validate_project_dict(project: dict) -> None:
    """Validate a project dictionary before save or after load."""
    # Preserve the older, user-friendly error messages for the most common
    # project-file failures while delegating deeper structural checks to the
    # serializer validator.
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

    validate_serialized_project(project)


def load_project_file(file_path: str | Path) -> dict:
    """Load, parse, and validate a ``.fse`` project file."""
    file_path = Path(file_path)
    breadcrumb("project_io.load_project_file.start", path=str(file_path))
    with active_operation("project_io.load_project_file", path=str(file_path)):
        with file_path.open("r", encoding="utf-8") as file:
            project = json.load(file)

        validate_project_dict(project)
    breadcrumb(
        "project_io.load_project_file.end",
        path=str(file_path),
        components=len(project.get("components", []) or []),
        links=len(project.get("links", []) or []),
        subcomp_attachments=len(project.get("subcompAttachments", []) or []),
    )
    return project


def save_project_file(project: dict, file_path: str | Path) -> None:
    """Atomically save a validated project dictionary to disk."""
    destination = Path(file_path)
    validate_project_dict(project)
    project = finalize_project_dict(project)

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(destination.parent or Path(".")),
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temp_name = file.name
            json.dump(project, file, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(temp_name, destination)
    except Exception:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise


def load_project_into_scene(project: dict, scene: ModelScene) -> None:
    """Rebuild a model scene from an already-loaded project dictionary."""
    validate_project_dict(project)
    breadcrumb(
        "project_io.load_project_into_scene.start",
        components=len(project.get("components", []) or []),
        links=len(project.get("links", []) or []),
        subcomp_attachments=len(project.get("subcompAttachments", []) or []),
    )

    # Scene loading is a bulk operation. Build all items first, then schedule one
    # final route pass. This avoids repeated history snapshots, model-outline
    # refreshes, and route calculations while the file is still being restored.
    scene.begin_model_load()
    try:
        scene.clear_model()
        editor = project.get("editor", {}) or {}
        suppressed_warnings = editor.get("suppressedCompatibilityWarnings", [])
        if isinstance(suppressed_warnings, list):
            scene.suppressed_compatibility_warnings = {
                str(code).strip()
                for code in suppressed_warnings
                if str(code).strip()
            }
        else:
            scene.suppressed_compatibility_warnings = set()

        nodes_by_id: dict[int, ComponentNodeItem] = {}
        palette_cache: dict[tuple[str, str | None], list] = {}
        palette_lookup_cache: dict[tuple[str, str | None], dict[tuple[str, str, str, str, int], object]] = {}
        metadata_cache: dict[tuple[str, str, str, str], list[dict]] = {}
        try:
            target_cache = list_all_targets()
        except Exception:
            target_cache = []

        for component_data in project["components"]:
            component = _resolve_saved_component_definition(
                component_data,
                palette_cache,
                palette_lookup_cache,
                target_cache,
            )

            node_id = int(component_data["id"])
            node = ComponentNodeItem(
                component,
                node_id=node_id,
                parameters=component_data.get("parameters", {}),
                instance_name=component_data.get("instanceName"),
                variable_port_counts=component_data.get("variablePortCounts", {}),
                instance_name_template=component_data.get("nameTemplate", ""),
                metadata_cache=metadata_cache,
            )

            composite_instance = component_data.get("compositeInstance", {}) or {}
            if isinstance(composite_instance, dict):
                mini_model = composite_instance.get("miniModel", {}) or {}
                port_mappings = composite_instance.get("portMappings", []) or []
                if isinstance(mini_model, dict) and bool(mini_model.get("components") or []):
                    normalized_model, normalized_mappings = normalize_mini_model_and_port_mappings(
                        mini_model,
                        port_mappings if isinstance(port_mappings, list) else [],
                    )
                    node.composite_instance_model = normalized_model
                    node.composite_port_mappings = normalized_mappings
                    node.sync_composite_ports_from_mappings()

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
            source_port_name = _resolve_restored_link_port_name(
                nodes_by_id[source_node_id],
                source["port"],
            )
            target_port_name = _resolve_restored_link_port_name(
                nodes_by_id[target_node_id],
                target["port"],
            )

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
            connection = ConnectionItem(
                link,
                source_port,
                target_port,
                update_immediately=False,
            )
            scene.addItem(connection)

            # Show a cheap visible path immediately. The final obstacle-avoiding
            # route is scheduled once after the entire model is restored.
            connection.update_position_fast()

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
            item = SubcompAttachmentItem(
                attachment,
                slot_connector,
                interface_connector,
                update_immediately=False,
            )
            scene.addItem(item)
            item.update_position()

        for node in nodes_by_id.values():
            if hasattr(node, "apply_subcomp_connector_visibility"):
                node.apply_subcomp_connector_visibility()

        scene._next_subcomp_attachment_id = max_attachment_id + 1
    finally:
        scene.end_model_load(emit_model_changed=False)

    breadcrumb(
        "project_io.load_project_into_scene.restored",
        scene_snapshot=scene.diagnostic_snapshot() if hasattr(scene, "diagnostic_snapshot") else {},
    )

    reroute_timer = getattr(scene, "_reroute_timer", None)
    if reroute_timer is not None:
        reroute_timer.start(75)
    else:
        scene.reroute_all_links()
    breadcrumb(
        "project_io.load_project_into_scene.end",
        scene_snapshot=scene.diagnostic_snapshot() if hasattr(scene, "diagnostic_snapshot") else {},
    )
