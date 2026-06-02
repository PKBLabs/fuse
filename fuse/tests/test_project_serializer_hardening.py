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
import json

import pytest


def _project_dict():
    return {
        "schemaVersion": "0.1.0",
        "project": {"name": "Hybrid Persistence Test"},
        "projectSettings": {
            "projectName": "Hybrid Persistence Test",
            "activePluginId": "sst",
            "plugins": {
                "sst": {"enabled": True, "targetId": "1", "frameworkVersion": "15.1.2"},
                "gem5": {"enabled": True, "targetId": "2", "frameworkVersion": "25.1.0.1"},
            },
        },
        "components": [
            {
                "id": 1,
                "pluginId": "sst",
                "targetId": "1",
                "targetLabel": "SST 15.1.2",
                "frameworkVersion": "15.1.2",
                "componentId": "memHierarchy.Cache",
                "element": "memHierarchy",
                "name": "Cache",
                "instanceName": "cache0",
                "parameters": {"cache_size": "32KiB"},
                "variablePortCounts": {"high_network": 2},
                "position": {"x": 10, "y": 20},
            },
            {
                "id": 2,
                "pluginId": "gem5",
                "targetId": "2",
                "targetLabel": "gem5 25.1.0.1",
                "frameworkVersion": "25.1.0.1",
                "componentId": "TimingSimpleCPU",
                "element": "gem5",
                "name": "TimingSimpleCPU",
                "instanceName": "cpu0",
                "parameters": {"clock": "2GHz"},
                "position": {"x": 300, "y": 20},
            },
        ],
        "links": [
            {
                "id": 1,
                "name": "cross_plugin_reference",
                "pluginId": "fuse",
                "sourceLatency": "1ns",
                "targetLatency": "2ns",
                "source": {"nodeId": 2, "componentName": "cpu0", "port": "dcache_port"},
                "target": {"nodeId": 1, "componentName": "cache0", "port": "high_network0"},
                "compatibility": {"severity": "warning", "code": "hybrid.not_exportable", "message": "Hybrid export is not supported yet."},
                "pluginMetadata": {"preserve": True},
            }
        ],
        "subcompAttachments": [],
        "editor": {
            "sceneRect": {"x": 0, "y": 0, "width": 2000, "height": 1500},
            "viewCenter": {"x": 640, "y": 480},
        },
    }


def test_save_project_file_adds_serialization_metadata_and_preserves_hybrid_model(tmp_path):
    from fuse.core.persistence.project_io import load_project_file, save_project_file

    path = tmp_path / "hybrid.fse"
    save_project_file(_project_dict(), path)

    loaded = load_project_file(path)

    assert loaded["serialization"]["format"] == "fuse.project"
    assert loaded["serialization"]["schemaVersion"] == "0.1.0"
    assert loaded["serialization"]["modelCounts"] == {
        "components": 2,
        "links": 1,
        "subcompAttachments": 0,
    }
    assert loaded["serialization"]["plugins"] == ["gem5", "sst"]
    assert {component["pluginId"] for component in loaded["components"]} == {"sst", "gem5"}
    assert loaded["links"][0]["pluginMetadata"] == {"preserve": True}
    assert loaded["editor"]["viewCenter"] == {"x": 640, "y": 480}


def test_load_project_file_rejects_dangling_link_references(tmp_path):
    from fuse.core.persistence.project_io import load_project_file

    project = _project_dict()
    project["links"][0]["target"]["nodeId"] = 999
    path = tmp_path / "dangling.fse"
    path.write_text(json.dumps(project), encoding="utf-8")

    with pytest.raises(ValueError, match="links\\[0\\]\\.target\\.nodeId.*missing component id 999"):
        load_project_file(path)


def test_load_project_file_reports_multiple_structural_errors(tmp_path):
    from fuse.core.persistence.project_io import load_project_file

    project = _project_dict()
    project["components"].append({"id": 1, "name": "Duplicate", "position": {"x": "bad", "y": 0}})
    project["links"][0]["pluginMetadata"] = []
    project["editor"]["sceneRect"]["width"] = "wide"
    path = tmp_path / "bad.fse"
    path.write_text(json.dumps(project), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        load_project_file(path)

    message = str(exc_info.value)
    assert "duplicates component id 1" in message
    assert "pluginMetadata" in message
    assert "editor.sceneRect.width" in message


def test_save_project_file_is_atomic_when_json_write_fails(tmp_path, monkeypatch):
    import fuse.core.persistence.project_io as project_io

    path = tmp_path / "atomic.fse"
    path.write_text("original contents", encoding="utf-8")

    def fail_dump(*args, **kwargs):
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr(project_io.json, "dump", fail_dump)

    with pytest.raises(RuntimeError, match="simulated write failure"):
        project_io.save_project_file(_project_dict(), path)

    assert path.read_text(encoding="utf-8") == "original contents"
    assert list(tmp_path.glob(".atomic.fse.*.tmp")) == []


def test_serializer_validation_allows_legacy_files_without_serialization_metadata():
    from fuse.core.persistence.model_serializer import validate_serialized_project

    project = _project_dict()
    project.pop("serialization", None)

    validate_serialized_project(project)
