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
import subprocess
import sys
from pathlib import Path


def find_package_root(start: Path) -> Path:
    """
    Walk upward until we find the FUSE package root.

    The package root is the directory containing:
      app/main.py
      core/
      plugins/
    """
    current = start.resolve()

    for candidate in [current, *current.parents]:
        if (
            (candidate / "app" / "main.py").exists()
            and (candidate / "core").is_dir()
            and (candidate / "plugins").is_dir()
        ):
            return candidate

    raise RuntimeError(f"Could not find FUSE package root from {start}")


def test_app_entrypoint_launches_and_shuts_down(tmp_path):
    package_root = find_package_root(Path(__file__))
    repo_parent = package_root.parent
    main_py = package_root / "app" / "main.py"
    db_path = tmp_path / "test_app.db"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_parent)
    env["FUSE_DB_PATH"] = str(db_path)
    env["FUSE_SPLASH_MS"] = "0"
    env["FUSE_TEST_AUTOCLOSE_MS"] = "250"
    env.setdefault("QT_QPA_PLATFORM", "offscreen")

    result = subprocess.run(
        [sys.executable, str(main_py)],
        cwd=str(package_root),
        env=env,
        text=True,
        capture_output=True,
        timeout=10,
    )

    assert result.returncode == 0, (
        "FUSE failed to launch/shut down cleanly.\n\n"
        f"STDOUT:\n{result.stdout}\n\n"
        f"STDERR:\n{result.stderr}"
    )