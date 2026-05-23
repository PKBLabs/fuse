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
import shutil
import subprocess
from pathlib import Path
import pytest


pytestmark = pytest.mark.gem5_live


def find_gem5_binary():
    env_path = os.environ.get("GEM5_BINARY")
    if env_path and Path(env_path).exists():
        return env_path

    path_binary = shutil.which("gem5")
    if path_binary:
        return path_binary

    gem5_root = os.environ.get("GEM5_ROOT")
    if gem5_root:
        candidates = [
            Path(gem5_root) / "build" / "X86" / "gem5.opt",
            Path(gem5_root) / "build" / "ALL" / "gem5.opt",
            Path(gem5_root) / "build" / "NULL" / "gem5.opt",
        ]

        for candidate in candidates:
            if candidate.exists():
                return str(candidate)

    pytest.skip("gem5 binary not found")


def test_real_gem5_binary_runs():
    gem5_binary = find_gem5_binary()

    result = subprocess.run(
        [gem5_binary, "--version"],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    assert result.returncode == 0
    assert "gem5" in (result.stdout + result.stderr).lower()