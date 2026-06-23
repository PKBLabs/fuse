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
"""Community SST framework plugin.

The SST plugin translates metadata imported from ``sst-info`` into FUSE palette
items, item details, compatibility checks, toolchain validation, and SST JSON
export support. Core code talks to this plugin through the public
``fuse.plugin_api`` contracts.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    ExportFormat,
    ExportResult,
    FrameworkTarget,
    ItemDetails,
    LinkCompatibilityResult,
    LinkEndpoint,
    PaletteItem,
    PropertyDefinition,
    SubcompConnectorDefinition,
)
from fuse.core.model.subcomponents import is_visual_subcomponent_connection_parameter
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.plugins.community.sst.initialize_db import (
    get_or_create_sst_framework_version,
    initialize_sst_schema,
)
from fuse.plugins.community.sst.policy.loader import (
    available_policy_catalog_versions,
    has_policy_catalog,
)
from fuse.plugins.community.sst.policy.bootstrap import ensure_sst_policy_catalogs

@dataclass
class SSTPlugin:
    """FUSE plugin implementation for Structural Simulation Toolkit models."""

    plugin_id: str = "sst"
    name: str = "FUSE SST Plugin"

    def initialize_database(self, conn) -> None:
        """Create or migrate SST-specific metadata tables."""
        initialize_sst_schema(conn)

    def register_bundled_policy_targets(self) -> None:
        """Register bundled SST policy catalogs as selectable FUSE targets.

        This makes Project Settings show supported SST versions even before the
        user has configured local or remote SST tools.
        """

        versions = available_policy_catalog_versions()

        if not versions:
            print("SST plugin: no bundled SST policy catalogs were found.")
            return

        default_version = versions[-1]

        with get_connection() as conn:
            existing_default = conn.execute(
                """
                SELECT id
                FROM sst_framework_versions
                WHERE is_default = 1
                LIMIT 1
                """
            ).fetchone()

            for version in versions:
                get_or_create_sst_framework_version(
                    conn=conn,
                    version=version,
                    label=f"SST {version}",
                    source_kind="sst-info",
                    source_path="",
                    command="bundled FUSE SST policy catalog",
                    is_default=(
                        existing_default is None
                        and version == default_version
                    ),
                )

    def bootstrap_database(self) -> None:
        """Bootstrap SST plugin metadata that ships with FUSE.

        This intentionally does not run sst-info. Users configure and validate
        local/remote SST tools from Project Settings.
        """

        self.register_bundled_policy_targets()

    def list_targets(self) -> list[FrameworkTarget]:
        """Return SST versions available in the local metadata database."""
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, version, label, is_default
                FROM sst_framework_versions
                ORDER BY is_default DESC, version DESC, id DESC
            """).fetchall()

        targets = []
        supported_versions = set(available_policy_catalog_versions())

        for row in rows_to_dicts(rows):
            version = str(row["version"] or "")

            if version not in supported_versions:
                continue

            targets.append(
                FrameworkTarget(
                    plugin_id=self.plugin_id,
                    target_id=str(row["id"]),
                    display_name=row["label"] or f"SST {version}",
                    framework_name="SST",
                    framework_version=version,
                    is_default=bool(row["is_default"]),
                )
            )

        return targets

    def _default_target_id(self) -> str | None:
        targets = self.list_targets()

        if not targets:
            return None

        for target in targets:
            if target.is_default:
                return target.target_id

        return targets[0].target_id

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        """Return SST components/subcomponents for the selected target."""
        if target_id is None:
            target_id = self._default_target_id()

        if target_id is None:
            return []

        framework_version_id = int(target_id)

        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    c.id AS component_id,
                    c.framework_version_id,
                    fv.version AS framework_version,
                    fv.label AS target_label,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.functionality,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
                WHERE c.framework_version_id = ?
                  AND e.framework_version_id = ?
                ORDER BY e.name, c.is_subcomp, c.name
            """, (framework_version_id, framework_version_id)).fetchall()

        items = []

        for row in rows_to_dicts(rows):
            kind = "SubComponent" if row["is_subcomp"] else "Component"
            display_name = f'{row["element_name"]}.{row["component_name"]} ({kind})'

            items.append(
                PaletteItem(
                    plugin_id=self.plugin_id,
                    item_id=str(row["component_id"]),
                    display_name=display_name,
                    type_name=row["component_name"],
                    element_name=row["element_name"] or "",
                    category=row["category"] or "",
                    functionality=row["functionality"] or "",
                    description=row["description"] or "",
                    icon_path=row["icon_path"] or "",
                    raw_kind=kind,
                    target_id=str(row["framework_version_id"]),
                    target_label=row["target_label"] or f"SST {row['framework_version']}",
                    framework_version=row["framework_version"] or "",
                    iface=row["iface"] or "",
                )
            )

        return items

    def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails:
        """Load connectors, parameters, and statistics for one SST item."""
        component_id = int(item_id)
        params = [component_id]
        target_filter = ""

        if target_id:
            target_filter = " AND c.framework_version_id = ?"
            params.append(int(target_id))

        with get_connection() as conn:
            component = conn.execute(f"""
                SELECT
                    c.id AS component_id,
                    c.framework_version_id,
                    fv.version AS framework_version,
                    fv.label AS target_label,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.functionality,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                JOIN sst_framework_versions fv ON c.framework_version_id = fv.id
                WHERE c.id = ?
                {target_filter}
            """, params).fetchone()

            if component is None:
                raise KeyError(f"SST component {item_id!r} was not found for target {target_id!r}.")

            component_dict = dict(component)
            framework_version_id = int(component_dict["framework_version_id"])

            ports = conn.execute("""
                SELECT
                    name,
                    description,
                    iface,
                    is_variable,
                    base_name,
                    count_parameter,
                    default_count
                FROM sst_ports
                WHERE framework_version_id = ?
                  AND parent_id = ?
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

            params_rows = conn.execute("""
                SELECT name, description, default_val, required
                FROM sst_parameters
                WHERE framework_version_id = ?
                  AND parent_id = ?
                  AND parent_type = 'sst_components'
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

            slots = conn.execute("""
                SELECT name, description, iface
                FROM sst_subcomp_slots
                WHERE framework_version_id = ?
                  AND parent_id = ?
                ORDER BY name
            """, (framework_version_id, component_id)).fetchall()

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(component_dict["component_id"]),
            display_name=f'{component_dict["element_name"]}.{component_dict["component_name"]}',
            type_name=component_dict["component_name"],
            element_name=component_dict["element_name"] or "",
            category=component_dict["category"] or "",
            functionality=component_dict["functionality"] or "",
            description=component_dict["description"] or "",
            icon_path=component_dict["icon_path"] or "",
            raw_kind="SubComponent" if component_dict["is_subcomp"] else "Component",
            target_id=str(component_dict["framework_version_id"]),
            target_label=component_dict["target_label"] or f"SST {component_dict['framework_version']}",
            framework_version=component_dict["framework_version"] or "",
            iface=component_dict["iface"] or "",
        )

        connectors = [
            ConnectorDefinition(
                name=row["name"],
                description=row["description"] or "",
                interface=row["iface"] or "",
                is_variable=bool(row.get("is_variable", 0)),
                base_name=row.get("base_name", "") or row["name"],
                count_parameter=row.get("count_parameter", "") or "",
                default_count=int(row.get("default_count", 1) or 1),
            )
            for row in rows_to_dicts(ports)
        ]

        subcomp_connectors = [
            SubcompConnectorDefinition(
                name=row["name"],
                role="slot",
                description=row["description"] or "",
                required_interface=row["iface"] or "",
                interface=row["iface"] or "",
            )
            for row in rows_to_dicts(slots)
        ]

        if bool(component_dict["is_subcomp"]):
            subcomp_connectors.append(
                SubcompConnectorDefinition(
                    name="interface",
                    role="interface",
                    description=(
                        "SubComponent interface connector"
                        if component_dict.get("iface")
                        else "SubComponent interface connector (interface unspecified)"
                    ),
                    provided_interface=component_dict["iface"] or "",
                    interface=component_dict["iface"] or "",
                )
            )

        properties = []
        component_is_subcomponent = bool(component_dict["is_subcomp"])
        for row in rows_to_dicts(params_rows):
            property_definition = {
                "name": row["name"],
                "description": row["description"] or "",
                "default_val": row["default_val"] or "",
                "required": bool(row["required"]),
            }
            required = bool(row["required"])
            if is_visual_subcomponent_connection_parameter(
                property_definition,
                component_is_subcomponent=component_is_subcomponent,
            ):
                required = False

            properties.append(
                PropertyDefinition(
                    name=row["name"],
                    description=row["description"] or "",
                    default_value=row["default_val"] or "",
                    required=required,
                )
            )

        return ItemDetails(
            palette_item=palette_item,
            connectors=connectors,
            subcomp_connectors=subcomp_connectors,
            properties=properties,
        )

    def check_link_compatibility(
            self,
            source: LinkEndpoint,
            target: LinkEndpoint,
    ) -> LinkCompatibilityResult:
        """
        Return compatibility for ordinary SST Link.connect() port links.

        SST Link.connect() connects named ports. Many normal component ports do not
        expose enough interface metadata in sst-info to prove semantic compatibility.
        Interface checking belongs to SubComponent Slot assignment, where SST
        provides explicit interface metadata.
        """
        return LinkCompatibilityResult()

    def check_subcomponent_slot_compatibility(
            self,
            slot_metadata: dict,
            subcomponent_metadata: dict,
    ) -> LinkCompatibilityResult:
        """
        Check SST SubComponent Slot assignment compatibility.

        This is where SST interface matching belongs. Ordinary SST Link.connect()
        port links should not use this rule.
        """
        slot_iface = (
                slot_metadata.get("required_interface", "")
                or slot_metadata.get("iface", "")
                or slot_metadata.get("interface", "")
                or ""
        ).strip()

        subcomponent_iface = (
                subcomponent_metadata.get("provided_interface", "")
                or subcomponent_metadata.get("iface", "")
                or subcomponent_metadata.get("interface", "")
                or ""
        ).strip()

        if not slot_iface or not subcomponent_iface:
            return LinkCompatibilityResult(
                can_create=True,
                severity="warning",
                title="Unknown SubComponent Interface",
                code="sst.subcomponent_slot_unknown_interface",
                visual_indicator="warning",
                message=(
                    "The interface type for at least one of these endpoints is unknown. "
                    "Compatibility cannot be determined!\n\n"
                    f"Slot interface: {slot_iface or '(unknown)'}\n"
                    f"SubComponent interface: {subcomponent_iface or '(unknown)'}\n\n"
                    "FUSE can create this SubComponent assignment, but the exported SST "
                    "model may not run correctly if the slot and SubComponent are not "
                    "actually compatible."
                ),
            )

        if slot_iface == subcomponent_iface:
            return LinkCompatibilityResult()

        return LinkCompatibilityResult(
            can_create=True,
            severity="warning",
            title="SST SubComponent Interface Mismatch",
            code="sst.subcomponent_slot_interface_mismatch",
            visual_indicator="warning",
            message=(
                "The selected SST SubComponent does not declare the exact "
                "interface required by this slot. SST interface names are not "
                "always standardized, so this may still be the correct "
                "assignment.\n\n"
                f"Slot requires: {slot_iface}\n"
                f"SubComponent provides: {subcomponent_iface}"
            ),
        )

    def export_formats(self) -> list[ExportFormat]:
        """Return SST export formats advertised to the core UI."""
        return [
            ExportFormat(
                format_id="sst.json",
                display_name="SST JSON",
                file_filter="SST JSON (*.json);;All Files (*)",
                default_suffix=".sst.json",
                description="Runnable SST JSON configuration generated from an SST-only FUSE model.",
            )
        ]

    def export_model(
        self,
        scene,
        output_path: str,
        format_id: str = "sst.json",
        *,
        plugin_settings=None,
    ) -> ExportResult:
        if format_id not in ("", "sst.json"):
            raise ValueError(f"Unsupported SST export format: {format_id}")

        from fuse.core.model.composite_flattening import flatten_scene_for_export
        from fuse.plugins.community.sst.export_json import export_sst_json, validate_sst_json_export

        output = Path(output_path)
        export_scene = flatten_scene_for_export(scene)
        report = validate_sst_json_export(export_scene)
        report_path = ""
        if report.warnings:
            report_path = str(output.with_suffix(".export-report.json"))

        export_sst_json(
            scene=export_scene,
            output_path=output,
            report_path=report_path or None,
        )

        warning_count = len(report.warnings)
        if warning_count:
            message = f"Exported SST JSON with {warning_count} warning(s)."
        else:
            message = "Exported SST JSON."

        return ExportResult(
            output_path=str(output),
            format_id="sst.json",
            message=message,
            report_path=report_path,
            warnings=list(report.warnings),
        )

    def validate_export(self, scene) -> list:
        from fuse.core.model.composite_flattening import flatten_scene_for_export
        from fuse.plugins.community.sst.export_json import validate_sst_json_export

        return validate_sst_json_export(flatten_scene_for_export(scene)).issues

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        """Validate the configured local or remote SST toolchain."""
        expected_version = getattr(plugin_settings, "framework_version", "") or ""
        ok, message, _ = validate_sst_toolchain(
            toolchain=plugin_settings.toolchain,
            expected_version=expected_version,
        )
        return ok, message

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        """Import ``sst-info`` metadata using configured toolchain settings."""
        version = getattr(plugin_settings, "framework_version", "") or os.environ.get("FUSE_SST_VERSION", "15.0.0")
        label = getattr(plugin_settings, "target_label", "") or f"SST {version}"

        sync_sstinfo_to_database(
            version=version,
            label=label,
            is_default=True,
            toolchain=plugin_settings.toolchain,
        )


def register_plugin():
    """Return the plugin instance consumed by the FUSE plugin runtime."""
    return SSTPlugin()
