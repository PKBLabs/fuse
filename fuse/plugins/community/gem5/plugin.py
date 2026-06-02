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

import json
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from fuse.core.model.project_settings import PluginProjectSettings, ToolchainSettings
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.core.toolchains.providers import provider_from_toolchain
from fuse.core.toolchains.version_match import parse_version_text
from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    FrameworkTarget,
    ItemDetails,
    LinkCompatibilityResult,
    LinkEndpoint,
    PaletteItem,
    PropertyDefinition,
)


DEFAULT_GEM5_VERSION = "25.1.0.1"
PREVIOUS_GEM5_VERSION = "24.1.0.3"
DEFAULT_GEM5_ISA = "X86"
GEM5_METADATA_BEGIN = "FUSE_GEM5_METADATA_BEGIN"
GEM5_METADATA_END = "FUSE_GEM5_METADATA_END"


BUILTIN_GEM5_COMPONENTS = {
    "system": {
        "display_name": "gem5.System (Component)",
        "type_name": "System",
        "element_name": "gem5",
        "category": "System",
        "functionality": "System",
        "description": "Top-level gem5 system object.",
        "connectors": [
            {"name": "system_port", "description": "System functional access port", "interface": "request_port"},
        ],
        "properties": [
            {"name": "clock", "description": "System clock frequency", "default_value": "1GHz", "required": True},
            {"name": "mem_mode", "description": "gem5 memory mode", "default_value": "timing", "required": True},
            {"name": "cache_line_size", "description": "Cache line size in bytes", "default_value": "64", "required": True},
            {"name": "mem_ranges", "description": "System memory ranges", "default_value": "512MiB", "required": True},
        ],
    },
    "timing_simple_cpu": {
        "display_name": "gem5.TimingSimpleCPU (Component)",
        "type_name": "TimingSimpleCPU",
        "element_name": "gem5",
        "category": "CPU",
        "functionality": "Processor",
        "description": "TimingSimpleCPU SimObject for timing-mode gem5 models.",
        "connectors": [
            {"name": "icache_port", "description": "Instruction cache port", "interface": "request_port"},
            {"name": "dcache_port", "description": "Data cache port", "interface": "request_port"},
        ],
        "properties": [
            {"name": "numThreads", "description": "Number of hardware threads", "default_value": "1", "required": True},
            {"name": "clock", "description": "CPU clock frequency", "default_value": "2GHz", "required": True},
        ],
    },

    "atomic_simple_cpu": {
        "display_name": "gem5.AtomicSimpleCPU (Component)",
        "type_name": "AtomicSimpleCPU",
        "element_name": "gem5",
        "category": "CPU",
        "functionality": "Processor",
        "description": "AtomicSimpleCPU SimObject for fast functional gem5 models.",
        "connectors": [
            {"name": "icache_port", "description": "Instruction cache port", "interface": "request_port"},
            {"name": "dcache_port", "description": "Data cache port", "interface": "request_port"},
        ],
        "properties": [
            {"name": "numThreads", "description": "Number of hardware threads", "default_value": "1", "required": True},
            {"name": "clock", "description": "CPU clock frequency", "default_value": "2GHz", "required": True},
        ],
    },
    "minor_cpu": {
        "display_name": "gem5.MinorCPU (Component)",
        "type_name": "MinorCPU",
        "element_name": "gem5",
        "category": "CPU",
        "functionality": "Processor",
        "description": "MinorCPU SimObject for in-order pipeline studies.",
        "connectors": [
            {"name": "icache_port", "description": "Instruction cache port", "interface": "request_port"},
            {"name": "dcache_port", "description": "Data cache port", "interface": "request_port"},
        ],
        "properties": [
            {"name": "numThreads", "description": "Number of hardware threads", "default_value": "1", "required": True},
            {"name": "clock", "description": "CPU clock frequency", "default_value": "2GHz", "required": True},
        ],
    },
    "system_xbar": {
        "display_name": "gem5.SystemXBar (Component)",
        "type_name": "SystemXBar",
        "element_name": "gem5",
        "category": "Interconnect",
        "functionality": "Interconnect",
        "description": "gem5 system crossbar interconnect.",
        "connectors": [
            {"name": "cpu_side_ports", "description": "CPU-side ports", "interface": "response_port"},
            {"name": "mem_side_ports", "description": "Memory-side ports", "interface": "request_port"},
        ],
        "properties": [
            {"name": "width", "description": "Crossbar width in bytes", "default_value": "16", "required": True},
            {"name": "frontend_latency", "description": "Frontend latency in cycles", "default_value": "3", "required": True},
            {"name": "forward_latency", "description": "Forward latency in cycles", "default_value": "4", "required": True},
            {"name": "response_latency", "description": "Response latency in cycles", "default_value": "2", "required": True},
        ],
    },
    "ddr3_1600_8x8": {
        "display_name": "gem5.DDR3_1600_8x8 (Component)",
        "type_name": "DDR3_1600_8x8",
        "element_name": "gem5",
        "category": "Memory",
        "functionality": "Memory",
        "description": "Common gem5 DDR3 memory controller model.",
        "connectors": [
            {"name": "port", "description": "Memory controller port", "interface": "response_port"},
        ],
        "properties": [
            {"name": "range", "description": "Address range served by this controller", "default_value": "512MiB", "required": True},
            {"name": "addr_mapping", "description": "Address mapping policy", "default_value": "RoRaBaChCo", "required": False},
        ],
    },
}


