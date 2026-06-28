# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""SST component metadata catalog seeding and custom discovery support.

There are two kinds of SST JSON catalogs in FUSE:

* ``policy/catalogs/sst-*.json`` drives SST JSON export behavior.
* ``component_catalogs/sst-*.json`` seeds the database rows used by the
  component palette, properties panel, ports, subcomponent slots, and statistics.

This module handles the second kind. The UI remains database-driven; JSON files
are only install-time seed data and toolchain-discovery snapshots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from fuse.core.model.project_settings import ToolchainSettings
from fuse.core.persistence.database import get_connection
from fuse.plugins.community.sst.get_sstinfo import (
    ParsedComponent,
    ParsedElement,
    get_sstinfo_for_toolchain,
    parse_sstinfo_output,
    parsed_sstinfo_from_catalog_dict,
    parsed_sstinfo_to_catalog_dict,
    sync_sstinfo_catalog_json_to_database,
    validate_sst_toolchain,
)
from fuse.plugins.community.sst.initialize_db import (
    get_or_create_sst_framework_version,
    initialize_database,
)
from fuse.plugins.community.sst.policy.loader import (
    available_policy_catalog_versions,
    normalize_sst_version,
)


_COMPONENT_CATALOG_DIR = Path(__file__).resolve().parent / "component_catalogs"

# Custom/toolchain-discovered SST catalog snapshots are plugin-owned runtime
# metadata.  Keep them inside the SST plugin tree instead of under the core
# application database directory so plugin-specific data never lands in
# ``fuse/app_data``.
_CUSTOM_CATALOG_DIR = _COMPONENT_CATALOG_DIR / "toolchains"


@dataclass(frozen=True)
class DiscoveredComponentEntry:
    """One component/subcomponent row shown in the custom component manager."""

    key: str
    element_name: str
    name: str
    display_name: str
    kind: str
    status: str
    description: str = ""
    parameter_count: int = 0
    port_count: int = 0
    subcomponent_slot_count: int = 0
    statistic_count: int = 0
    enabled_by_default: bool = False
    previously_enabled: bool = False


@dataclass(frozen=True)
class ComponentMetadataDiff:
    """Human-readable metadata differences for one discovered SST component."""

    key: str
    display_name: str
    status: str
    lines: tuple[str, ...] = ()

    def summary(self) -> str:
        """Return a compact one-line summary for table display."""

        if self.status == "baseline":
            return "Matches baseline"
        if self.status == "custom":
            return "New component"
        if self.status == "missing":
            return "Missing from runtime"
        if not self.lines:
            return "Changed"

        details = [
            line
            for line in self.lines
            if line.startswith(("+ ", "- ", "~ "))
        ]

        if not details:
            return "Changed"

        return "; ".join(line[2:] for line in details[:3])


@dataclass
class SSTComponentDiscovery:
    """Result of scanning one configured local/remote SST installation."""

    version: str
    source_label: str
    source_fingerprint: str
    discovered_catalog: dict[str, Any]
    baseline_catalog: dict[str, Any]
    entries: list[DiscoveredComponentEntry]
    previous_enabled_keys: set[str]
    command_text: str = ""


@dataclass
class SSTRuntimeVerificationReport:
    """Result of checking a project against the currently configured SST runtime."""

    ok: bool
    version: str = ""
    target_id: str = ""
    target_label: str = ""
    command_text: str = ""
    used_component_keys: set[str] = field(default_factory=set)
    runtime_component_keys: set[str] = field(default_factory=set)
    enabled_custom_component_keys: set[str] = field(default_factory=set)
    missing_used_component_keys: set[str] = field(default_factory=set)
    missing_enabled_component_keys: set[str] = field(default_factory=set)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    infos: list[str] = field(default_factory=list)

    def message(self) -> str:
        lines: list[str] = []

        if self.ok:
            lines.append("SST runtime verified.")
        else:
            lines.append("SST runtime verification failed.")

        if self.target_label:
            lines.append(f"Target: {self.target_label}")
        if self.version:
            lines.append(f"Expected SST version: {self.version}")
        if self.command_text:
            lines.append(f"Command: {self.command_text}")

        lines.append(f"Components used by model: {len(self.used_component_keys)}")
        lines.append(f"Components exposed by runtime: {len(self.runtime_component_keys)}")

        if self.enabled_custom_component_keys:
            available_enabled = (
                len(self.enabled_custom_component_keys)
                - len(self.missing_enabled_component_keys)
                - len(self.missing_used_component_keys.intersection(self.enabled_custom_component_keys))
            )
            lines.append(
                "Enabled custom/changed components available: "
                f"{max(0, available_enabled)}/{len(self.enabled_custom_component_keys)}"
            )

        if self.errors:
            lines.append("")
            lines.append("Errors:")
            lines.extend(f"- {item}" for item in self.errors)

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {item}" for item in self.warnings)

        if self.infos:
            lines.append("")
            lines.append("Info:")
            lines.extend(f"- {item}" for item in self.infos)

        return "\n".join(lines)


@dataclass
class SSTExportPolicyDiagnostics:
    """Grouped export diagnostics for custom/changed SST component metadata."""

    target_id: str = ""
    target_label: str = ""
    used_component_keys: set[str] = field(default_factory=set)
    custom_component_keys: set[str] = field(default_factory=set)
    changed_component_keys: set[str] = field(default_factory=set)

    @property
    def has_diagnostics(self) -> bool:
        return bool(self.custom_component_keys or self.changed_component_keys)

    def custom_warning_message(self) -> str:
        names = ", ".join(
            component_key_display_name(key)
            for key in sorted(self.custom_component_keys)
        )
        return (
            "This model uses custom SST components that are not part of the "
            "bundled baseline SST component catalog. FUSE will use generic SST "
            "export rules and discovered sst-info metadata for these components: "
            f"{names}."
        )

    def changed_warning_message(self) -> str:
        names = ", ".join(
            component_key_display_name(key)
            for key in sorted(self.changed_component_keys)
        )
        return (
            "This model uses SST components whose discovered metadata differs "
            "from the bundled baseline SST component catalog. FUSE will use "
            "discovered parameter/port metadata for editing and bundled export "
            "policy rules where they are still applicable: "
            f"{names}."
        )

    def warning_messages(self) -> list[str]:
        messages: list[str] = []

        if self.custom_component_keys:
            messages.append(self.custom_warning_message())

        if self.changed_component_keys:
            messages.append(self.changed_warning_message())

        return messages


