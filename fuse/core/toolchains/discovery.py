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

from pathlib import Path
import os
import shutil


def _is_executable_file(path: Path) -> bool:
    return path.exists() and path.is_file() and os.access(path, os.X_OK)


def _expand_candidate(path: str) -> Path:
    return Path(path).expanduser().resolve()


def discover_local_executable(
    name: str,
    extra_candidates: list[str] | None = None,
) -> str:
    """
    Find a local executable.

    This first checks the current Python process PATH. If the app was launched
    from a desktop launcher or IDE, that PATH may differ from the user's shell
    PATH, so we also check common development/install locations.
    """
    path = shutil.which(name)

    if path:
        resolved = Path(path).resolve()

        if _is_executable_file(resolved):
            return str(resolved)

    for candidate in extra_candidates or []:
        candidate_path = _expand_candidate(candidate)

        if _is_executable_file(candidate_path):
            return str(candidate_path)

    return ""


def discover_local_directory(
    extra_candidates: list[str] | None = None,
) -> str:
    for candidate in extra_candidates or []:
        candidate_path = _expand_candidate(candidate)

        if candidate_path.exists() and candidate_path.is_dir():
            return str(candidate_path)

    return ""


def _sst_prefix_candidates() -> list[Path]:
    candidates: list[Path] = []

    for env_name in (
        "SST_HOME",
        "SST_ROOT",
        "SST_CORE_HOME",
        "SST_INSTALL_ROOT",
    ):
        value = os.environ.get(env_name, "").strip()

        if value:
            candidates.append(Path(value).expanduser())

    candidates.extend(
        [
            Path("~/research/sst/sst-core").expanduser(),
            Path("~/research/sst/install").expanduser(),
            Path("~/sst/sst-core").expanduser(),
            Path("~/sst/install").expanduser(),
            Path("/opt/sst"),
            Path("/opt/sst-15.1.2"),
            Path("/opt/sst-15.0.0"),
            Path("/opt/sst-16.0.0"),
            Path("/usr/local"),
        ]
    )

    return candidates


def _gem5_prefix_candidates() -> list[Path]:
    candidates: list[Path] = []

    for env_name in (
        "GEM5_ROOT",
        "GEM5_HOME",
    ):
        value = os.environ.get(env_name, "").strip()

        if value:
            candidates.append(Path(value).expanduser())

    candidates.extend(
        [
            Path("~/research/gem5").expanduser(),
            Path("~/gem5").expanduser(),
            Path("/opt/gem5"),
            Path("/opt/gem5-v25.1.0.1"),
            Path("/opt/gem5-v24.1.0.3"),
        ]
    )

    return candidates


def discover_local_sst_info() -> str:
    candidates: list[str] = []

    for prefix in _sst_prefix_candidates():
        candidates.extend(
            [
                str(prefix / "bin" / "sst-info"),
                str(prefix / "sst-core" / "bin" / "sst-info"),
                str(prefix / "build" / "sst-info"),
            ]
        )

    candidates.extend(
        [
            "/usr/local/bin/sst-info",
            "/usr/bin/sst-info",
        ]
    )

    return discover_local_executable("sst-info", candidates)


def discover_local_sst() -> str:
    candidates: list[str] = []

    for prefix in _sst_prefix_candidates():
        candidates.extend(
            [
                str(prefix / "bin" / "sst"),
                str(prefix / "sst-core" / "bin" / "sst"),
                str(prefix / "build" / "sst"),
            ]
        )

    candidates.extend(
        [
            "/usr/local/bin/sst",
            "/usr/bin/sst",
        ]
    )

    return discover_local_executable("sst", candidates)


def discover_local_gem5_root() -> str:
    return discover_local_directory(
        [str(path) for path in _gem5_prefix_candidates()]
    )


def discover_local_gem5_binary() -> str:
    candidates: list[str] = []

    for prefix in _gem5_prefix_candidates():
        candidates.extend(
            [
                str(prefix / "build" / "X86" / "gem5.opt"),
                str(prefix / "build" / "X86" / "gem5.fast"),
                str(prefix / "build" / "X86" / "gem5.debug"),
                str(prefix / "build" / "ARM" / "gem5.opt"),
                str(prefix / "build" / "RISCV" / "gem5.opt"),
                str(prefix / "gem5.opt"),
            ]
        )

    candidates.extend(
        [
            "/usr/local/bin/gem5",
            "/usr/bin/gem5",
        ]
    )

    return discover_local_executable("gem5", candidates)