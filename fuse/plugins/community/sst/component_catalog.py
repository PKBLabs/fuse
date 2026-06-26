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
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from fuse.core.model.project_settings import ToolchainSettings
from fuse.core.persistence.database import get_connection, get_database_path
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
_CUSTOM_CATALOG_DIR = get_database_path().parent / "sst" / "component_catalogs" / "toolchains"


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
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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
                    1 if entry.key in enabled_keys else 0,
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

