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


def test_save_and_load_project_file_round_trip(tmp_path):
    from fuse.core.persistence.project_io import load_project_file, save_project_file

    project = {
        "schemaVersion": "0.1.0",
        "project": {
            "name": "Test Project",
            "updatedAt": "2026-01-01T00:00:00+00:00",
        },
        "view": {},
        "components": [],
        "links": [],
    }

    path = tmp_path / "test_project.fse"

    save_project_file(project, path)
    loaded = load_project_file(path)

    assert loaded["project"]["name"] == "Test Project"
    assert loaded["components"] == []
    assert loaded["links"] == []


def test_load_project_file_rejects_unsupported_schema(tmp_path):
    from fuse.core.persistence.project_io import load_project_file

    project = {
        "schemaVersion": "999.0.0",
        "project": {"name": "Bad Schema"},
        "components": [],
        "links": [],
    }

    path = tmp_path / "bad_schema.fse"
    path.write_text(json.dumps(project), encoding="utf-8")

    with pytest.raises(ValueError, match="Unsupported project schemaVersion"):
        load_project_file(path)


def test_load_project_file_rejects_missing_components(tmp_path):
    from fuse.core.persistence.project_io import load_project_file

    project = {
        "schemaVersion": "0.1.0",
        "project": {"name": "Missing Components"},
        "links": [],
    }

    path = tmp_path / "missing_components.fse"
    path.write_text(json.dumps(project), encoding="utf-8")

    with pytest.raises(ValueError, match="missing components list"):
        load_project_file(path)


def test_load_project_file_rejects_missing_links(tmp_path):
    from fuse.core.persistence.project_io import load_project_file

    project = {
        "schemaVersion": "0.1.0",
        "project": {"name": "Missing Links"},
        "components": [],
    }

    path = tmp_path / "missing_links.fse"
    path.write_text(json.dumps(project), encoding="utf-8")

    with pytest.raises(ValueError, match="missing links list"):
        load_project_file(path)