@dataclass
class SSTCatalogSourceSummary:
    """User-facing lifecycle summary for one SST component catalog target."""

    target_id: str = ""
    target_label: str = ""
    version: str = ""
    source_kind: str = ""
    source_path: str = ""
    command_text: str = ""
    catalog_path: str = ""
    source_label: str = ""
    source_fingerprint: str = ""
    discovered_at: str = ""
    component_count: int = 0
    baseline_component_count: int = 0
    enabled_custom_count: int = 0
    enabled_changed_count: int = 0
    disabled_discovered_count: int = 0
    current_toolchain_fingerprint: str = ""
    fingerprint_stale: bool = False

    @property
    def is_custom(self) -> bool:
        return self.source_kind == "toolchain-component-catalog" or bool(
            self.source_fingerprint
        )

    @property
    def is_baseline(self) -> bool:
        return not self.is_custom

    @property
    def has_target(self) -> bool:
        return bool(self.target_id)

    def short_label(self) -> str:
        if not self.has_target:
            return "No SST catalog target is selected."

        if self.is_custom:
            return self.target_label or f"SST {self.version} custom catalog"

        return self.target_label or f"SST {self.version} bundled baseline"

    def message(self) -> str:
        if not self.has_target:
            return "No SST catalog target is selected."

        lines: list[str] = [f"Active target: {self.short_label()}"]

        if self.version:
            lines.append(f"SST version: {self.version}")

        if self.is_custom:
            lines.append(f"Source: {self.source_label or 'Discovered SST toolchain'}")
            if self.discovered_at:
                lines.append(f"Last discovered: {self.discovered_at}")
            if self.catalog_path:
                lines.append(f"Snapshot: {self.catalog_path}")

            counts: list[str] = []
            if self.baseline_component_count:
                counts.append(f"{self.baseline_component_count} baseline")
            if self.enabled_custom_count:
                counts.append(f"{self.enabled_custom_count} custom")
            if self.enabled_changed_count:
                counts.append(f"{self.enabled_changed_count} changed")
            if self.disabled_discovered_count:
                counts.append(f"{self.disabled_discovered_count} disabled discovered")

            lines.append("Components: " + (", ".join(counts) if counts else f"{self.component_count} total"))

            if self.fingerprint_stale:
                lines.append("")
                lines.append(
                    "The configured SST toolchain path/SSH settings differ from the "
                    "toolchain used to create this custom catalog. Refresh the catalog "
                    "before relying on it for export or run validation."
                )
        else:
            lines.append("Source: Bundled FUSE baseline component catalog")
            lines.append(f"Components: {self.component_count} baseline")

        return "\n".join(lines)


def _version_sort_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in normalize_sst_version(version).split("."))
    except ValueError:
        return (0,)


def component_catalog_path_for_version(version: str) -> Path:
    return _COMPONENT_CATALOG_DIR / f"sst-{normalize_sst_version(version)}.json"


def available_component_catalog_versions() -> list[str]:
    if not _COMPONENT_CATALOG_DIR.exists():
        return []

    versions: list[str] = []

    for path in _COMPONENT_CATALOG_DIR.glob("sst-*.json"):
        version = normalize_sst_version(path.stem.removeprefix("sst-"))

        if version:
            versions.append(version)

    return sorted(versions, key=_version_sort_key)


def has_component_catalog(version: str | None) -> bool:
    version = normalize_sst_version(version)

    if not version:
        return False

    return component_catalog_path_for_version(version).exists()


def load_component_catalog(version: str) -> dict[str, Any]:
    version = normalize_sst_version(version)
    path = component_catalog_path_for_version(version)

    if not path.exists():
        raise FileNotFoundError(
            f"No bundled SST component catalog is available for SST {version}: {path}"
        )

    return json.loads(path.read_text(encoding="utf-8"))


def _component_key_from_parts(element_name: str, name: str, is_subcomp: int | bool) -> str:
    kind = "subcomponent" if int(is_subcomp or 0) else "component"
    return f"{element_name}.{name}|{kind}"


def component_key(component: dict[str, Any] | ParsedComponent) -> str:
    if isinstance(component, ParsedComponent):
        return _component_key_from_parts(
            component.element_name,
            component.name,
            component.is_subcomp,
        )

    return _component_key_from_parts(
        str(component.get("element_name", "") or ""),
        str(component.get("name", "") or ""),
        int(component.get("is_subcomp", 0) or 0),
    )


def _component_display_name(component: dict[str, Any]) -> str:
    return f"{component.get('element_name', '')}.{component.get('name', '')}"


def _component_signature(component: dict[str, Any]) -> str:
    """Return a stable signature for metadata relevant to FUSE editing."""

    def sorted_records(name: str) -> list[dict[str, Any]]:
        records = component.get(name, []) or []
        return sorted(records, key=lambda item: json.dumps(item, sort_keys=True))

    payload = {
        "description": component.get("description", "") or "",
        "iface": component.get("iface", "") or "",
        "category": component.get("category", "") or "",
        "functionality": component.get("functionality", "") or "",
        "checkpointable": int(component.get("checkpointable", 0) or 0),
        "parameters": sorted_records("parameters"),
        "ports": sorted_records("ports"),
        "subcomp_slots": sorted_records("subcomp_slots"),
        "statistics": sorted_records("statistics"),
    }

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _record_name(record: dict[str, Any]) -> str:
    return str(record.get("name", "") or "")


