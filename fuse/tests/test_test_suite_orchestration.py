# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Core-only regression tests for standard FUSE test-suite orchestration."""

from __future__ import annotations

from pathlib import Path

from fuse.tools.run_tests import SUITES, build_pytest_args


def test_core_test_suite_is_registered():
    assert "core" in SUITES
    assert "coverage-core" in SUITES


def test_core_suite_is_core_only():
    args = build_pytest_args("core")

    assert "fuse/tests" in args
    assert "fuse/plugins/community/sst/tests" not in args
    assert "fuse/plugins/community/gem5/tests" not in args
    assert "-m" not in args


def test_core_coverage_suite_is_core_only():
    args = build_pytest_args("coverage-core")

    assert "fuse/tests" in args
    assert "fuse/plugins/community/sst/tests" not in args
    assert "fuse/plugins/community/gem5/tests" not in args
    assert "--cov=fuse.core" in args
    assert "--cov=fuse.app" in args
    assert "--cov=fuse.plugins.community.sst" not in args
    assert "--cov=fuse.plugins.community.gem5" not in args


def test_core_workflow_is_core_only(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Tier 1 / Core Tests" in text
    assert "core-tests:" in text
    assert "PYTHONPATH: ${{ github.workspace }}" in text
    assert "working-directory: fuse" not in text
    assert "python -m pytest --collect-only -q fuse/tests" in text
    assert "python -m pytest -q fuse/tests" in text
    assert "fuse/plugins/community/sst/tests" not in text
    assert "fuse/plugins/community/gem5/tests" not in text
    assert "plugin-deterministic-tests:" not in text


def test_deterministic_plugin_workflows_are_separate_files(repo_root: Path):
    workflows = repo_root / ".github" / "workflows"

    assert (workflows / "gem5-deterministic-tests.yml").exists()
    assert (workflows / "sst-deterministic-tests.yml").exists()
    assert (workflows / "sst-external-fixture-tests.yml").exists()
