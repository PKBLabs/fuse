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

from fuse.core.model.project_settings import PluginProjectSettings, ToolchainSettings
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.core.toolchains.providers import provider_from_toolchain
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


BUILTIN_GEM5_COMPONENTS = {
    "system": {
        "display_name": "gem5.System (Component)",
        "type_name": "System",
        "element_name": "gem5",
        "category": "System",
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
        metadata = BUILTIN_GEM5_COMPONENTS.get(str(item_id))

        if metadata is None:
            raise KeyError(f"gem5 item details are not implemented for item: {item_id}")

        target = None
        for candidate in self.list_targets():
            if target_id is None or candidate.target_id == str(target_id):
                target = candidate
                break

        framework_version = target.framework_version if target is not None else DEFAULT_GEM5_VERSION
        target_label = target.display_name if target is not None else f"gem5 {framework_version}"

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(item_id),
            display_name=metadata["display_name"],
            type_name=metadata["type_name"],
            element_name=metadata["element_name"],
            category=metadata["category"],
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

        cpu_nodes = [node for node in gem5_nodes if "CPU" in self._node_type(node)]
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

        xbar_nodes = [node for node in gem5_nodes if self._node_type(node) == "SystemXBar"]
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

        memory_nodes = [
            node for node in gem5_nodes
            if self._node_type(node) in {"DDR3_1600_8x8"}
        ]
        if not memory_nodes:
            issues.append(
                ValidationIssue(
                    issue_type="gem5_export",
                    object_name="Project",
                    message="gem5 export validation expects at least one memory controller/DRAM component.",
                )
            )

        for node in memory_nodes:
            if not link_map.get((getattr(node, "node_id", None), "port")):
                issues.append(
                    ValidationIssue(
                        issue_type="gem5_export",
                        object_name=getattr(node, "instance_name", "<unnamed>"),
                        node_id=getattr(node, "node_id", None),
                        parameter_name="port",
                        message="Memory component port must be connected for gem5 export.",
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
        # gem5 does not yet have a metadata importer equivalent to SST's sst-info.
        # Future work can query SimObjects/config schemas here.
        return


def gem5_command_from_toolchain(toolchain: ToolchainSettings) -> list[str]:
    binary = (
        toolchain.tool_paths.get("gem5Binary")
        or toolchain.tool_paths.get("remoteGem5Binary")
        or "gem5"
    )
    return [binary]


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
