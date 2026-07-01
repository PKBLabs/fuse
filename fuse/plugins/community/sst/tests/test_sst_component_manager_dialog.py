# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.sst


def _component(element_name: str, name: str, *, description: str = "", parameters=None):
    return {
        "element_name": element_name,
        "name": name,
        "description": description,
        "is_subcomp": 0,
        "parameters": list(parameters or []),
        "ports": [],
        "subcomp_slots": [],
        "statistics": [],
    }


def _component_names(dialog) -> list[str]:
    names: list[str] = []

    for top_index in range(dialog.tree.topLevelItemCount()):
        element_item = dialog.tree.topLevelItem(top_index)

        for child_index in range(element_item.childCount()):
            names.append(element_item.child(child_index).text(0))

    return names


def test_sst_component_manager_defaults_to_all_detected_components(monkeypatch):
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )

    qt_widgets = pytest.importorskip("PySide6.QtWidgets")
    from fuse.app.project_settings_dialog import SSTComponentManagerDialog
    from fuse.plugins.community.sst.component_catalog import (
        SSTComponentDiscovery,
        classify_discovered_catalog,
        component_key,
    )

    app = qt_widgets.QApplication.instance() or qt_widgets.QApplication([])

    baseline_cache = _component("core", "Cache")
    changed_baseline = _component("mem", "MemController")
    changed_discovered = _component(
        "mem",
        "MemController",
        description="Discovered metadata changed",
        parameters=[{"name": "clock", "type": "string", "default": "1GHz"}],
    )
    custom_cpu = _component("core", "CustomCPU")
    missing_router = _component("legacy", "Router")

    baseline_catalog = {
        "schema_version": "1.0.0",
        "sst_version": "16.0.0",
        "elements": [],
        "components": [baseline_cache, changed_baseline, missing_router],
    }
    discovered_catalog = {
        "schema_version": "1.0.0",
        "sst_version": "16.0.0",
        "elements": [],
        "components": [baseline_cache, changed_discovered, custom_cpu],
    }

    entries = classify_discovered_catalog(
        version="16.0.0",
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
    )
    statuses_by_key = {entry.key: entry.status for entry in entries}
    assert statuses_by_key[component_key(baseline_cache)] == "baseline"
    assert statuses_by_key[component_key(changed_baseline)] == "changed"
    assert statuses_by_key[component_key(custom_cpu)] == "custom"
    assert statuses_by_key[component_key(missing_router)] == "missing"

    discovery = SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — pytest discovery",
        source_fingerprint="pytest-fingerprint",
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        entries=entries,
        previous_enabled_keys=set(),
        command_text="sst-info",
    )

    dialog = SSTComponentManagerDialog(discovery)
    try:
        assert dialog.status_filter.currentData() == "detected"
        assert dialog.status_filter.currentText() == "All detected components"

        names = _component_names(dialog)
        assert "core.Cache" in names
        assert "core.CustomCPU" in names
        assert "mem.MemController" in names
        assert "legacy.Router" not in names

        all_index = dialog.status_filter.findData("all")
        assert all_index >= 0
        dialog.status_filter.setCurrentIndex(all_index)

        assert "legacy.Router" in _component_names(dialog)
    finally:
        dialog.close()
        app.processEvents()
