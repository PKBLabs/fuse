# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from pathlib import Path
import shutil


def discover_local_executable(name: str, extra_candidates: list[str] | None = None) -> str:
    path = shutil.which(name)
    if path:
        return path

    for candidate in extra_candidates or []:
        candidate_path = Path(candidate).expanduser()
        if candidate_path.exists() and candidate_path.is_file():
            return str(candidate_path)

    return ""


def discover_local_sst_info() -> str:
    return discover_local_executable(
        "sst-info",
        [
            "/opt/sst/bin/sst-info",
            "/opt/sst-15.0.0/bin/sst-info",
            "/usr/local/bin/sst-info",
        ],
    )


def discover_local_sst() -> str:
    return discover_local_executable(
        "sst",
        [
            "/opt/sst/bin/sst",
            "/opt/sst-15.0.0/bin/sst",
            "/usr/local/bin/sst",
        ],
    )
