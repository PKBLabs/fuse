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
    ItemDetails,
    PaletteItem,
    PropertyDefinition,
)
from fuse.core.persistence.database import get_connection, rows_to_dicts
from fuse.plugins.community.sst.initialize_db import initialize_sst_schema
from fuse.plugins.community.sst.get_sstinfo import sync_sstinfo_to_database


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

        force_refresh = os.environ.get("FUSE_REFRESH_SSTINFO", "0") == "1"

        with get_connection() as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS count
                FROM sst_info_runs
                WHERE return_code = 0
            """).fetchone()

        successful_runs = int(row["count"]) if row is not None else 0

        if successful_runs > 0 and not force_refresh:
            print("SST plugin: existing successful import found; skipping refresh.")
            print("SST plugin: set FUSE_REFRESH_SSTINFO=1 to force refresh.")
            return

        print("SST plugin: running sst-info import...")
        sync_sstinfo_to_database()

    def load_palette_items(self) -> list[PaletteItem]:
        with get_connection() as conn:
            rows = conn.execute("""
                SELECT
                    c.id AS component_id,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                ORDER BY e.name, c.is_subcomp, c.name
            """).fetchall()

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
                    category=row["category"] or "",
                    description=row["description"] or "",
                    icon_path=row["icon_path"] or "",
                    raw_kind=kind,
                )
            )

        return items

    def load_item_details(self, item_id: str) -> ItemDetails:
        component_id = int(item_id)

        with get_connection() as conn:
            component = conn.execute("""
                SELECT
                    c.id AS component_id,
                    e.name AS element_name,
                    c.name AS component_name,
                    c.description,
                    c.category,
                    c.iface,
                    c.is_subcomp,
                    c.icon_path
                FROM sst_components c
                JOIN sst_elements e ON c.parent_id = e.id
                WHERE c.id = ?
            """, (component_id,)).fetchone()

            ports = conn.execute("""
                SELECT name, description, iface
                FROM sst_ports
                WHERE parent_id = ?
                ORDER BY name
            """, (component_id,)).fetchall()

            params = conn.execute("""
                SELECT name, description, default_val, required
                FROM sst_parameters
                WHERE parent_id = ?
                  AND parent_type = 'sst_components'
                ORDER BY name
            """, (component_id,)).fetchall()

        component = dict(component)

        palette_item = PaletteItem(
            plugin_id=self.plugin_id,
            item_id=str(component["component_id"]),
            display_name=f'{component["element_name"]}.{component["component_name"]}',
            type_name=component["component_name"],
            category=component["category"] or "",
            description=component["description"] or "",
            icon_path=component["icon_path"] or "",
            raw_kind="SubComponent" if component["is_subcomp"] else "Component",
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
            for row in rows_to_dicts(params)
        ]

        return ItemDetails(
            palette_item=palette_item,
            connectors=connectors,
            properties=properties,
        )


def register_plugin():
    return SSTPlugin()