def _record_signature(record: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _records_by_name(records: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}

    for index, record in enumerate(records or []):
        name = _record_name(record) or f"<unnamed #{index + 1}>"
        result[name] = record

    return result


def _record_collection_diff_lines(
    *,
    label: str,
    baseline_records: list[dict[str, Any]] | None,
    discovered_records: list[dict[str, Any]] | None,
) -> list[str]:
    baseline_by_name = _records_by_name(baseline_records)
    discovered_by_name = _records_by_name(discovered_records)

    added = sorted(set(discovered_by_name) - set(baseline_by_name))
    removed = sorted(set(baseline_by_name) - set(discovered_by_name))
    changed = sorted(
        name
        for name in set(baseline_by_name).intersection(discovered_by_name)
        if _record_signature(baseline_by_name[name]) != _record_signature(discovered_by_name[name])
    )

    lines: list[str] = []

    if added:
        lines.append(f"+ Added {label}: {', '.join(added)}")
    if removed:
        lines.append(f"- Removed {label}: {', '.join(removed)}")
    if changed:
        lines.append(f"~ Changed {label}: {', '.join(changed)}")

    return lines


def _scalar_metadata_diff_lines(
    baseline_component: dict[str, Any],
    discovered_component: dict[str, Any],
) -> list[str]:
    fields = [
        ("description", "description"),
        ("iface", "interface"),
        ("category", "category"),
        ("functionality", "functionality"),
        ("checkpointable", "checkpointable"),
    ]

    lines: list[str] = []

    for field_name, display_name in fields:
        baseline_value = baseline_component.get(field_name, "") or ""
        discovered_value = discovered_component.get(field_name, "") or ""

        if field_name == "checkpointable":
            baseline_value = int(baseline_value or 0)
            discovered_value = int(discovered_value or 0)

        if baseline_value != discovered_value:
            lines.append(
                f"~ Changed {display_name}: {baseline_value!r} → {discovered_value!r}"
            )

    return lines


def describe_component_metadata_diff(
    *,
    key: str,
    baseline_catalog: dict[str, Any],
    discovered_catalog: dict[str, Any],
) -> ComponentMetadataDiff:
    """Return user-facing metadata differences for one discovered SST component.

    The custom component manager uses this to explain why a row is classified as
    custom, changed, missing, or baseline without requiring users to inspect JSON.
    """

    baseline_by_key = _catalog_component_map(baseline_catalog)
    discovered_by_key = _catalog_component_map(discovered_catalog)

    baseline_component = baseline_by_key.get(key)
    discovered_component = discovered_by_key.get(key)
    component = discovered_component or baseline_component or {}
    display_name = _component_display_name(component) if component else key

    if discovered_component is None and baseline_component is None:
        return ComponentMetadataDiff(
            key=key,
            display_name=display_name,
            status="unknown",
            lines=("Component metadata is not available in either catalog.",),
        )

    if baseline_component is None and discovered_component is not None:
        return ComponentMetadataDiff(
            key=key,
            display_name=display_name,
            status="custom",
            lines=(
                "This component was discovered from the configured SST installation, "
                "but it is not part of the bundled baseline catalog.",
                f"Parameters: {len(discovered_component.get('parameters', []) or [])}",
                f"Ports: {len(discovered_component.get('ports', []) or [])}",
                f"Subcomponent slots: {len(discovered_component.get('subcomp_slots', []) or [])}",
                f"Statistics: {len(discovered_component.get('statistics', []) or [])}",
            ),
        )

    if discovered_component is None and baseline_component is not None:
        return ComponentMetadataDiff(
            key=key,
            display_name=display_name,
            status="missing",
            lines=(
                "This bundled baseline component was not exposed by the configured "
                "SST installation during discovery.",
                "Projects can still use the bundled metadata for editing, but running "
                "against this SST installation may fail if the component is required.",
            ),
        )

    assert baseline_component is not None
    assert discovered_component is not None

    if _component_signature(baseline_component) == _component_signature(discovered_component):
        return ComponentMetadataDiff(
            key=key,
            display_name=display_name,
            status="baseline",
            lines=("The discovered metadata matches the bundled baseline catalog.",),
        )

    lines: list[str] = ["This component differs from the bundled baseline catalog."]
    lines.extend(_scalar_metadata_diff_lines(baseline_component, discovered_component))
    lines.extend(
        _record_collection_diff_lines(
            label="parameters",
            baseline_records=baseline_component.get("parameters", []) or [],
            discovered_records=discovered_component.get("parameters", []) or [],
        )
    )
    lines.extend(
        _record_collection_diff_lines(
            label="ports",
            baseline_records=baseline_component.get("ports", []) or [],
            discovered_records=discovered_component.get("ports", []) or [],
        )
    )
    lines.extend(
        _record_collection_diff_lines(
            label="subcomponent slots",
            baseline_records=baseline_component.get("subcomp_slots", []) or [],
            discovered_records=discovered_component.get("subcomp_slots", []) or [],
        )
    )
    lines.extend(
        _record_collection_diff_lines(
            label="statistics",
            baseline_records=baseline_component.get("statistics", []) or [],
            discovered_records=discovered_component.get("statistics", []) or [],
        )
    )

    if len(lines) == 1:
        lines.append("The metadata changed, but FUSE could not reduce the difference to named fields.")

    return ComponentMetadataDiff(
        key=key,
        display_name=display_name,
        status="changed",
        lines=tuple(lines),
    )


def _catalog_component_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        component_key(component): component
        for component in catalog.get("components", []) or []
    }


def _catalog_element_map(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(element.get("name", "") or ""): element
        for element in catalog.get("elements", []) or []
        if str(element.get("name", "") or "")
    }


def _toolchain_fingerprint(
    version: str,
    toolchain: ToolchainSettings,
    *,
    project_uid: str = "",
) -> str:
    payload = {
        "version": normalize_sst_version(version),
        "backend": toolchain.backend,
        "host": toolchain.host,
        "port": toolchain.port,
        "username": toolchain.username,
        "host_alias": toolchain.host_alias,
        "remote_setup_command": toolchain.remote_setup_command,
        "tool_paths": dict(sorted((toolchain.tool_paths or {}).items())),
        "environment": dict(sorted((toolchain.environment or {}).items())),
        "options": dict(sorted((toolchain.options or {}).items())),
        "project_uid": project_uid or "",
    }

    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]


