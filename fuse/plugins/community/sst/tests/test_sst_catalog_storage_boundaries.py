# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
"""Guardrails for SST-owned runtime catalog storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from fuse.plugins.community.sst import component_catalog


pytestmark = pytest.mark.sst


def test_custom_catalog_snapshots_are_plugin_local_not_core_app_data():
    custom_dir = component_catalog._CUSTOM_CATALOG_DIR.resolve()
    plugin_root = Path(component_catalog.__file__).resolve().parent
    core_app_data = plugin_root.parents[2] / "app_data"

    assert custom_dir == plugin_root / "component_catalogs" / "toolchains"
    assert plugin_root in custom_dir.parents
    assert core_app_data not in custom_dir.parents
