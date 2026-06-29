# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Core tests for repository-level test infrastructure.

Plugin-specific SST/gem5 suite details belong under the corresponding plugin
unit tests. This file verifies the core suite remains core-only and that the
repository-level deterministic workflow preserves the tier dependency shape.
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


def test_deterministic_ci_uses_single_tiered_orchestrator(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Tiered Deterministic Test Suite" in workflow
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "core-tests:" in workflow
    assert "gem5-deterministic-tests:" in workflow
    assert "sst-deterministic-tests:" in workflow
    assert "sst-external-fixture-tests:" in workflow
    assert "PYTHONPATH: ${{ github.workspace }}" in workflow
    assert "working-directory: fuse" not in workflow


def test_core_job_uses_only_core_test_path(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    core_start = workflow.index("  core-tests:")
    gem5_start = workflow.index("  gem5-deterministic-tests:")
    core_job = workflow[core_start:gem5_start]

    assert "name: Tier 1 / core tests" in core_job
    assert "python -m pytest -c fuse/pytest.ini --markers" in core_job
    assert "python -m pytest -c fuse/pytest.ini --trace-config -q fuse/tests" in core_job
    assert "python -m pytest --collect-only -q fuse/tests" in core_job
    assert "python -m pytest -q fuse/tests" in core_job
    assert "fuse/plugins/community/sst/tests" not in core_job
    assert "fuse/plugins/community/gem5/tests" not in core_job


def test_tiered_workflow_preserves_job_dependencies(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "needs: core-tests" in workflow
    assert "needs:\n      - gem5-deterministic-tests\n      - sst-deterministic-tests" in workflow
    assert "workflow_run:" not in workflow


def test_deprecated_split_workflows_are_manual_only(repo_root: Path):
    workflows = repo_root / ".github" / "workflows"

    for workflow_name in (
        "gem5-deterministic-tests.yml",
        "sst-deterministic-tests.yml",
        "sst-external-fixture-tests.yml",
    ):
        text = (workflows / workflow_name).read_text(encoding="utf-8")
        assert "workflow_dispatch:" in text
        assert "workflow_run:" not in text
        assert "push:" not in text
        assert "pull_request:" not in text
        assert "Use Tiered Deterministic Test Suite" in text


def test_readme_uses_overall_workflow_and_per_tier_check_badges(repo_root: Path):
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    assert "actions/workflows/core-tests.yml/badge.svg?branch=develop&event=push" in readme
    assert "img.shields.io/github/check-runs/PKBLabs/fuse/develop" in readme
    assert "name=Tier%201%20%2F%20core%20tests" in readme
    assert "name=Tier%202%20%2F%20gem5%20deterministic%20plugin%20tests" in readme
    assert "name=Tier%202%20%2F%20SST%20deterministic%20plugin%20tests" in readme
    assert "name=Tier%203%20%2F%20SST%20external%20fixture%20tests" in readme