class Gem5Plugin:
    plugin_id = "gem5"
    name = "gem5"

    def initialize_database(self, conn) -> None:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS gem5_framework_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                version TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'built-in',
                source_path TEXT NOT NULL DEFAULT '',
                gem5_root TEXT NOT NULL DEFAULT '',
                gem5_binary_path TEXT NOT NULL DEFAULT '',
                build_isa TEXT NOT NULL DEFAULT 'X86',
                is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,

                UNIQUE(version, source_kind, source_path, build_isa)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gem5_components (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                framework_version_id INTEGER NOT NULL,
                item_id TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                type_name TEXT NOT NULL,
                element_name TEXT NOT NULL DEFAULT 'gem5',
                category TEXT NOT NULL DEFAULT 'SimObject',
                functionality TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                raw_kind TEXT NOT NULL DEFAULT 'Component',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(framework_version_id) REFERENCES gem5_framework_versions(id) ON DELETE CASCADE,
                UNIQUE(framework_version_id, item_id)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gem5_component_connectors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                interface TEXT NOT NULL DEFAULT '',
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(component_id) REFERENCES gem5_components(id) ON DELETE CASCADE,
                UNIQUE(component_id, name)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS gem5_component_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                component_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                default_value TEXT NOT NULL DEFAULT '',
                required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
                sort_order INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(component_id) REFERENCES gem5_components(id) ON DELETE CASCADE,
                UNIQUE(component_id, name)
            )
        """)

        self._ensure_gem5_component_columns(conn)

        conn.execute("""
            INSERT OR IGNORE INTO gem5_framework_versions (
                version,
                label,
                source_kind,
                source_path,
                gem5_root,
                gem5_binary_path,
                build_isa,
                is_default
            )
            VALUES
                (?, ?, 'built-in', '', '', '', ?, 1),
                (?, ?, 'built-in', '', '', '', ?, 0)
        """, (
            DEFAULT_GEM5_VERSION,
            f"gem5 {DEFAULT_GEM5_VERSION}",
            DEFAULT_GEM5_ISA,
            PREVIOUS_GEM5_VERSION,
            f"gem5 {PREVIOUS_GEM5_VERSION}",
            DEFAULT_GEM5_ISA,
        ))

    def _ensure_gem5_component_columns(self, conn) -> None:
        """Add optional catalog columns for databases created by older FUSE builds."""
        try:
            rows = conn.execute("PRAGMA table_info(gem5_components)").fetchall()
        except sqlite3.OperationalError:
            return

        names = {row[1] for row in rows}
        if "functionality" not in names:
            conn.execute(
                "ALTER TABLE gem5_components ADD COLUMN functionality TEXT NOT NULL DEFAULT ''"
            )


    def bootstrap_database(self) -> None:
        return

    def list_targets(self) -> list[FrameworkTarget]:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, version, label, is_default
                FROM gem5_framework_versions
                ORDER BY is_default DESC, version DESC, id DESC
            """).fetchall()

        targets: list[FrameworkTarget] = []

        for row in rows_to_dicts(rows):
            targets.append(
                FrameworkTarget(
                    plugin_id=self.plugin_id,
                    target_id=str(row["id"]),
                    display_name=row["label"] or f"gem5 {row['version']}",
                    framework_name="gem5",
                    framework_version=row["version"],
                    is_default=bool(row["is_default"]),
                )
            )

        return targets

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        targets = self.list_targets()

        if target_id is None and targets:
            target_id = next((target.target_id for target in targets if target.is_default), targets[0].target_id)

        target_by_id = {target.target_id: target for target in targets}
        target = target_by_id.get(str(target_id)) if target_id is not None else None
        framework_version = target.framework_version if target is not None else DEFAULT_GEM5_VERSION
        target_label = target.display_name if target is not None else f"gem5 {framework_version}"

        imported = self._load_imported_palette_items(str(target_id or ""), framework_version, target_label)
        if imported:
            return imported

        items: list[PaletteItem] = []

        for item_id, metadata in BUILTIN_GEM5_COMPONENTS.items():
            items.append(
                PaletteItem(
                    plugin_id=self.plugin_id,
                    item_id=item_id,
                    display_name=metadata["display_name"],
                    type_name=metadata["type_name"],
                    element_name=metadata["element_name"],
                    category=metadata["category"],
                    functionality=metadata.get("functionality", gem5_functionality_for_type(metadata["type_name"])),
                    description=metadata["description"],
                    raw_kind="Component",
                    target_id=str(target_id or ""),
                    target_label=target_label,
                    framework_version=framework_version,
                )
            )

        return items

    def load_item_details(
        self,
        item_id: str,
        target_id: str | None = None,
    ) -> ItemDetails:
        target = None
        for candidate in self.list_targets():
            if target_id is None or candidate.target_id == str(target_id):
                target = candidate
                break

        framework_version = target.framework_version if target is not None else DEFAULT_GEM5_VERSION
        target_label = target.display_name if target is not None else f"gem5 {framework_version}"

        imported = self._load_imported_item_details(str(item_id), str(target_id or ""), framework_version, target_label)
        if imported is not None:
            return imported

        metadata = BUILTIN_GEM5_COMPONENTS.get(str(item_id))

        if metadata is None:
            raise KeyError(f"gem5 item details are not implemented for item: {item_id}")

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(item_id),
            display_name=metadata["display_name"],
            type_name=metadata["type_name"],
            element_name=metadata["element_name"],
            category=metadata["category"],
            functionality=metadata.get("functionality", gem5_functionality_for_type(metadata["type_name"])),
            description=metadata["description"],
            raw_kind="Component",
            target_id=str(target_id or ""),
            target_label=target_label,
            framework_version=framework_version,
        )

        return ItemDetails(
            palette_item=palette_item,
            connectors=[
                ConnectorDefinition(
                    name=connector["name"],
                    description=connector.get("description", ""),
                    interface=connector.get("interface", ""),
                )
                for connector in metadata["connectors"]
            ],
            properties=[
                PropertyDefinition(
                    name=property_definition["name"],
                    description=property_definition.get("description", ""),
                    default_value=property_definition.get("default_value", ""),
                    required=bool(property_definition.get("required", False)),
                )
                for property_definition in metadata["properties"]
            ],
        )

    def _load_imported_palette_items(
        self,
        target_id: str,
        framework_version: str,
        target_label: str,
    ) -> list[PaletteItem]:
        if not target_id:
            return []

        try:
            with get_connection() as conn:
                rows = conn.execute(
                    """
                    SELECT item_id, display_name, type_name, element_name, category, functionality, description, raw_kind
                    FROM gem5_components
                    WHERE framework_version_id = ?
                    ORDER BY category COLLATE NOCASE, display_name COLLATE NOCASE, type_name COLLATE NOCASE
                    """,
                    (target_id,),
                ).fetchall()
        except sqlite3.OperationalError:
            return []

        return [
            PaletteItem(
                plugin_id=self.plugin_id,
                item_id=row["item_id"],
                display_name=row["display_name"] or f"gem5.{row['type_name']} (Component)",
                type_name=row["type_name"],
                element_name=row["element_name"] or "gem5",
                category=row["category"] or "SimObject",
                functionality=row.get("functionality") or gem5_functionality_for_type(row["type_name"]),
                description=row["description"] or "Imported gem5 SimObject.",
                raw_kind=row["raw_kind"] or "Component",
                target_id=target_id,
                target_label=target_label,
                framework_version=framework_version,
            )
            for row in rows_to_dicts(rows)
        ]

    def _load_imported_item_details(
        self,
        item_id: str,
        target_id: str,
        framework_version: str,
        target_label: str,
    ) -> ItemDetails | None:
        if not target_id:
            return None

        try:
            conn = get_connection()
            component_row = conn.execute(
                """
                SELECT id, item_id, display_name, type_name, element_name, category, functionality, description, raw_kind
                FROM gem5_components
                WHERE framework_version_id = ? AND item_id = ?
                """,
                (target_id, item_id),
            ).fetchone()

            if component_row is None:
                return None

            connector_rows = conn.execute(
                """
                SELECT name, description, interface
                FROM gem5_component_connectors
                WHERE component_id = ?
                ORDER BY sort_order, name COLLATE NOCASE
                """,
                (component_row["id"],),
            ).fetchall()
            property_rows = conn.execute(
                """
                SELECT name, description, default_value, required
                FROM gem5_component_properties
                WHERE component_id = ?
                ORDER BY sort_order, name COLLATE NOCASE
                """,
                (component_row["id"],),
            ).fetchall()
        except sqlite3.OperationalError:
            return None
        finally:
            try:
                conn.close()
            except Exception:
                pass

        row = dict(component_row)
        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=row["item_id"],
            display_name=row["display_name"] or f"gem5.{row['type_name']} (Component)",
            type_name=row["type_name"],
            element_name=row["element_name"] or "gem5",
            category=row["category"] or "SimObject",
            functionality=row.get("functionality") or gem5_functionality_for_type(row["type_name"]),
            description=row["description"] or "Imported gem5 SimObject.",
            raw_kind=row["raw_kind"] or "Component",
            target_id=target_id,
            target_label=target_label,
            framework_version=framework_version,
        )

        return ItemDetails(
            palette_item=palette_item,
            connectors=[
                ConnectorDefinition(
                    name=row["name"],
                    description=row["description"] or "",
                    interface=row["interface"] or "",
                )
                for row in rows_to_dicts(connector_rows)
            ],
            properties=[
                PropertyDefinition(
                    name=row["name"],
                    description=row["description"] or "",
                    default_value=row["default_value"] or "",
                    required=bool(row["required"]),
                )
                for row in rows_to_dicts(property_rows)
            ],
        )



    def compatible_gem5_interfaces(self, source_iface: str, target_iface: str) -> bool:
        pair = {source_iface, target_iface}
        if not source_iface or not target_iface:
            return True
        if pair == {"request_port", "response_port"}:
            return True
        if source_iface == target_iface == "bus":
            return True
        if source_iface == target_iface == "memory_range":
            return True
        return False

    def check_link_compatibility(
        self,
        source: LinkEndpoint,
        target: LinkEndpoint,
    ) -> LinkCompatibilityResult:
        source_iface = (source.port_metadata.get("iface") or source.port_metadata.get("interface") or "").strip()
        target_iface = (target.port_metadata.get("iface") or target.port_metadata.get("interface") or "").strip()

        if self.compatible_gem5_interfaces(source_iface, target_iface):
            return LinkCompatibilityResult()

        return LinkCompatibilityResult(
            can_create=False,
            severity="error",
            title="Incompatible gem5 Ports",
            message=(
                f"gem5 port '{source.port_name}' ({source_iface or 'unknown'}) cannot be "
                f"linked to '{target.port_name}' ({target_iface or 'unknown'})."
            ),
            code="gem5_incompatible_port_interface",
            visual_indicator="error",
        )

    def validate_links(self, scene) -> list:
        from fuse.core.model.validation import ValidationIssue

        issues = []
        nodes_by_id = {node.node_id: node for node in scene.component_items()}

        for link in getattr(scene, "links", []):
            source = nodes_by_id.get(link.source_node_id)
            target = nodes_by_id.get(link.target_node_id)

            if source is None or target is None:
                continue

            if getattr(source.component, "plugin_id", "") != self.plugin_id or getattr(target.component, "plugin_id", "") != self.plugin_id:
                continue

            source_port = next((port for port in getattr(source, "ports", []) if port.name == link.source_port), None)
            target_port = next((port for port in getattr(target, "ports", []) if port.name == link.target_port), None)

            if source_port is None or target_port is None:
                issues.append(
                    ValidationIssue(
                        issue_type="gem5_link",
                        object_name=link.name,
                        link_id=link.link_id,
                        message="gem5 link references a port that no longer exists.",
                    )
                )
                continue

            result = self.check_link_compatibility(
                LinkEndpoint(source.instance_name, source_port.name, getattr(source_port, "metadata", {}) or {}),
                LinkEndpoint(target.instance_name, target_port.name, getattr(target_port, "metadata", {}) or {}),
            )

            if result.is_error:
                issues.append(
                    ValidationIssue(
                        issue_type="gem5_link",
                        object_name=link.name,
                        link_id=link.link_id,
                        message=result.message,
                    )
                )

        return issues

    def _gem5_nodes(self, scene) -> list:
        return [
            node
            for node in scene.component_items()
            if getattr(node.component, "plugin_id", "") == self.plugin_id
        ]

    def _node_type(self, node) -> str:
        return getattr(node.component, "name", "")

    def _node_category(self, node) -> str:
        return getattr(node.component, "category", "") or _category_for_gem5_type(self._node_type(node))

    def _node_functionality(self, node) -> str:
        return getattr(node.component, "functionality", "") or gem5_functionality_for_type(self._node_type(node), self._node_category(node))

    def _node_role(self, node) -> str:
        return gem5_component_role(self._node_type(node), self._node_category(node), self._node_functionality(node))

    def _has_port(self, node, port_name: str) -> bool:
        return any(getattr(port, "name", "") == port_name for port in getattr(node, "ports", []) or [])

    def _ports_with_interface(self, node, interface: str) -> list[str]:
        result = []
        for port in getattr(node, "ports", []) or []:
            metadata = getattr(port, "metadata", {}) or {}
            iface = (metadata.get("iface") or metadata.get("interface") or "").strip()
            if iface == interface:
                result.append(getattr(port, "name", ""))
        return [name for name in result if name]

    def _link_map(self, scene, gem5_nodes: list) -> dict[tuple[int, str], list]:
        node_ids = {getattr(node, "node_id", None) for node in gem5_nodes}
        node_ids.discard(None)
        result: dict[tuple[int, str], list] = {}
        for link in getattr(scene, "links", []):
            if link.source_node_id in node_ids and link.target_node_id in node_ids:
                result.setdefault((link.source_node_id, link.source_port), []).append(link)
                result.setdefault((link.target_node_id, link.target_port), []).append(link)
        return result

    def _target_ids(self, gem5_nodes: list) -> set[str]:
        return {
            str(getattr(node.component, "target_id", "") or "")
            for node in gem5_nodes
            if str(getattr(node.component, "target_id", "") or "")
        }

    def validate_export(self, scene) -> list:
        from fuse.core.model.validation import ValidationIssue

        issues = []
        gem5_nodes = self._gem5_nodes(scene)

        if not gem5_nodes:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="There are no gem5 components to export.",
                )
            )
            return issues

        target_ids = self._target_ids(gem5_nodes)
        if len(target_ids) > 1:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message=(
                        "gem5 export requires all gem5 components to use the same "
                        f"target/version; found {', '.join(sorted(target_ids))}."
                    ),
                )
            )

        system_nodes = [node for node in gem5_nodes if self._node_type(node) == "System"]
        if len(system_nodes) != 1:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export validation expects exactly one System component in the model.",
                )
            )

        link_map = self._link_map(scene, gem5_nodes)

        cpu_nodes = [node for node in gem5_nodes if self._node_role(node) == "cpu"]
        if not cpu_nodes:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export validation expects at least one CPU component.",
                )
            )

        for node in cpu_nodes:
            for port_name in ("icache_port", "dcache_port"):
                if not link_map.get((getattr(node, "node_id", None), port_name)):
                    issues.append(
                        ValidationIssue(
                            issue_type="gem5_export",
                            object_name=getattr(node, "instance_name", "<unnamed>"),
                            node_id=getattr(node, "node_id", None),
                            parameter_name=port_name,
                            message=f"CPU port '{port_name}' must be connected for gem5 export.",
                        )
                    )

        xbar_nodes = [node for node in gem5_nodes if self._node_role(node) == "interconnect"]
        if not xbar_nodes:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export validation expects a SystemXBar interconnect component.",
                )
            )

        for node in xbar_nodes:
            for port_name in ("cpu_side_ports", "mem_side_ports"):
                if not link_map.get((getattr(node, "node_id", None), port_name)):
                    issues.append(
                        ValidationIssue(
                            issue_type="gem5_export",
                            object_name=getattr(node, "instance_name", "<unnamed>"),
                            node_id=getattr(node, "node_id", None),
                            parameter_name=port_name,
                            message=f"SystemXBar port '{port_name}' must be connected for gem5 export.",
                        )
                    )

        memory_nodes = [node for node in gem5_nodes if self._node_role(node) == "memory"]
        if not memory_nodes:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export validation expects at least one memory controller/DRAM component.",
                )
            )

        for node in memory_nodes:
            candidate_ports = ["port"] if self._has_port(node, "port") else self._ports_with_interface(node, "response_port")
            if candidate_ports and any(link_map.get((getattr(node, "node_id", None), port_name)) for port_name in candidate_ports):
                continue
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name=getattr(node, "instance_name", "<unnamed>"),
                    node_id=getattr(node, "node_id", None),
                    parameter_name=",".join(candidate_ports) or "port",
                    message="Memory component response port must be connected for gem5 export.",
                )
            )

        if getattr(scene, "subcomp_attachments", []):
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export does not currently support FUSE SubComponent attachments.",
                )
            )

        return issues

    def validate_toolchain(
        self,
        plugin_settings: PluginProjectSettings,
    ) -> tuple[bool, str]:
        ok, message, _ = validate_gem5_toolchain(
            toolchain=plugin_settings.toolchain,
            expected_version=plugin_settings.framework_version,
            timeout_seconds=60,
        )
        return ok, message

    def import_metadata_for_toolchain(self, plugin_settings: PluginProjectSettings) -> None:
        metadata = query_gem5_metadata(plugin_settings.toolchain)
        version = (
            plugin_settings.framework_version
            or metadata.get("version", "")
            or DEFAULT_GEM5_VERSION
        )
        build_isa = (
            plugin_settings.toolchain.options.get("buildIsa")
            or plugin_settings.toolchain.options.get("build_isa")
            or metadata.get("build_isa", "")
            or DEFAULT_GEM5_ISA
        )
        binary_path = (
            plugin_settings.toolchain.tool_paths.get("gem5Binary")
            or plugin_settings.toolchain.tool_paths.get("remoteGem5Binary")
            or "gem5"
        )
        gem5_root = plugin_settings.toolchain.tool_paths.get("gem5Root", "")
        label = plugin_settings.target_label or f"gem5 {version} ({build_isa}, live)"

        with get_connection() as conn:
            conn.execute("UPDATE gem5_framework_versions SET is_default = 0 WHERE source_kind = 'live'")
            conn.execute(
                """
                INSERT INTO gem5_framework_versions (
                    version, label, source_kind, source_path, gem5_root,
                    gem5_binary_path, build_isa, is_default
                )
                VALUES (?, ?, 'live', ?, ?, ?, ?, 1)
                ON CONFLICT(version, source_kind, source_path, build_isa)
                DO UPDATE SET
                    label = excluded.label,
                    gem5_root = excluded.gem5_root,
                    gem5_binary_path = excluded.gem5_binary_path,
                    is_default = 1
                """,
                (version, label, binary_path, gem5_root, binary_path, build_isa),
            )
            target_id = conn.execute(
                """
                SELECT id FROM gem5_framework_versions
                WHERE version = ? AND source_kind = 'live' AND source_path = ? AND build_isa = ?
                """,
                (version, binary_path, build_isa),
            ).fetchone()["id"]
            self._replace_imported_components(conn, target_id, metadata.get("components", []))
            conn.commit()

    def _replace_imported_components(self, conn, target_id: int, components: list[dict[str, Any]]) -> None:
        conn.execute("DELETE FROM gem5_components WHERE framework_version_id = ?", (target_id,))

        for component in components:
            type_name = str(component.get("type_name", "") or "").strip()
            if not type_name:
                continue

            item_id = str(component.get("item_id", "") or gem5_item_id_for_type(type_name))
            conn.execute(
                """
                INSERT INTO gem5_components (
                    framework_version_id, item_id, display_name, type_name,
                    element_name, category, functionality, description, raw_kind
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    target_id,
                    item_id,
                    component.get("display_name", "") or f"gem5.{type_name} (Component)",
                    type_name,
                    component.get("element_name", "gem5") or "gem5",
                    component.get("category", "SimObject") or "SimObject",
                    component.get("functionality", "") or gem5_functionality_for_type(type_name),
                    component.get("description", "") or "Imported gem5 SimObject.",
                    component.get("raw_kind", "Component") or "Component",
                ),
            )
            component_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            for index, connector in enumerate(component.get("connectors", []) or []):
                name = str(connector.get("name", "") or "").strip()
                if not name:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO gem5_component_connectors (
                        component_id, name, description, interface, sort_order
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        component_id,
                        name,
                        connector.get("description", "") or "",
                        connector.get("interface", "") or "",
                        index,
                    ),
                )

            for index, property_definition in enumerate(component.get("properties", []) or []):
                name = str(property_definition.get("name", "") or "").strip()
                if not name:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO gem5_component_properties (
                        component_id, name, description, default_value, required, sort_order
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        component_id,
                        name,
                        property_definition.get("description", "") or "",
                        property_definition.get("default_value", "") or "",
                        1 if property_definition.get("required", False) else 0,
                        index,
                    ),
                )


def gem5_command_from_toolchain(toolchain: ToolchainSettings) -> list[str]:
    binary = (
        toolchain.tool_paths.get("gem5Binary")
        or toolchain.tool_paths.get("remoteGem5Binary")
        or "gem5"
    )
    return [binary]


def gem5_item_id_for_type(type_name: str) -> str:
    value = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", type_name)
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return value.replace("_x_bar", "_xbar").lower()


def _category_for_gem5_type(type_name: str) -> str:
    if type_name in {"System", "Root"}:
        return "System"
    if "CPU" in type_name:
        return "CPU"
    if any(token in type_name for token in ("XBar", "Bus", "Bridge", "Switch")):
        return "Interconnect"
    if any(token in type_name for token in ("DRAM", "DDR", "HBM", "Memory", "Mem", "NVM")):
        return "Memory"
    if any(token in type_name for token in ("Cache", "TLB", "MMU")):
        return "Cache"
    if any(token in type_name for token in ("Device", "Disk", "Ether", "Pci", "PCI", "VirtIO")):
        return "Device"
    return "SimObject"



def gem5_functionality_for_type(type_name: str, category: str = "") -> str:
    text = str(type_name or "")
    category_text = str(category or _category_for_gem5_type(text) or "")
    lowered = text.lower()
    if category_text == "System" or text in {"System", "Root"}:
        return "System"
    if category_text == "CPU" or "cpu" in lowered:
        return "Processor"
    if category_text == "Interconnect" or any(token in text for token in ("XBar", "Bus", "Bridge", "Switch")):
        return "Interconnect"
    if category_text == "Memory" or any(token in text for token in ("DRAM", "DDR", "HBM", "Memory", "Mem", "NVM")):
        return "Memory"
    if category_text == "Cache" or any(token in text for token in ("Cache", "TLB", "MMU")):
        return "Memory Hierarchy"
    if category_text == "Device":
        return "Device"
    return category_text or "SimObject"


def gem5_component_role(type_name: str, category: str = "", functionality: str = "") -> str:
    type_text = str(type_name or "")
    cat = str(category or _category_for_gem5_type(type_text) or "").lower()
    func = str(functionality or gem5_functionality_for_type(type_text, category) or "").lower()
    lowered = type_text.lower()
    if type_text == "System" or func == "system":
        return "system"
    if "cpu" in lowered or func == "processor" or cat == "cpu":
        return "cpu"
    if any(token in type_text for token in ("XBar", "Bus", "Bridge", "Switch")) or func == "interconnect" or cat == "interconnect":
        return "interconnect"
    if any(token in type_text for token in ("DRAM", "DDR", "HBM", "Memory", "Mem", "NVM")) or func == "memory" or cat == "memory":
        return "memory"
    if "cache" in lowered or cat == "cache":
        return "cache"
    return "simobject"


def _infer_gem5_port_interface(port_text: str) -> str:
    lowered = port_text.lower()
    if "request" in lowered or "master" in lowered:
        return "request_port"
    if "response" in lowered or "slave" in lowered:
        return "response_port"
    return "gem5_port"


GEM5_METADATA_PROBE_SCRIPT = 'import json\n\nBEGIN = "FUSE_GEM5_METADATA_BEGIN"\nEND = "FUSE_GEM5_METADATA_END"\n\ntry:\n    import m5.objects as objects\nexcept Exception as error:\n    print(BEGIN)\n    print(json.dumps({"error": f"Could not import m5.objects: {type(error).__name__}: {error}"}))\n    print(END)\n    raise\n\n\ndef item_id_for_type(type_name):\n    import re\n    value = re.sub(r"(.)([A-Z][a-z]+)", r"\\1_\\2", type_name)\n    value = re.sub(r"([a-z0-9])([A-Z])", r"\\1_\\2", value)\n    return value.replace("_x_bar", "_xbar").lower()\n\n\ndef category_for_type(type_name):\n    if type_name in {"System", "Root"}:\n        return "System"\n    if "CPU" in type_name:\n        return "CPU"\n    if any(token in type_name for token in ("XBar", "Bus", "Bridge", "Switch")):\n        return "Interconnect"\n    if any(token in type_name for token in ("DRAM", "DDR", "HBM", "Memory", "Mem", "NVM")):\n        return "Memory"\n    if any(token in type_name for token in ("Cache", "TLB", "MMU")):\n        return "Cache"\n    if any(token in type_name for token in ("Device", "Disk", "Ether", "Pci", "PCI", "VirtIO")):\n        return "Device"\n    return "SimObject"\n\n\ndef port_interface(port):\n    text = f"{type(port).__name__} {port!r}".lower()\n    if "request" in text or "master" in text:\n        return "request_port"\n    if "response" in text or "slave" in text:\n        return "response_port"\n    return "gem5_port"\n\n\ndef safe_text(value):\n    try:\n        if value is None:\n            return ""\n        return str(value)\n    except Exception:\n        return ""\n\n\ncomponents = []\nfor name in sorted(dir(objects)):\n    if name.startswith("_"):\n        continue\n    try:\n        cls = getattr(objects, name)\n    except Exception:\n        continue\n    if not isinstance(cls, type):\n        continue\n    if not hasattr(cls, "_params") and not hasattr(cls, "_ports"):\n        continue\n\n    connectors = []\n    for port_name, port in sorted((getattr(cls, "_ports", {}) or {}).items()):\n        connectors.append({\n            "name": str(port_name),\n            "description": safe_text(getattr(port, "desc", "")),\n            "interface": port_interface(port),\n        })\n\n    properties = []\n    for param_name, param in sorted((getattr(cls, "_params", {}) or {}).items()):\n        if param_name in getattr(cls, "_ports", {}):\n            continue\n        default = getattr(param, "default", None)\n        has_default = default is not None\n        properties.append({\n            "name": str(param_name),\n            "description": safe_text(getattr(param, "desc", "")),\n            "default_value": safe_text(default) if has_default else "",\n            "required": not has_default,\n        })\n\n    if not connectors and not properties and name not in {"Root", "System"}:\n        continue\n\n    components.append({\n        "item_id": item_id_for_type(name),\n        "display_name": f"gem5.{name} (Component)",\n        "type_name": name,\n        "element_name": "gem5",\n        "category": category_for_type(name),\n        "description": f"Imported gem5 SimObject {name} from m5.objects.",\n        "raw_kind": "Component",\n        "connectors": connectors,\n        "properties": properties,\n    })\n\nprint(BEGIN)\nprint(json.dumps({"components": components}, sort_keys=True))\nprint(END)\n'


def _extract_probe_payload(output: str) -> dict[str, Any]:
    begin = output.find(GEM5_METADATA_BEGIN)
    end = output.find(GEM5_METADATA_END)
    if begin == -1 or end == -1 or end <= begin:
        raise RuntimeError(
            "gem5 metadata probe did not emit the expected metadata markers.\n\n"
            f"Output:\n{output}"
        )
    payload_text = output[begin + len(GEM5_METADATA_BEGIN):end].strip()
    payload = json.loads(payload_text)
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    return payload


def query_gem5_metadata(toolchain: ToolchainSettings, timeout_seconds: int = 120) -> dict[str, Any]:
    if (toolchain.backend or "local") != "local":
        raise RuntimeError(
            "gem5 live metadata import currently supports local toolchains only. "
            "Use a local gem5 binary or continue using the built-in gem5 catalog."
        )

    provider = provider_from_toolchain(toolchain)
    version_command = [*gem5_command_from_toolchain(toolchain), "--version"]
    version_result = provider.run(
        version_command,
        timeout_seconds=timeout_seconds,
        env=toolchain.environment,
    )
    version_output = (version_result.stdout + version_result.stderr).strip()
    if version_result.return_code != 0:
        raise RuntimeError(
            "Could not query gem5 version before metadata import.\n\n"
            f"Command: {' '.join(version_command)}\n"
            f"Return code: {version_result.return_code}\n\n{version_output}"
        )

    parsed_version = parse_version_text(version_output)
    version = parsed_version.text if parsed_version is not None else ""

    script_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix="_fuse_gem5_probe.py", delete=False) as handle:
            handle.write(GEM5_METADATA_PROBE_SCRIPT)
            script_path = Path(handle.name)

        command = [*gem5_command_from_toolchain(toolchain), str(script_path)]
        result = provider.run(
            command,
            timeout_seconds=timeout_seconds,
            env=toolchain.environment,
        )
        output = (result.stdout + result.stderr).strip()
        if result.return_code != 0:
            raise RuntimeError(
                "gem5 metadata probe failed.\n\n"
                f"Command: {' '.join(command)}\n"
                f"Return code: {result.return_code}\n\n{output}"
            )

        payload = _extract_probe_payload(output)
        payload["version"] = version
        return payload
    finally:
        if script_path is not None:
            try:
                script_path.unlink(missing_ok=True)
            except Exception:
                pass


def validate_gem5_toolchain(
    toolchain: ToolchainSettings,
    expected_version: str = "",
    timeout_seconds: int = 60,
) -> tuple[bool, str, str]:
    """Validate that the configured local/SSH gem5 binary is reachable.

    Returns:
        (ok, user_message, detected_output)
    """
    provider = provider_from_toolchain(toolchain)
    command = [*gem5_command_from_toolchain(toolchain), "--version"]
    result = provider.run(command, timeout_seconds=timeout_seconds)
    output = (result.stdout + result.stderr).strip()

    if result.return_code != 0:
        return (
            False,
            (
                "gem5 validation failed.\n\n"
                f"Backend: {result.backend}\n"
                f"Host: {result.host or 'local'}\n"
                f"Command: {' '.join(command)}\n"
                f"Return code: {result.return_code}\n\n"
                f"STDERR/STDOUT:\n{output}"
            ),
            output,
        )

    if "gem5" not in output.lower():
        return (
            False,
            (
                "The configured command ran successfully, but its version output "
                "does not look like gem5.\n\n"
                f"Command: {' '.join(command)}\n\nOutput:\n{output}"
            ),
            output,
        )

    if expected_version and expected_version not in output:
        return (
            False,
            (
                f"The project target is gem5 {expected_version}, but the configured "
                "gem5 binary reported a different version.\n\n"
                f"Command: {' '.join(command)}\n\nOutput:\n{output}"
            ),
            output,
        )

    version_text = f"gem5 {expected_version}" if expected_version else "gem5"
    return (
        True,
        (
            f"Validated {version_text} toolchain.\n\n"
            f"Backend: {result.backend}\n"
            f"Host: {result.host or 'local'}\n"
            f"Command: {' '.join(command)}\n\n"
            f"Output:\n{output}"
        ),
        output,
    )


def register_plugin():
    return Gem5Plugin()
