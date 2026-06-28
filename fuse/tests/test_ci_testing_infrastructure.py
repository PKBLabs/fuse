# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Core-only tests for repository-level test infrastructure.

Plugin-specific SST/gem5 test-suite assertions belong under the corresponding
plugin test directories.  This file only verifies that the core suite remains
core-only and that plugin tiers are ordered after the core tier in CI.
"""

from __future__ import annotations

from pathlib import Path

from fuse.tools.run_tests import SUITES, build_pytest_args


def test_pytest_configuration_includes_core_test_path(repo_root: Path):
    pytest_ini = (repo_root / "fuse" / "pytest.ini").read_text(encoding="utf-8")

    assert "tests" in pytest_ini


def test_core_suite_is_registered_and_core_only():
    assert "core" in SUITES
    assert "coverage-core" in SUITES

    args = build_pytest_args("core")

    assert "fuse/tests" in args
    assert "fuse/plugins/community/sst/tests" not in args
    assert "fuse/plugins/community/gem5/tests" not in args
    assert "-m" not in args


def test_core_coverage_suite_is_registered_and_core_only():
    args = build_pytest_args("coverage-core")

    assert "fuse/tests" in args
    assert "fuse/plugins/community/sst/tests" not in args
    assert "fuse/plugins/community/gem5/tests" not in args
    assert "--cov=fuse.core" in args
    assert "--cov=fuse.app" in args
    assert "--cov=fuse.plugins.community.sst" not in args
    assert "--cov=fuse.plugins.community.gem5" not in args


def test_core_workflow_runs_core_tier_before_plugin_tiers(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "core-tests:" in workflow
    assert "plugin-deterministic-tests:" in workflow
    assert "sst-external-fixture-tests:" in workflow
    assert "needs: core-tests" in workflow
    assert "needs: plugin-deterministic-tests" in workflow


def test_core_workflow_core_job_uses_only_core_test_path(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )
    core_job = workflow.split("  plugin-deterministic-tests:", 1)[0]

    assert "PYTHONPATH: ${{ github.workspace }}" in workflow
    assert "working-directory: fuse" not in workflow
    assert "python -m pytest --collect-only -q fuse/tests" in core_job
    assert "python -m pytest -q fuse/tests" in core_job
    assert "fuse/plugins/community/sst/tests" not in core_job
    assert "fuse/plugins/community/gem5/tests" not in core_job