def _toolchain_label(version: str, toolchain: ToolchainSettings, custom_count: int = 0) -> str:
    if toolchain.backend == "ssh":
        host = toolchain.host_alias or toolchain.host or "remote"
        base = f"SST {version} — {host} custom"
    else:
        path = (
            toolchain.tool_paths.get("sstInfo", "")
            or toolchain.tool_paths.get("sst", "")
            or "local"
        )
        base = f"SST {version} — Local custom"

        if path:
            base = f"{base} ({Path(path).parent})"

    if custom_count:
        base = f"{base} [{custom_count} custom]"

    return base


def _component_count_for_version(version: str, *, source_kind: str = "bundled-component-catalog") -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM sst_components c
            JOIN sst_framework_versions fv
              ON c.framework_version_id = fv.id
            WHERE fv.version = ?
              AND fv.source_kind = ?
            """,
            (normalize_sst_version(version), source_kind),
        ).fetchone()

    return int(row["count"]) if row is not None else 0


def import_bundled_component_catalogs() -> None:
    """Import bundled SST component catalogs into the database at setup time."""

    initialize_database()

    policy_versions = set(available_policy_catalog_versions())
    component_versions = available_component_catalog_versions()

    if not component_versions:
        print("SST plugin: no bundled SST component catalogs were found.")
        return

    default_candidates = sorted(
        policy_versions.intersection(component_versions) or set(component_versions),
        key=_version_sort_key,
    )
    default_version = default_candidates[-1] if default_candidates else component_versions[-1]

    for version in component_versions:
        if policy_versions and version not in policy_versions:
            print(
                f"SST plugin: bundled component catalog for SST {version} "
                "does not have a matching policy catalog; skipping."
            )
            continue

        if _component_count_for_version(version) > 0:
            continue

        catalog_path = component_catalog_path_for_version(version)

        print(
            f"SST plugin: importing bundled SST component catalog for SST {version}..."
        )

        sync_sstinfo_catalog_json_to_database(
            path=catalog_path,
            version=version,
            label=f"SST {version}",
            source_kind="bundled-component-catalog",
            source_path="",
            command=f"bundled SST component catalog: {catalog_path}",
            is_default=(version == default_version),
            clear_existing=True,
        )


def previous_enablement_for_fingerprint(version: str, fingerprint: str) -> dict[str, bool]:
    """Return persisted enablement choices for a previous discovery, if any."""

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM sst_component_catalog_sources
            WHERE base_version = ?
              AND source_fingerprint = ?
            """,
            (normalize_sst_version(version), fingerprint),
        ).fetchone()

        if row is None:
            return {}

        rows = conn.execute(
            """
            SELECT component_key, enabled
            FROM sst_component_enablement
            WHERE source_id = ?
            """,
            (int(row["id"]),),
        ).fetchall()

    return {
        str(item["component_key"]): bool(item["enabled"])
        for item in rows
    }


def previous_enabled_keys_for_fingerprint(version: str, fingerprint: str) -> set[str]:
    return {
        key
        for key, enabled in previous_enablement_for_fingerprint(version, fingerprint).items()
        if enabled
    }


def classify_discovered_catalog(
    *,
    version: str,
    discovered_catalog: dict[str, Any],
    baseline_catalog: dict[str, Any] | None = None,
    previous_enablement: dict[str, bool] | None = None,
) -> list[DiscoveredComponentEntry]:
    """Classify discovered metadata against the bundled baseline catalog."""

    baseline_catalog = baseline_catalog if baseline_catalog is not None else load_component_catalog(version)
    previous_enablement = previous_enablement or {}

    baseline_by_key = _catalog_component_map(baseline_catalog)
    discovered_by_key = _catalog_component_map(discovered_catalog)

    entries: list[DiscoveredComponentEntry] = []

    for key, component in sorted(
        discovered_by_key.items(),
        key=lambda item: (
            str(item[1].get("element_name", "") or ""),
            int(item[1].get("is_subcomp", 0) or 0),
            str(item[1].get("name", "") or ""),
        ),
    ):
        baseline_component = baseline_by_key.get(key)

        if baseline_component is None:
            status = "custom"
            enabled_by_default = previous_enablement.get(key, False)
        elif _component_signature(component) != _component_signature(baseline_component):
            status = "changed"
            enabled_by_default = previous_enablement.get(key, True)
        else:
            status = "baseline"
            enabled_by_default = True

        entries.append(
            DiscoveredComponentEntry(
                key=key,
                element_name=str(component.get("element_name", "") or ""),
                name=str(component.get("name", "") or ""),
                display_name=_component_display_name(component),
                kind="SubComponent" if int(component.get("is_subcomp", 0) or 0) else "Component",
                status=status,
                description=str(component.get("description", "") or ""),
                parameter_count=len(component.get("parameters", []) or []),
                port_count=len(component.get("ports", []) or []),
                subcomponent_slot_count=len(component.get("subcomp_slots", []) or []),
                statistic_count=len(component.get("statistics", []) or []),
                enabled_by_default=enabled_by_default,
                previously_enabled=bool(previous_enablement.get(key, False)),
            )
        )

    for key, component in sorted(
        baseline_by_key.items(),
        key=lambda item: (
            str(item[1].get("element_name", "") or ""),
            int(item[1].get("is_subcomp", 0) or 0),
            str(item[1].get("name", "") or ""),
        ),
    ):
        if key in discovered_by_key:
            continue

        entries.append(
            DiscoveredComponentEntry(
                key=key,
                element_name=str(component.get("element_name", "") or ""),
                name=str(component.get("name", "") or ""),
                display_name=_component_display_name(component),
                kind="SubComponent" if int(component.get("is_subcomp", 0) or 0) else "Component",
                status="missing",
                description=str(component.get("description", "") or ""),
                parameter_count=len(component.get("parameters", []) or []),
                port_count=len(component.get("ports", []) or []),
                subcomponent_slot_count=len(component.get("subcomp_slots", []) or []),
                statistic_count=len(component.get("statistics", []) or []),
                enabled_by_default=False,
                previously_enabled=False,
            )
        )

    return entries


