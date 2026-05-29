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
    iface: str = ""


@dataclass
class ConnectorDefinition:
    name: str
    description: str = ""
    interface: str = ""
    is_variable: bool = False
    base_name: str = ""
    count_parameter: str = ""
    default_count: int = 1


@dataclass
class SubcompConnectorDefinition:
    """
    Plugin-defined endpoint used to attach SubComponents to parent slots.

    These connectors are not normal link ports and must not export as
    Link.connect() endpoints.
    """

    name: str
    role: str  # slot or interface
    description: str = ""
    required_interface: str = ""
    provided_interface: str = ""
    interface: str = ""


@dataclass
class PropertyDefinition:
    name: str
    description: str = ""
    default_value: str = ""
    required: bool = False
    value_type: str = "string"


@dataclass
class LinkEndpoint:
    component_name: str
    port_name: str
    port_metadata: dict = field(default_factory=dict)


@dataclass
class LinkCompatibilityResult:
    can_create: bool = True
    severity: str = "ok"  # ok, warning, error
    title: str = ""
    message: str = ""
    code: str = ""
    visual_indicator: str = ""  # "", warning, error

    @property
    def is_ok(self) -> bool:
        return self.severity == "ok"

    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass
class ItemDetails:
    palette_item: PaletteItem
    connectors: list[ConnectorDefinition] = field(default_factory=list)
    subcomp_connectors: list[SubcompConnectorDefinition] = field(default_factory=list)
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

    def check_link_compatibility(
        self,
        source: LinkEndpoint,
        target: LinkEndpoint,
    ) -> LinkCompatibilityResult:
        ...

    def validate_links(self, scene) -> list:
        ...