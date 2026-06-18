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
"""Public plugin API contracts for the FUSE editor.

This module is the stable boundary between the FUSE core application and
framework-specific plugins such as SST and gem5. Plugins should return these
dataclasses from their entry points and should implement :class:`FusePlugin`
rather than importing Qt widgets, database helpers, or other internal core
modules.

The types here intentionally use plain Python data structures so that plugins
can describe simulator metadata, validation results, and export capabilities
without depending on the graphical editor implementation. Once FUSE reaches
v1.0, these contracts should be treated as compatibility-sensitive API.
"""

from dataclasses import dataclass, field
from typing import Protocol




@dataclass
class ExportFormat:
    """Plugin-owned export format advertised to the core UI.

    Core code can list or invoke these formats without knowing simulator-
    specific schemas such as SST JSON or gem5 Python.
    """

    format_id: str
    display_name: str
    file_filter: str
    default_suffix: str
    description: str = ""


@dataclass
class ExportResult:
    """Result returned by a plugin export operation.

    Attributes:
        output_path: Primary file or directory written by the exporter.
        format_id: Identifier of the :class:`ExportFormat` used.
        message: Human-readable success or diagnostic summary.
        report_path: Optional path to a generated validation/export report.
        warnings: Non-fatal issues encountered during export.
    """

    output_path: str
    format_id: str
    message: str = ""
    report_path: str = ""
    warnings: list = field(default_factory=list)

@dataclass
class FrameworkTarget:
    """Simulator/framework version target exposed by a plugin.

    A target distinguishes metadata sets that may have different component
    catalogs or compatibility rules, for example SST 15 versus SST 16 or
    gem5 24 versus gem5 25.
    """
    plugin_id: str
    target_id: str
    display_name: str
    framework_name: str = ""
    framework_version: str = ""
    is_default: bool = False


@dataclass
class PaletteItem:
    """Component or template entry shown in the component palette.

    Plugins provide palette items as lightweight summaries. The core palette UI
    uses them for display, filtering, drag/drop payloads, and later calls
    :meth:`FusePlugin.load_item_details` when connector/property metadata is
    needed.
    """
    plugin_id: str
    item_id: str
    display_name: str
    type_name: str
    element_name: str = ""
    category: str = ""
    functionality: str = ""
    description: str = ""
    icon_path: str = ""
    raw_kind: str = ""
    target_id: str = ""
    target_label: str = ""
    framework_version: str = ""
    iface: str = ""


@dataclass
class ConnectorDefinition:
    """Linkable port or connector definition for a component.

    Connector definitions describe normal graph links between component ports.
    Subcomponent attachment points use :class:`SubcompConnectorDefinition`
    instead and are exported differently by simulator plugins.
    """
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
    """Editable parameter/property exposed for a component instance."""
    name: str
    description: str = ""
    default_value: str = ""
    required: bool = False
    value_type: str = "string"


@dataclass
class LinkEndpoint:
    """Endpoint metadata used for plugin-owned link compatibility checks."""
    component_name: str
    port_name: str
    port_metadata: dict = field(default_factory=dict)


@dataclass
class LinkCompatibilityResult:
    """Plugin response describing whether a user may create a link.

    The scene uses this result to allow, warn about, or reject interactive link
    creation and to select the appropriate visual warning/error decoration.
    """
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
class CompatibilityIssue:
    """Validation or migration issue produced by a plugin.

    Issues are intentionally generic so the validation panel can present SST,
    gem5, and future framework diagnostics through the same UI.
    """
    severity: str
    object_name: str
    message: str
    node_id: int | None = None
    link_id: int | None = None
    parameter_name: str | None = None
    fix_kind: str = ""
    fix_data: dict = field(default_factory=dict)

    @property
    def is_warning(self) -> bool:
        return self.severity == "warning"

    @property
    def is_error(self) -> bool:
        return self.severity == "error"


@dataclass
class CompatibilityReport:
    """Collection of compatibility issues for a target or migration check."""
    plugin_id: str
    source_target_id: str = ""
    destination_target_id: str = ""
    issues: list[CompatibilityIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.is_error for issue in self.issues)

    @property
    def has_warnings(self) -> bool:
        return any(issue.is_warning for issue in self.issues)

    @property
    def can_apply(self) -> bool:
        return not self.has_errors


@dataclass
class MigrationPlan:
    """Plugin-generated plan for moving a model between framework targets."""
    plugin_id: str
    source_target_id: str = ""
    destination_target_id: str = ""
    report: CompatibilityReport | None = None
    node_updates: list[dict] = field(default_factory=list)

    @property
    def can_apply(self) -> bool:
        return self.report is None or self.report.can_apply


@dataclass
class ItemDetails:
    """Complete metadata for one palette item.

    The palette item itself is a summary; this object contains the connectors,
    subcomponent connectors, editable properties, and statistics needed by the
    editor once a component is selected or placed.
    """
    palette_item: PaletteItem
    connectors: list[ConnectorDefinition] = field(default_factory=list)
    subcomp_connectors: list[SubcompConnectorDefinition] = field(default_factory=list)
    properties: list[PropertyDefinition] = field(default_factory=list)
    statistics: list[dict] = field(default_factory=list)


class FusePlugin(Protocol):
    """Protocol implemented by all FUSE framework plugins.

    Core services discover plugins, call lifecycle hooks, request palette
    metadata, delegate validation/compatibility checks, and invoke exporters
    only through this protocol.
    """
    plugin_id: str
    name: str

    def initialize_database(self, conn) -> None:
        """Create or migrate plugin-owned database tables."""
        ...

    def bootstrap_database(self) -> None:
        """Populate plugin metadata caches when external tools are available."""
        ...

    def list_targets(self) -> list[FrameworkTarget]:
        """Return simulator/framework targets available to the current project."""
        ...

    def load_palette_items(self, target_id: str | None = None) -> list[PaletteItem]:
        """Return palette entries for ``target_id`` or the plugin default."""
        ...

    def load_item_details(
        self,
        item_id: str,
        target_id: str | None = None,
    ) -> ItemDetails:
        """Return full connector/property metadata for a palette item."""
        ...

    def export_formats(self) -> list[ExportFormat]:
        """Return export formats supported by this plugin."""
        ...

    def export_model(
        self,
        scene,
        output_path: str,
        format_id: str = "",
        *,
        plugin_settings=None,
    ) -> ExportResult:
        """Export the active scene into a simulator-specific artifact."""
        ...

    def validate_toolchain(self, plugin_settings) -> tuple[bool, str]:
        """Validate local or remote simulator toolchain settings."""
        ...

    def import_metadata_for_toolchain(self, plugin_settings) -> None:
        """Import simulator metadata for the configured toolchain."""
        ...

    def check_link_compatibility(
        self,
        source: LinkEndpoint,
        target: LinkEndpoint,
    ) -> LinkCompatibilityResult:
        """Return interactive compatibility status for a proposed link."""
        ...

    def validate_links(self, scene) -> list:
        """Return plugin-specific link validation issues for a scene."""
        ...