def discover_sst_components_for_toolchain(
    *,
    version: str,
    toolchain: ToolchainSettings,
    timeout_seconds: int = 120,
    project_uid: str = "",
) -> SSTComponentDiscovery:
    """Run configured local/remote sst-info and classify installed components."""

    version = normalize_sst_version(version)

    if not version:
        raise ValueError("An SST version is required for component discovery.")

    baseline_catalog = load_component_catalog(version)
    fingerprint = _toolchain_fingerprint(version, toolchain, project_uid=project_uid)
    previous_enablement = previous_enablement_for_fingerprint(version, fingerprint)

    result = get_sstinfo_for_toolchain(toolchain, timeout_seconds=timeout_seconds)

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    elements, components = parse_sstinfo_output(result.stdout)
    backend = str(getattr(toolchain, "backend", "") or "local")
    discovered_catalog = parsed_sstinfo_to_catalog_dict(
        version=version,
        elements=elements,
        components=components,
        source=f"{backend} sst-info discovery",
    )

    entries = classify_discovered_catalog(
        version=version,
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        previous_enablement=previous_enablement,
    )

    return SSTComponentDiscovery(
        version=version,
        source_label=_toolchain_label(version, toolchain),
        source_fingerprint=fingerprint,
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        entries=entries,
        previous_enabled_keys={key for key, enabled in previous_enablement.items() if enabled},
        command_text=" ".join(result.command),
    )


def _merge_catalog_for_selection(
    *,
    version: str,
    baseline_catalog: dict[str, Any],
    discovered_catalog: dict[str, Any],
    enabled_keys: set[str],
) -> dict[str, Any]:
    """Return baseline metadata plus enabled custom/changed discovered entries."""

    baseline_components = _catalog_component_map(baseline_catalog)
    discovered_components = _catalog_component_map(discovered_catalog)

    merged_components: dict[str, dict[str, Any]] = dict(baseline_components)

    for key in sorted(enabled_keys):
        component = discovered_components.get(key)

        if component is not None:
            merged_components[key] = component

    merged_elements = _catalog_element_map(baseline_catalog)

    for component in merged_components.values():
        element_name = str(component.get("element_name", "") or "")

        if not element_name:
            continue

        if element_name not in merged_elements:
            merged_elements[element_name] = {
                "name": element_name,
                "description": "",
            }

    for element in discovered_catalog.get("elements", []) or []:
        element_name = str(element.get("name", "") or "")

        if not element_name:
            continue

        if element_name not in merged_elements:
            merged_elements[element_name] = element

    return {
        "schema_version": "1.0.0",
        "source": "FUSE custom SST component catalog",
        "sst_version": normalize_sst_version(version),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "baseline_component_catalog": f"sst-{normalize_sst_version(version)}.json",
        "elements": sorted(
            merged_elements.values(),
            key=lambda element: str(element.get("name", "") or ""),
        ),
        "components": sorted(
            merged_components.values(),
            key=lambda component: (
                str(component.get("element_name", "") or ""),
                int(component.get("is_subcomp", 0) or 0),
                str(component.get("name", "") or ""),
            ),
        ),
    }


