# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Bundled and toolchain-discovered SST component catalog helpers.

Bundled catalogs seed the SST database at install/bootstrap time. Toolchain
catalogs are discovered from a project's configured local or remote sst-info and
imported as separate custom framework targets so the bundled baseline rows stay
clean.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tempfile

from fuse.core.model.project_settings import ToolchainSettings
from fuse.core.persistence.database import get_connection, get_database_path
from fuse.plugins.community.sst.get_sstinfo import (
    ParsedComponent,
    ParsedElement,
    get_sstinfo_for_toolchain,
    parse_sstinfo_output,
    parsed_sstinfo_to_catalog_dict,
    read_sstinfo_catalog_json,
    sync_parsed_sstinfo_to_database,
    sync_sstinfo_catalog_json_to_database,
    toolchain_fingerprint,
    write_sstinfo_catalog_json,
)
from fuse.plugins.community.sst.initialize_db import (
    get_or_create_sst_framework_version,
    initialize_database,
)
from fuse.plugins.community.sst.policy.loader import available_policy_catalog_versions


_COMPONENT_CATALOG_DIR = Path(__file__).resolve().parent / "component_catalogs"


@dataclass(frozen=True)
class CatalogComponentSummary:
    """A compact component record used by custom-component management UI."""

    identity: str
    element_name: str
    name: str
    kind: str
    description: str
    parameter_count: int
    port_count: int
    slot_count: int
    status: str


@dataclass(frozen=True)
class DiscoveredCatalog:
    """A parsed component catalog discovered from one SST toolchain."""

    version: str
    elements: list[ParsedElement]
    components: list[ParsedComponent]
    baseline_identities: set[str]
    custom_components: list[ParsedComponent]
    changed_components: list[ParsedComponent]
    missing_baseline_identities: set[str]
    stdout: str


def _version_sort_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


def component_identity(component: ParsedComponent) -> str:
    return f"{component.element_name}.{component.name}"


def component_catalog_path_for_version(version: str) -> Path:
    return _COMPONENT_CATALOG_DIR / f"sst-{version}.json"


def available_component_catalog_versions() -> list[str]:
    if not _COMPONENT_CATALOG_DIR.exists():
        return []

    versions: list[str] = []

    for path in _COMPONENT_CATALOG_DIR.glob("sst-*.json"):
        version = path.stem.removeprefix("sst-").strip()

        if version:
            versions.append(version)

    return sorted(versions, key=_version_sort_key)


def _component_count_for_version(version: str, *, source_kind: str = "bundled-sst-info-catalog") -> int:
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
            (version, source_kind),
        ).fetchone()

    return int(row["count"]) if row is not None else 0


def import_bundled_component_catalogs() -> None:
    """Import bundled SST component metadata into the database.

    This makes the SST palette/component list available immediately after FUSE
    setup, even when the user has not configured local or remote SST tools.
    """

    initialize_database()

    policy_versions = set(available_policy_catalog_versions())
    component_versions = available_component_catalog_versions()

    if not component_versions:
        print("SST plugin: no bundled SST component catalogs were found.")
        return

    default_version = sorted(
        policy_versions or set(component_versions),
        key=_version_sort_key,
    )[-1]

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
            f"SST plugin: importing bundled SST component catalog "
            f"for SST {version}..."
        )

        sync_sstinfo_catalog_json_to_database(
            path=catalog_path,
            version=version,
            label=f"SST {version}",
            is_default=(version == default_version),
            source_kind="bundled-sst-info-catalog",
            source_path=str(catalog_path),
        )


def load_baseline_component_catalog(
    version: str,
) -> tuple[list[ParsedElement], list[ParsedComponent]]:
    """Load the bundled component catalog for a supported SST version."""

    catalog_path = component_catalog_path_for_version(version)

    if not catalog_path.exists():
        raise FileNotFoundError(
            f"Bundled SST component catalog not found: {catalog_path}"
        )

    _catalog_version, elements, components, _catalog = read_sstinfo_catalog_json(catalog_path)
    return elements, components


def _component_signature(component: ParsedComponent) -> dict:
    """Return metadata that indicates whether a discovered component changed."""

    return {
        "description": component.description,
        "is_subcomp": int(component.is_subcomp),
        "iface": component.iface,
        "category": component.category,
        "parameters": [
            (p.name, p.default_val, int(p.required), p.description)
            for p in component.parameters
        ],
        "ports": [
            (
                p.name,
                p.description,
                p.iface,
                int(p.is_variable),
                p.base_name,
                p.count_parameter,
                int(p.default_count),
            )
            for p in component.ports
        ],
        "slots": [
            (s.name, s.description, s.iface)
            for s in component.subcomp_slots
        ],
    }


