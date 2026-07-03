# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Versioned SST runtime overlay loader.

Runtime overlays are plugin-authored metadata layered on top of raw
``sst-info`` component catalogs.  They describe SST slots and convenience
logical ports that are loaded by runtime source code but are not fully exposed
through the generated catalog metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from fuse.plugins.community.sst.policy.loader import normalize_sst_version
from fuse.plugins.community.sst.policy.runtime import framework_version_for_node


_OVERLAY_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class RuntimeSlot:
    """Runtime-loaded user subcomponent slot metadata."""

    name: str
    description: str = ""
    required_interface: str = ""
    default_type: str = ""
    required: bool = False
    inject_default: bool = False
    params: dict[str, Any] = field(default_factory=dict)
    provenance: str = ""


@dataclass(frozen=True)
class LogicalPortMapping:
    """Map a visible/logical port to a concrete nested runtime endpoint."""

    name: str
    component_path: str
    port: str
    description: str = ""
    provenance: str = ""


@dataclass(frozen=True)
class RuntimeComponentOverlay:
    """Overlay metadata for one SST element.component type."""

    component_type: str
    runtime_slots: dict[str, RuntimeSlot] = field(default_factory=dict)
    logical_ports: dict[str, LogicalPortMapping] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeOverlay:
    """Loaded runtime overlay for one SST framework version."""

    version: str = ""
    schema_version: int = 1
    description: str = ""
    components: dict[str, RuntimeComponentOverlay] = field(default_factory=dict)

    def component(self, component_type: str) -> RuntimeComponentOverlay | None:
        """Return overlay metadata for ``component_type``, if present."""

        return self.components.get(str(component_type or "").strip())


def _overlay_path(version: str) -> Path | None:
    normalized = normalize_sst_version(version)
    if not normalized:
        return None

    path = _OVERLAY_DIR / f"sst-{normalized}.json"
    return path if path.exists() else None


def available_runtime_overlay_versions() -> list[str]:
    """Return SST versions that have committed runtime overlay files."""

    versions: list[str] = []
    for path in sorted(_OVERLAY_DIR.glob("sst-*.json")):
        version = path.stem.removeprefix("sst-")
        normalized = normalize_sst_version(version)
        if normalized:
            versions.append(normalized)
    return versions


def _runtime_slot_from_dict(name: str, raw: dict[str, Any]) -> RuntimeSlot:
    params = raw.get("params", {}) or {}
    if not isinstance(params, dict):
        params = {}

    return RuntimeSlot(
        name=str(name),
        description=str(raw.get("description", "") or ""),
        required_interface=str(raw.get("required_interface", "") or ""),
        default_type=str(raw.get("default_type", "") or ""),
        required=bool(raw.get("required", False)),
        inject_default=bool(raw.get("inject_default", False)),
        params=dict(params),
        provenance=str(raw.get("provenance", "") or ""),
    )


def _logical_port_from_dict(name: str, raw: dict[str, Any]) -> LogicalPortMapping:
    return LogicalPortMapping(
        name=str(name),
        component_path=str(raw.get("component_path", "") or ""),
        port=str(raw.get("port", "") or ""),
        description=str(raw.get("description", "") or ""),
        provenance=str(raw.get("provenance", "") or ""),
    )


def _component_overlay_from_dict(component_type: str, raw: dict[str, Any]) -> RuntimeComponentOverlay:
    runtime_slots = {
        str(slot_name): _runtime_slot_from_dict(str(slot_name), slot_raw or {})
        for slot_name, slot_raw in (raw.get("runtime_slots", {}) or {}).items()
    }
    logical_ports = {
        str(port_name): _logical_port_from_dict(str(port_name), port_raw or {})
        for port_name, port_raw in (raw.get("logical_ports", {}) or {}).items()
    }

    return RuntimeComponentOverlay(
        component_type=str(component_type),
        runtime_slots=runtime_slots,
        logical_ports=logical_ports,
    )


@lru_cache(maxsize=None)
def load_runtime_overlay(version: str) -> RuntimeOverlay:
    """Load the runtime overlay for an SST version.

    Unknown or unsupported versions intentionally return an empty overlay so
    callers can layer this helper into UI and validation paths without special
    exception handling.
    """

    path = _overlay_path(version)
    if path is None:
        return RuntimeOverlay(version=normalize_sst_version(version))

    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    components = {
        str(component_type): _component_overlay_from_dict(str(component_type), component_raw or {})
        for component_type, component_raw in (raw.get("components", {}) or {}).items()
    }

    return RuntimeOverlay(
        version=normalize_sst_version(raw.get("sst_version", version)),
        schema_version=int(raw.get("schema_version", 1) or 1),
        description=str(raw.get("description", "") or ""),
        components=components,
    )


def runtime_slots_for_component(component_type: str, framework_version: str = "") -> dict[str, RuntimeSlot]:
    """Return runtime overlay slots for a component type/version."""

    component = load_runtime_overlay(framework_version).component(component_type)
    return dict(component.runtime_slots) if component is not None else {}


def logical_ports_for_component(component_type: str, framework_version: str = "") -> dict[str, LogicalPortMapping]:
    """Return logical port mappings for a component type/version."""

    component = load_runtime_overlay(framework_version).component(component_type)
    return dict(component.logical_ports) if component is not None else {}


__all__ = [
    "LogicalPortMapping",
    "RuntimeComponentOverlay",
    "RuntimeOverlay",
    "RuntimeSlot",
    "available_runtime_overlay_versions",
    "framework_version_for_node",
    "load_runtime_overlay",
    "logical_ports_for_component",
    "runtime_slots_for_component",
]