def _write_custom_catalog_snapshot(
    *,
    discovery: SSTComponentDiscovery,
    catalog: dict[str, Any],
) -> Path:
    _CUSTOM_CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    path = _CUSTOM_CATALOG_DIR / (
        f"sst-{discovery.version}-{discovery.source_fingerprint}.json"
    )
    path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def _record_catalog_source_and_enablement(
    *,
    framework_version_id: int,
    discovery: SSTComponentDiscovery,
    enabled_keys: set[str],
    catalog_path: Path,
    project_uid: str = "",
) -> None:
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sst_component_catalog_sources (
                framework_version_id,
                base_version,
                source_kind,
                source_label,
                source_fingerprint,
                catalog_path,
                discovered_at
            )
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(base_version, source_fingerprint) DO UPDATE SET
                framework_version_id = excluded.framework_version_id,
                source_kind = excluded.source_kind,
                source_label = excluded.source_label,
                catalog_path = excluded.catalog_path,
                discovered_at = CURRENT_TIMESTAMP
            """,
            (
                framework_version_id,
                discovery.version,
                "toolchain-discovery",
                discovery.source_label,
                discovery.source_fingerprint,
                str(catalog_path),
            ),
        )

        source_row = conn.execute(
            """
            SELECT id
            FROM sst_component_catalog_sources
            WHERE base_version = ?
              AND source_fingerprint = ?
            """,
            (discovery.version, discovery.source_fingerprint),
        ).fetchone()

        source_id = int(source_row["id"]) if source_row is not None else int(cursor.lastrowid)

        conn.execute(
            "DELETE FROM sst_component_enablement WHERE source_id = ?",
            (source_id,),
        )

        for entry in discovery.entries:
            if entry.status not in {"custom", "changed"}:
                continue

            enabled = 1 if entry.key in enabled_keys else 0

            conn.execute(
                """
                INSERT INTO sst_component_enablement (
                    source_id,
                    component_key,
                    status,
                    enabled
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    source_id,
                    entry.key,
                    entry.status,
                    enabled,
                ),
            )

            if project_uid:
                conn.execute(
                    """
                    INSERT INTO sst_project_component_enablement (
                        project_key,
                        framework_version_id,
                        base_version,
                        source_fingerprint,
                        component_key,
                        status,
                        enabled,
                        reason,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'user-selection', CURRENT_TIMESTAMP)
                    ON CONFLICT(project_key, base_version, source_fingerprint, component_key)
                    DO UPDATE SET
                        framework_version_id = excluded.framework_version_id,
                        status = excluded.status,
                        enabled = excluded.enabled,
                        reason = excluded.reason,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        project_uid,
                        framework_version_id,
                        discovery.version,
                        discovery.source_fingerprint,
                        entry.key,
                        entry.status,
                        enabled,
                    ),
                )


def import_custom_component_selection(
    *,
    discovery: SSTComponentDiscovery,
    enabled_keys: set[str],
    project_uid: str = "",
) -> tuple[int, str, Path]:
    """Create/update a custom SST target from selected discovered components."""

    actionable_enabled = {
        entry.key
        for entry in discovery.entries
        if entry.key in enabled_keys and entry.status in {"custom", "changed"}
    }

    custom_count = sum(
        1
        for entry in discovery.entries
        if entry.key in actionable_enabled and entry.status == "custom"
    )

    label = _toolchain_label(
        discovery.version,
        ToolchainSettings(),  # used only for fallback; overwritten below
        custom_count=custom_count,
    )
    # Preserve the real source label but append a count with current selection.
    label = discovery.source_label
    if custom_count:
        label = f"{label} [{custom_count} custom]"

    custom_catalog = _merge_catalog_for_selection(
        version=discovery.version,
        baseline_catalog=discovery.baseline_catalog,
        discovered_catalog=discovery.discovered_catalog,
        enabled_keys=actionable_enabled,
    )
    catalog_path = _write_custom_catalog_snapshot(
        discovery=discovery,
        catalog=custom_catalog,
    )

    source_path = f"toolchain:{discovery.source_fingerprint}"

    framework_version_id = sync_sstinfo_catalog_json_to_database(
        path=catalog_path,
        version=discovery.version,
        label=label,
        source_kind="toolchain-component-catalog",
        source_path=source_path,
        command=discovery.command_text or f"custom SST component catalog: {catalog_path}",
        is_default=True,
        clear_existing=True,
    )

    _record_catalog_source_and_enablement(
        framework_version_id=framework_version_id,
        discovery=discovery,
        enabled_keys=actionable_enabled,
        catalog_path=catalog_path,
        project_uid=project_uid,
    )

    return framework_version_id, label, catalog_path

def _component_key_from_node(node) -> str:
    component = getattr(node, "component", None)
    if component is None:
        return ""

    plugin_id = str(getattr(component, "plugin_id", "") or "")
    if plugin_id != "sst":
        return ""

    element_name = str(getattr(component, "element", "") or "").strip()
    name = str(getattr(component, "name", "") or "").strip()

    if not name:
        return ""

    return _component_key_from_parts(
        element_name,
        name,
        int(getattr(component, "is_subcomp", 0) or 0),
    )


def used_sst_component_keys_for_scene(scene) -> set[str]:
    """Return SST component/subcomponent keys used by a scene.

    The check flattens composites when possible so runtime verification sees the
    same SST components that export will generate.
    """

    try:
        from fuse.core.model.composite_flattening import flatten_scene_for_export

        scene = flatten_scene_for_export(scene)
    except Exception:
        pass

    keys: set[str] = set()

    for node in list(getattr(scene, "component_items", lambda: [])()):
        key = _component_key_from_node(node)
        if key:
            keys.add(key)

    return keys


def component_key_display_name(key: str) -> str:
    if "|" in key:
        name, kind = key.split("|", 1)
        if kind == "subcomponent":
            return f"{name} (SubComponent)"
        return f"{name} (Component)"
    return key


def _enabled_discovered_component_keys_for_target(
    framework_version_id: int,
) -> dict[str, str]:
    """Return enabled custom/changed component keys for a custom target."""

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ce.component_key, ce.status
            FROM sst_component_catalog_sources src
            JOIN sst_component_enablement ce
              ON ce.source_id = src.id
            WHERE src.framework_version_id = ?
              AND ce.enabled = 1
            """,
            (framework_version_id,),
        ).fetchall()

    return {
        str(row["component_key"]): str(row["status"] or "")
        for row in rows
    }


def _target_metadata(framework_version_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, version, label, source_kind, source_path, sst_info_command
            FROM sst_framework_versions
            WHERE id = ?
            """,
            (framework_version_id,),
        ).fetchone()

    return dict(row) if row is not None else {}


def bundled_target_for_version(version: str) -> tuple[str, str] | None:
    """Return the bundled baseline SST target id/label for a version, if present."""

    normalized = normalize_sst_version(version)

    if not normalized:
        return None

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT id, label
            FROM sst_framework_versions
            WHERE version = ?
              AND source_kind = 'bundled-component-catalog'
              AND source_path = ''
            ORDER BY is_default DESC, id ASC
            LIMIT 1
            """,
            (normalized,),
        ).fetchone()

    if row is None:
        return None

    return str(row["id"]), str(row["label"] or f"SST {normalized}")


def _catalog_source_for_target(framework_version_id: int) -> dict[str, Any]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                framework_version_id,
                base_version,
                source_kind,
                source_label,
                source_fingerprint,
                catalog_path,
                discovered_at
            FROM sst_component_catalog_sources
            WHERE framework_version_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (framework_version_id,),
        ).fetchone()

    return dict(row) if row is not None else {}