def discover_sst_toolchain_catalog(
    *,
    version: str,
    toolchain: ToolchainSettings,
    timeout_seconds: int = 120,
) -> DiscoveredCatalog:
    """Run configured sst-info and compare discovered metadata to bundled baseline."""

    result = get_sstinfo_for_toolchain(
        toolchain,
        timeout_seconds=timeout_seconds,
    )

    if result.return_code != 0:
        raise RuntimeError(
            f"sst-info failed with return code {result.return_code}\n"
            f"STDERR:\n{result.stderr}"
        )

    discovered_elements, discovered_components = parse_sstinfo_output(result.stdout)
    _baseline_elements, baseline_components = load_baseline_component_catalog(version)

    baseline_by_identity = {
        component_identity(component): component
        for component in baseline_components
    }
    discovered_by_identity = {
        component_identity(component): component
        for component in discovered_components
    }

    baseline_identities = set(baseline_by_identity)
    discovered_identities = set(discovered_by_identity)

    custom_components = [
        component
        for identity, component in sorted(discovered_by_identity.items())
        if identity not in baseline_identities
    ]

    changed_components = []
    for identity in sorted(discovered_identities & baseline_identities):
        baseline = baseline_by_identity[identity]
        discovered = discovered_by_identity[identity]

        if _component_signature(baseline) != _component_signature(discovered):
            changed_components.append(discovered)

    missing_baseline_identities = baseline_identities - discovered_identities

    return DiscoveredCatalog(
        version=version,
        elements=discovered_elements,
        components=discovered_components,
        baseline_identities=baseline_identities,
        custom_components=custom_components,
        changed_components=changed_components,
        missing_baseline_identities=missing_baseline_identities,
        stdout=result.stdout,
    )


def summarize_components(
    components: list[ParsedComponent],
    *,
    status: str,
) -> list[CatalogComponentSummary]:
    """Return compact rows for component-management dialogs."""

    summaries: list[CatalogComponentSummary] = []

    for component in sorted(components, key=lambda c: (c.element_name, int(c.is_subcomp), c.name)):
        summaries.append(
            CatalogComponentSummary(
                identity=component_identity(component),
                element_name=component.element_name,
                name=component.name,
                kind="SubComponent" if int(component.is_subcomp) else "Component",
                description=component.description,
                parameter_count=len(component.parameters),
                port_count=len(component.ports),
                slot_count=len(component.subcomp_slots),
                status=status,
            )
        )

    return summaries


def write_toolchain_catalog_snapshot(
    *,
    version: str,
    discovery: DiscoveredCatalog,
    fingerprint: str,
) -> Path:
    """Persist a discovered catalog snapshot under FUSE app_data."""

    db_path = get_database_path()
    snapshot_dir = db_path.parent / "sst" / "component_catalogs" / "toolchains"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    out_path = snapshot_dir / f"sst-{version}-{fingerprint}.json"
    catalog = parsed_sstinfo_to_catalog_dict(
        version=version,
        elements=discovery.elements,
        components=discovery.components,
    )
    out_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return out_path


def import_custom_sst_target(
    *,
    version: str,
    toolchain: ToolchainSettings,
    discovery: DiscoveredCatalog,
    selected_custom_identities: set[str],
    include_changed_baseline_components: bool = True,
    make_default: bool = False,
) -> int:
    """Import baseline plus selected custom components as a separate SST target."""

    baseline_elements, baseline_components = load_baseline_component_catalog(version)

    selected_custom_components = [
        component
        for component in discovery.custom_components
        if component_identity(component) in selected_custom_identities
    ]

    selected_identities = {component_identity(component) for component in selected_custom_components}

    merged_by_identity = {
        component_identity(component): component
        for component in baseline_components
    }

    if include_changed_baseline_components:
        for component in discovery.changed_components:
            merged_by_identity[component_identity(component)] = component

    for component in selected_custom_components:
        merged_by_identity[component_identity(component)] = component

    element_names = {
        element.name
        for element in baseline_elements
    } | {
        component.element_name
        for component in merged_by_identity.values()
    }

    discovered_elements_by_name = {
        element.name: element
        for element in discovery.elements
    }
    baseline_elements_by_name = {
        element.name: element
        for element in baseline_elements
    }

    merged_elements = []
    for name in sorted(element_names):
        merged_elements.append(
            discovered_elements_by_name.get(name)
            or baseline_elements_by_name.get(name)
            or ParsedElement(name=name)
        )

    sst_info_path = toolchain.tool_paths.get("sstInfo", "")
    sst_path = toolchain.tool_paths.get("sst", "")

    fingerprint = toolchain_fingerprint(
        version=version,
        backend=toolchain.backend,
        sst_info_path=sst_info_path,
        sst_path=sst_path,
        host=toolchain.host,
        username=toolchain.username,
        remote_setup_command=toolchain.remote_setup_command,
    )

    snapshot_path = write_toolchain_catalog_snapshot(
        version=version,
        discovery=discovery,
        fingerprint=fingerprint,
    )

    if toolchain.backend == "ssh":
        location_label = toolchain.host or "Remote"
    else:
        location_label = "Local"

    custom_count = len(selected_identities)
    changed_count = len(discovery.changed_components) if include_changed_baseline_components else 0

    label = (
        f"SST {version} — {location_label} custom "
        f"({custom_count} custom"
    )
    if changed_count:
        label += f", {changed_count} changed"
    label += ")"

    with get_connection() as conn:
        framework_version_id = get_or_create_sst_framework_version(
            conn=conn,
            version=version,
            label=label,
            source_kind="toolchain-component-catalog",
            source_path=f"toolchain:{fingerprint}",
            command=f"toolchain catalog snapshot: {snapshot_path}",
            is_default=make_default,
        )

    from fuse.plugins.community.sst.get_sstinfo import clear_sst_metadata_for_framework_version

    clear_sst_metadata_for_framework_version(framework_version_id)
    sync_parsed_sstinfo_to_database(
        framework_version_id,
        merged_elements,
        list(sorted(merged_by_identity.values(), key=lambda c: (c.element_name, int(c.is_subcomp), c.name))),
    )

    return framework_version_id
