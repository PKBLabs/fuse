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
class PaletteItem:
    plugin_id: str
    item_id: str
    display_name: str
    type_name: str
    category: str = ""
    description: str = ""
    icon_path: str = ""
    raw_kind: str = ""


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

    def load_palette_items(self) -> list[PaletteItem]:
        ...

    def load_item_details(self, item_id: str) -> ItemDetails:
        ...