def _enablement_counts_for_source(source_id: int | None) -> dict[str, int]:
    if not source_id:
        return {
            "enabled_custom_count": 0,
            "enabled_changed_count": 0,
            "disabled_discovered_count": 0,
        }

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT status, enabled, COUNT(*) AS count
            FROM sst_component_enablement
            WHERE source_id = ?
            GROUP BY status, enabled
            """,
            (source_id,),
        ).fetchall()

    counts = {
        "enabled_custom_count": 0,
        "enabled_changed_count": 0,
        "disabled_discovered_count": 0,
    }

    for row in rows:
        status = str(row["status"] or "")
        enabled = int(row["enabled"] or 0)
        count = int(row["count"] or 0)

        if enabled and status == "custom":
            counts["enabled_custom_count"] += count
        elif enabled and status == "changed":
            counts["enabled_changed_count"] += count
        elif not enabled and status in {"custom", "changed"}:
            counts["disabled_discovered_count"] += count

    return counts


def catalog_source_summary_for_target(
    framework_version_id: int | str | None,
    *,
    toolchain: ToolchainSettings | None = None,
    project_uid: str = "",
) -> SSTCatalogSourceSummary:
    """Return a user-facing lifecycle summary for the selected SST catalog target."""

    if framework_version_id in (None, ""):
        return SSTCatalogSourceSummary()

    try:
        target_id = int(framework_version_id)
    except (TypeError, ValueError):
        return SSTCatalogSourceSummary(target_id=str(framework_version_id or ""))

    metadata = _target_metadata(target_id)

    if not metadata:
        return SSTCatalogSourceSummary(target_id=str(framework_version_id or ""))

    version = normalize_sst_version(str(metadata.get("version", "") or ""))
    source = _catalog_source_for_target(target_id)
    source_id = int(source.get("id") or 0) if source else None

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM sst_components
            WHERE framework_version_id = ?
            """,
            (target_id,),
        ).fetchone()

    component_count = int(row["count"] or 0) if row is not None else 0

    baseline_count = 0
    try:
        baseline_catalog = load_component_catalog(version)
        baseline_count = len(baseline_catalog.get("components", []) or [])
    except Exception:
        baseline_count = 0

    enablement_counts = _enablement_counts_for_source(source_id)

    current_fingerprint = ""
    fingerprint_stale = False

    if toolchain is not None and source:
        current_fingerprint = _toolchain_fingerprint(version, toolchain, project_uid=project_uid)
        stored_fingerprint = str(source.get("source_fingerprint", "") or "")
        fingerprint_stale = bool(stored_fingerprint and current_fingerprint != stored_fingerprint)

    return SSTCatalogSourceSummary(
        target_id=str(target_id),
        target_label=str(metadata.get("label", "") or ""),
        version=version,
        source_kind=str(metadata.get("source_kind", "") or ""),
        source_path=str(metadata.get("source_path", "") or ""),
        command_text=str(metadata.get("sst_info_command", "") or ""),
        catalog_path=str(source.get("catalog_path", "") or ""),
        source_label=str(source.get("source_label", "") or ""),
        source_fingerprint=str(source.get("source_fingerprint", "") or ""),
        discovered_at=str(source.get("discovered_at", "") or ""),
        component_count=component_count,
        baseline_component_count=baseline_count,
        current_toolchain_fingerprint=current_fingerprint,
        fingerprint_stale=fingerprint_stale,
        **enablement_counts,
    )


def revert_target_to_bundled_baseline(
    framework_version_id: int | str | None,
) -> tuple[str, str] | None:
    """Return the bundled baseline target for the selected target's SST version."""

    if framework_version_id in (None, ""):
        return None

    try:
        target_id = int(framework_version_id)
    except (TypeError, ValueError):
        return None

    metadata = _target_metadata(target_id)
    version = str(metadata.get("version", "") or "")

    if not version:
        return None

    return bundled_target_for_version(version)


def delete_custom_catalog_target(
    framework_version_id: int | str | None,
    *,
    force: bool = False,
) -> tuple[bool, str]:
    """Delete a toolchain-discovered custom target and its DB metadata.

    Bundled baseline targets are intentionally protected.
    """

    if framework_version_id in (None, ""):
        return False, "No SST target is selected."

    try:
        target_id = int(framework_version_id)
    except (TypeError, ValueError):
        return False, f"Invalid SST target id: {framework_version_id!r}."

    metadata = _target_metadata(target_id)

    if not metadata:
        return False, f"SST target {target_id} was not found."

    if str(metadata.get("source_kind", "") or "") != "toolchain-component-catalog":
        return False, "Only toolchain-discovered custom SST catalog targets can be deleted."

    with get_connection() as conn:
        usage_rows = conn.execute(
            """
            SELECT project_key, COUNT(*) AS count
            FROM sst_project_component_enablement
            WHERE framework_version_id = ?
            GROUP BY project_key
            """,
            (target_id,),
        ).fetchall()

        if usage_rows and not force:
            projects = ", ".join(str(row["project_key"] or "<unknown>") for row in usage_rows[:5])
            extra = "" if len(usage_rows) <= 5 else f" and {len(usage_rows) - 5} more"
            return (
                False,
                "This custom SST catalog target has project-scoped enablement "
                f"records for {projects}{extra}. Confirm deletion to remove it.",
            )

        source_rows = conn.execute(
            """
            SELECT id, catalog_path
            FROM sst_component_catalog_sources
            WHERE framework_version_id = ?
            """,
            (target_id,),
        ).fetchall()

        for row in source_rows:
            conn.execute(
                "DELETE FROM sst_component_enablement WHERE source_id = ?",
                (int(row["id"]),),
            )

        conn.execute(
            "DELETE FROM sst_component_catalog_sources WHERE framework_version_id = ?",
            (target_id,),
        )
        conn.execute(
            "DELETE FROM sst_project_component_enablement WHERE framework_version_id = ?",
            (target_id,),
        )

        # Delete child metadata explicitly so this works even when SQLite foreign
        # key enforcement is disabled by the connection configuration.
        for table in (
            "sst_ports",
            "sst_subcomp_slots",
            "sst_statistics",
            "sst_parameters",
            "sst_components",
            "sst_elements",
            "sst_info_runs",
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE framework_version_id = ?",
                (target_id,),
            )

        conn.execute(
            "DELETE FROM sst_framework_versions WHERE id = ?",
            (target_id,),
        )

    deleted_paths: list[str] = []
    for row in source_rows:
        path_text = str(row["catalog_path"] or "")
        if not path_text:
            continue
        try:
            path = Path(path_text)
            if path.exists() and _CUSTOM_CATALOG_DIR in path.resolve().parents:
                path.unlink()
                deleted_paths.append(str(path))
        except Exception:
            pass

    suffix = f" Deleted {len(deleted_paths)} catalog snapshot file(s)." if deleted_paths else ""
    return True, f"Deleted custom SST catalog target {metadata.get('label') or target_id}.{suffix}"


