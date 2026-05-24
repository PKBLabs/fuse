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
from dataclasses import dataclass
import os
import shutil

from fuse.plugin_api.interfaces import (
    ConnectorDefinition,
    FrameworkTarget,
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.plugins.community.sst.initialize_db import initialize_sst_schema
from fuse.plugins.community.sst.get_sstinfo import (
    sync_sstinfo_to_database,
    validate_sst_toolchain,
)


@dataclass
class SSTPlugin:
    plugin_id: str = "sst"
    name: str = "FUSE SST Plugin"

    def initialize_database(self, conn) -> None:
        initialize_sst_schema(conn)

    def bootstrap_database(self) -> None:
        if shutil.which("sst-info") is None:
            print("SST plugin: sst-info not found; skipping SST import.")
            return

        requested_version = os.environ.get("FUSE_SST_VERSION", "15.0.0")
        force_refresh = os.environ.get("FUSE_REFRESH_SSTINFO", "0") == "1"

        with get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS count
                FROM sst_info_runs r
                JOIN sst_framework_versions fv ON r.framework_version_id = fv.id
                WHERE r.return_code = 0
                  AND fv.version = ?
            """, (requested_version,)).fetchone()

        successful_runs = int(row["count"]) if row is not None else 0

        if successful_runs > 0 and not force_refresh:
            print(f"SST plugin: existing successful SST {requested_version} import found; skipping refresh.")
            print("SST plugin: set FUSE_REFRESH_SSTINFO=1 to force refresh.")
            return

        print(f"SST plugin: running sst-info import for SST {requested_version}...")
        sync_sstinfo_to_database(
            version=requested_version,
            label=f"SST {requested_version}",
            is_default=True,
        )

    def list_targets(self) -> list[FrameworkTarget]:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT id, version, label, is_default
                FROM sst_framework_versions
                ORDER BY is_default DESC, version DESC, id DESC
            """).fetchall()

        targets = []

        for row in rows_to_dicts(rows):
            targets.append(
                FrameworkTarget(
                    plugin_id=self.plugin_id,
                    target_id=str(row["id"]),
                    display_name=row["label"] or f"SST {row['version']}",
                    framework_name="SST",
                    framework_version=row["version"],
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
                    description=row["description"] or "",
                    icon_path=row["icon_path"] or "",
                    raw_kind=kind,
                    target_id=str(row["framework_version_id"]),
                    target_label=row["target_label"] or f"SST {row['framework_version']}",
                    framework_version=row["framework_version"] or "",
                )
            )

        return items

    def load_item_details(self, item_id: str, target_id: str | None = None) -> ItemDetails:
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
                SELECT name, description, iface
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

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(component_dict["component_id"]),
            display_name=f'{component_dict["element_name"]}.{component_dict["component_name"]}',
            type_name=component_dict["component_name"],
            element_name=component_dict["element_name"] or "",
            category=component_dict["category"] or "",
            description=component_dict["description"] or "",
            icon_path=component_dict["icon_path"] or "",
            raw_kind="SubComponent" if component_dict["is_subcomp"] else "Component",
            target_id=str(component_dict["framework_version_id"]),
            target_label=component_dict["target_label"] or f"SST {component_dict['framework_version']}",
            framework_version=component_dict["framework_version"] or "",
        )

        connectors = [
            ConnectorDefinition(
                name=row["name"],
                description=row["description"] or "",
                interface=row["iface"] or "",
            )
            for row in rows_to_dicts(ports)
        ]

        properties = [
            PropertyDefinition(
                name=row["name"],
                description=row["description"] or "",
                default_value=row["default_val"] or "",
                required=bool(row["required"]),
            )
            for row in rows_to_dicts(params_rows)
        ]

        return ItemDetails(
            palette_item=palette_item,
            connectors=connectors,
            properties=properties,
        )

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        expected_version = getattr(plugin_settings, "framework_version", "") or ""
        ok, message, _ = validate_sst_toolchain(
            toolchain=plugin_settings.toolchain,
            expected_version=expected_version,
        )
        return ok, message

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        version = getattr(plugin_settings, "framework_version", "") or os.environ.get("FUSE_SST_VERSION", "15.0.0")
        label = getattr(plugin_settings, "target_label", "") or f"SST {version}"

        sync_sstinfo_to_database(
            version=version,
            label=label,
            is_default=True,
            toolchain=plugin_settings.toolchain,
        )


def register_plugin():
    return SSTPlugin()
