# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Load versioned SST export policy catalogs."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any


CATALOG_DIR = Path(__file__).resolve().parent / "catalogs"
_VERSION_RE = re.compile(r"(\d+(?:\.\d+){1,3})")


def normalize_sst_version(value: Any) -> str:
    """Extract a stable SST version string from common FUSE/metadata values."""

    text = str(value or "").strip()

    if not text:
        return ""

    match = _VERSION_RE.search(text)
    return match.group(1) if match else text


def _available_catalog_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}

    if not CATALOG_DIR.exists():
        return paths

    for path in CATALOG_DIR.glob("sst-*.json"):
        version = normalize_sst_version(path.stem.removeprefix("sst-"))
        if version:
            paths[version] = path

    return paths


def _version_sort_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(
            int(part)
            for part in normalize_sst_version(version).split(".")
            if part != ""
        )
    except ValueError:
        return (0,)


def _catalog_path_for_version(version: str | None) -> Path | None:
    version = normalize_sst_version(version)
    paths = _available_catalog_paths()

    if not paths:
        return None

    if version in paths:
        return paths[version]

    # Important:
    # If a project explicitly requested a target version, do not silently fall
    # back to another catalog. The Project Settings target catalog should mean
    # exactly that catalog.
    if version:
        return None

    # If no version was specified at all, use the newest bundled catalog as a
    # convenience fallback.
    newest_version = sorted(paths, key=_version_sort_key)[-1]
    return paths[newest_version]


def available_policy_catalog_versions() -> list[str]:
    """Return SST versions that have bundled FUSE policy catalogs."""

    return sorted(
        _available_catalog_paths(),
        key=_version_sort_key,
    )


def has_policy_catalog(version: str | None) -> bool:
    """Return true when FUSE has a bundled policy catalog for this SST version."""

    normalized = normalize_sst_version(version)

    if not normalized:
        return False

    return normalized in _available_catalog_paths()


@lru_cache(maxsize=8)
def load_policy_catalog(version: str | None = None) -> dict[str, Any]:
    """Load the best policy catalog for the requested SST version."""

    path = _catalog_path_for_version(version)

    if path is None:
        return {"schema_version": 1, "sst_version": normalize_sst_version(version), "components": {}}

    try:
        with path.open("r", encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1, "sst_version": normalize_sst_version(version), "components": {}}

    if not isinstance(data, dict):
        return {"schema_version": 1, "sst_version": normalize_sst_version(version), "components": {}}

    data.setdefault("components", {})
    return data


def component_policy(version: str | None, component_type: str) -> dict[str, Any]:
    """Return catalog policy for one SST component/subcomponent type."""

    catalog = load_policy_catalog(version)
    components = catalog.get("components", {})

    if not isinstance(components, dict):
        return {}

    policy = components.get(component_type, {})

    return policy if isinstance(policy, dict) else {}


def param_policy_override(version: str | None, component_type: str, param_name: str) -> dict[str, Any]:
    """Return catalog override data for one parameter."""

    comp_policy = component_policy(version, component_type)
    params = comp_policy.get("params", {})

    if not isinstance(params, dict):
        return {}

    override = params.get(param_name, {})
    return override if isinstance(override, dict) else {}


def _version_sort_key(version: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in normalize_sst_version(version).split("."))
    except ValueError:
        return (0,)


def available_policy_catalog_versions() -> list[str]:
    """Return SST versions that have bundled FUSE policy catalogs."""

    return sorted(
        _available_catalog_paths(),
        key=_version_sort_key,
    )


def has_policy_catalog(version: str | None) -> bool:
    """Return true when FUSE has a bundled policy catalog for this SST version."""

    normalized = normalize_sst_version(version)

    if not normalized:
        return False

    return normalized in _available_catalog_paths()