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
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.gem5_live


def find_gem5_binary() -> str:
    explicit = os.environ.get("GEM5_BINARY", "").strip()

    if explicit:
        path = Path(explicit)

        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    gem5_root = os.environ.get("GEM5_ROOT", "").strip()

    if gem5_root:
        root = Path(gem5_root)

        candidates = [
            root / "build" / "X86" / "gem5.opt",
            root / "build" / "RISCV" / "gem5.opt",
            root / "build" / "ARM" / "gem5.opt",
            root / "gem5.opt",
        ]

        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                return str(candidate)

    from_path = shutil.which("gem5")

    if from_path:
        return from_path

    pytest.skip(
        "No gem5 binary found. Set GEM5_BINARY or GEM5_ROOT, or run inside a "
        "gem5-capable CI image."
    )


def test_real_gem5_binary_runs():
    gem5_binary = find_gem5_binary()

    result = subprocess.run(
        [gem5_binary, "--help"],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )

    output = result.stdout + result.stderr

    assert result.returncode == 0
    assert "gem5" in output.lower()
    assert "usage" in output.lower() or "options" in output.lower()