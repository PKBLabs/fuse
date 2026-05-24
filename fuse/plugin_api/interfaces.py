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
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class FrameworkTarget:
    plugin_id: str
    target_id: str
    display_name: str
    framework_name: str = ""
    framework_version: str = ""
    is_default: bool = False


@dataclass
class PaletteItem:
    plugin_id: str
    item_id: str
    display_name: str
    type_name: str
    element_name: str = ""
    category: str = ""
    description: str = ""
    icon_path: str = ""
    raw_kind: str = ""
    target_id: str = ""
    target_label: str = ""
    framework_version: str = ""


@dataclass
class ConnectorDefinition:
    name: str
    description: str = ""
    interface: str = ""


@dataclass
class PropertyDefinition:
    name: str
    description: str = ""
    default_value: str = ""
    required: bool = False
    value_type: str = "string"


@dataclass
class ItemDetails:
    palette_item: PaletteItem
    connectors: list[ConnectorDefinition] = field(default_factory=list)
    properties: list[PropertyDefinition] = field(default_factory=list)
    statistics: list[dict] = field(default_factory=list)


class FusePlugin(Protocol):
    plugin_id: str
    name: str

    def initialize_database(self, conn) -> None:
        ...

    def bootstrap_database(self) -> None:
        ...

    def list_targets(self) -> list[FrameworkTarget]:
        ...

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        ...

    def load_item_details(
        self,
        item_id: str,
        target_id: str | None = None,
    ) -> ItemDetails:
        ...

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        ...

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        ...
