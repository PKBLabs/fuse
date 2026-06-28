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

from __future__ import annotations

import os
from pathlib import Path

from fuse.plugins.community.sst.policy.build_catalog import build_policy_catalog


SUPPORTED_SST_POLICY_VERSIONS = ("15.1.2", "16.0.0")

_POLICY_DIR = Path(__file__).resolve().parent
_CATALOG_DIR = _POLICY_DIR / "catalogs"


def _source_env_name(version: str) -> str:
    normalized = version.replace(".", "_")
    return f"FUSE_SST_ELEMENTS_{normalized}_SOURCE"


def catalog_path_for_version(version: str) -> Path:
    return _CATALOG_DIR / f"sst-{version}.json"


def ensure_sst_policy_catalogs() -> None:
    """
    Ensure bundled SST policy catalogs are available.

    Normal FUSE setup uses committed catalog JSON files.

    Rebuilding catalogs requires SST-Elements source trees, so it is opt-in:

        FUSE_REBUILD_SST_POLICY_CATALOGS=1
        FUSE_SST_ELEMENTS_15_1_2_SOURCE=/path/to/sstelements-15.1.2
        FUSE_SST_ELEMENTS_16_0_0_SOURCE=/path/to/sstelements-16.0.0
    """

    _CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    rebuild = os.environ.get("FUSE_REBUILD_SST_POLICY_CATALOGS", "0") == "1"

    for version in SUPPORTED_SST_POLICY_VERSIONS:
        catalog_path = catalog_path_for_version(version)

        if catalog_path.exists() and not rebuild:
            continue

        source_env = _source_env_name(version)
        source_root = os.environ.get(source_env, "").strip()

        if not source_root:
            if not catalog_path.exists():
                print(
                    "SST policy: missing policy catalog "
                    f"{catalog_path}. Set {source_env} and "
                    "FUSE_REBUILD_SST_POLICY_CATALOGS=1 to generate it."
                )
            continue

        source_path = Path(source_root).expanduser().resolve()

        if not source_path.exists():
            print(
                f"SST policy: {source_env} points to missing path "
                f"{source_path}; skipping catalog generation for SST {version}."
            )
            continue

        print(
            f"SST policy: generating catalog for SST {version} "
            f"from {source_path}..."
        )

        build_policy_catalog(
            sst_version=version,
            source_root=source_path,
            out_path=catalog_path,
        )