def sst_target_requires_runtime_verification(framework_version_id: int | str | None) -> bool:
    """Return true if an SST target depends on a discovered/custom runtime."""

    if framework_version_id in (None, ""):
        return False

    try:
        target_id = int(framework_version_id)
    except (TypeError, ValueError):
        return False

    metadata = _target_metadata(target_id)

    if not metadata:
        return False

    if str(metadata.get("source_kind", "")) == "toolchain-component-catalog":
        return True

    return bool(_enabled_discovered_component_keys_for_target(target_id))


def export_policy_diagnostics_for_scene(scene) -> SSTExportPolicyDiagnostics:
    """Return grouped export diagnostics for custom/changed components in a scene.

    The exporter uses this to avoid noisy per-parameter messages. Bundled
    baseline models return an empty diagnostic report. Toolchain-discovered
    targets report only custom/changed components that are actually used by the
    model.
    """

    try:
        from fuse.core.model.composite_flattening import flatten_scene_for_export

        scene = flatten_scene_for_export(scene)
    except Exception:
        pass

    target_ids: set[str] = set()

    for node in list(getattr(scene, "component_items", lambda: [])()):
        component = getattr(node, "component", None)
        if component is None:
            continue

        if str(getattr(component, "plugin_id", "") or "") != "sst":
            continue

        target_id = str(getattr(component, "target_id", "") or "").strip()
        if target_id:
            target_ids.add(target_id)

    if len(target_ids) != 1:
        return SSTExportPolicyDiagnostics(
            used_component_keys=used_sst_component_keys_for_scene(scene),
        )

    target_id_text = next(iter(target_ids))

    try:
        target_id = int(target_id_text)
    except (TypeError, ValueError):
        return SSTExportPolicyDiagnostics(
            target_id=target_id_text,
            used_component_keys=used_sst_component_keys_for_scene(scene),
        )

    status_by_key = _enabled_discovered_component_keys_for_target(target_id)

    if not status_by_key:
        metadata = _target_metadata(target_id)
        return SSTExportPolicyDiagnostics(
            target_id=target_id_text,
            target_label=str(metadata.get("label", "") or ""),
            used_component_keys=used_sst_component_keys_for_scene(scene),
        )

    used_keys = used_sst_component_keys_for_scene(scene)
    custom_keys = {
        key
        for key in used_keys
        if status_by_key.get(key) == "custom"
    }
    changed_keys = {
        key
        for key in used_keys
        if status_by_key.get(key) == "changed"
    }

    metadata = _target_metadata(target_id)

    return SSTExportPolicyDiagnostics(
        target_id=target_id_text,
        target_label=str(metadata.get("label", "") or ""),
        used_component_keys=used_keys,
        custom_component_keys=custom_keys,
        changed_component_keys=changed_keys,
    )


def verify_project_sst_runtime(
    *,
    scene,
    framework_version_id: int | str,
    expected_version: str,
    target_label: str,
    toolchain: ToolchainSettings,
    timeout_seconds: int = 120,
) -> SSTRuntimeVerificationReport:
    """Verify that the configured SST runtime exposes components used by a project."""

    try:
        target_id = int(framework_version_id)
    except (TypeError, ValueError):
        target_id = 0

    expected_version = normalize_sst_version(expected_version)
    used_keys = used_sst_component_keys_for_scene(scene)
    enabled_status_by_key = _enabled_discovered_component_keys_for_target(target_id)
    enabled_keys = set(enabled_status_by_key)

    report = SSTRuntimeVerificationReport(
        ok=False,
        version=expected_version,
        target_id=str(framework_version_id or ""),
        target_label=target_label or "",
        used_component_keys=used_keys,
        enabled_custom_component_keys=enabled_keys,
    )

    ok, version_message, version_result = validate_sst_toolchain(
        toolchain=toolchain,
        expected_version=expected_version,
        timeout_seconds=timeout_seconds,
        version_policy="major_minor_patch",
    )

    if version_result is not None:
        report.command_text = " ".join(version_result.command)

    if not ok:
        report.errors.append(version_message)
        return report

    try:
        result = get_sstinfo_for_toolchain(
            toolchain=toolchain,
            timeout_seconds=timeout_seconds,
        )
    except Exception as exc:
        report.errors.append(
            f"FUSE could not run sst-info against the configured SST runtime: {exc}"
        )
        return report

    report.command_text = " ".join(result.command)

    if result.return_code != 0:
        output = (result.stdout + "\n" + result.stderr).strip()
        report.errors.append(
            "sst-info failed while verifying runtime component availability. "
            f"Return code: {result.return_code}\n{output}"
        )
        return report

    try:
        _, runtime_components = parse_sstinfo_output(result.stdout)
    except Exception as exc:
        report.errors.append(
            f"FUSE could not parse sst-info output while verifying runtime availability: {exc}"
        )
        return report

    runtime_keys = {component_key(component) for component in runtime_components}
    report.runtime_component_keys = runtime_keys

    missing_used = used_keys - runtime_keys
    missing_enabled = (enabled_keys - runtime_keys) - missing_used

    report.missing_used_component_keys = missing_used
    report.missing_enabled_component_keys = missing_enabled

    if missing_used:
        report.errors.append(
            "The configured SST runtime does not expose these components used by "
            "the current model: "
            + ", ".join(component_key_display_name(key) for key in sorted(missing_used))
        )

    if missing_enabled:
        report.warnings.append(
            "These enabled custom/changed SST components are not currently exposed "
            "by the configured runtime, but they are not used by the current model: "
            + ", ".join(component_key_display_name(key) for key in sorted(missing_enabled))
        )

    custom_used = used_keys.intersection(enabled_keys)
    if custom_used and not missing_used.intersection(custom_used):
        report.infos.append(
            "All custom/changed SST components used by this model are available "
            "on the configured runtime."
        )
    elif not custom_used:
        report.infos.append(
            "The current model does not use any enabled custom/changed SST components."
        )

    if not missing_used:
        report.ok = True

    return report

