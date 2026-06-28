# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Helpers for adaptive local SST live-test version selection.

CI sets ``FUSE_SST_VERSION`` and validates pinned SST releases strictly. Local
developer runs usually should not need to export a version; they detect the
installed ``sst-info`` version and run the compatible live-test subset.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
import shutil
import subprocess

import pytest

from fuse.core.toolchains.version_match import parse_version_text


FUSE_SST_VERSION_ENV = "FUSE_SST_VERSION"
FUSE_SST_VERSION_POLICY_ENV = "FUSE_SST_VERSION_POLICY"


@dataclass(frozen=True)
class DetectedSSTVersion:
    """Version discovered from a live ``sst-info --version`` command."""

    text: str
    raw_output: str
    sst_info_path: str

    @property
    def major(self) -> int:
        """Return the SST major version."""
        return int(self.text.split(".", 1)[0])


def require_sst_info() -> str:
    """Return the local ``sst-info`` path or skip the current live test."""
    path = shutil.which("sst-info")
    if path is None:
        pytest.skip("sst-info is not installed")
    return path


def parse_sst_version_output(output: str) -> str | None:
    """Extract the comparable SST version from command output."""
    parsed = parse_version_text(output)
    return parsed.text if parsed is not None else None


def detect_installed_sst_version(
    sst_info_path: str | None = None,
) -> DetectedSSTVersion:
    """Detect the installed SST version from ``sst-info --version``.

    A nonzero command result is a live-test environment failure. Unparseable
    output skips version-sensitive live tests because generic ``sst_live`` tests
    can still validate that the command itself runs.
    """
    path = sst_info_path or require_sst_info()
    completed = subprocess.run(
        [path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    output = (completed.stdout + "\n" + completed.stderr).strip()

    if completed.returncode != 0:
        pytest.fail(
            f"sst-info --version failed with return code {completed.returncode}.\n\n"
            f"Command: {path} --version\n\n"
            f"Output:\n{output}"
        )

    version = parse_sst_version_output(output)
    if version is None:
        pytest.skip(
            "Could not detect an SST version from "
            f"sst-info --version output:\n{output}"
        )

    return DetectedSSTVersion(
        text=version,
        raw_output=output,
        sst_info_path=path,
    )


def configured_sst_version() -> str | None:
    """Return the explicitly configured SST version, when present."""
    value = os.environ.get(FUSE_SST_VERSION_ENV)
    return value.strip() if value and value.strip() else None


def expected_sst_version() -> str:
    """Return the version live tests should validate or import locally."""
    configured = configured_sst_version()
    if configured:
        return configured

    return detect_installed_sst_version().text


def expected_sst_version_policy() -> str:
    """Return the version-match policy for live SST validation.

    CI sets ``FUSE_SST_VERSION`` and should verify the pinned release at patch
    precision by default. Local runs without an explicitly configured expected
    version compare against the detected version and therefore do not need a
    separately configured policy.
    """
    configured_policy = os.environ.get(FUSE_SST_VERSION_POLICY_ENV)
    if configured_policy and configured_policy.strip():
        return configured_policy.strip()

    if configured_sst_version():
        return "major_minor_patch"

    return "major"
