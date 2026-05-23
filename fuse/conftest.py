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
import os
import sys
from pathlib import Path

import pytest


def find_package_root(start: Path) -> Path:
    current = start.resolve()

    for candidate in [current, *current.parents]:
        if (
            (candidate / "app" / "main.py").exists()
            and (candidate / "core").is_dir()
            and (candidate / "plugins").is_dir()
        ):
            return candidate

    raise RuntimeError(f"Could not find FUSE package root from {start}")


PACKAGE_ROOT = find_package_root(Path(__file__))
REPO_PARENT = PACKAGE_ROOT.parent

if str(REPO_PARENT) not in sys.path:
    sys.path.insert(0, str(REPO_PARENT))


@pytest.fixture(autouse=True)
def test_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "test_app.db"))
    monkeypatch.setenv("FUSE_SPLASH_MS", "0")
    monkeypatch.setenv("FUSE_TEST_AUTOCLOSE_MS", "100")
    monkeypatch.setenv(
        "QT_QPA_PLATFORM",
        os.environ.get("QT_QPA_PLATFORM", "offscreen"),
    )

    yield


@pytest.fixture
def package_root() -> Path:
    return PACKAGE_ROOT


@pytest.fixture
def repo_parent() -> Path:
    return REPO_PARENT