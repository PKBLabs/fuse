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
plugin test directories. This file verifies that the core workflow remains
core-only and that deterministic plugin tiers live in separate workflow files so
README badges can report tier status independently.
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


def test_deterministic_ci_tiers_have_separate_workflow_files(repo_root: Path):
    workflows = repo_root / ".github" / "workflows"

    assert (workflows / "core-tests.yml").exists()
    assert (workflows / "gem5-deterministic-tests.yml").exists()
    assert (workflows / "sst-deterministic-tests.yml").exists()
    assert (workflows / "sst-external-fixture-tests.yml").exists()


def test_core_workflow_core_job_uses_only_core_test_path(repo_root: Path):
    workflow = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Tier 1 / Core Tests" in workflow
    assert "core-tests:" in workflow
    assert "PYTHONPATH: ${{ github.workspace }}" in workflow
    assert "working-directory: fuse" not in workflow
    assert "python -m pytest --collect-only -q fuse/tests" in workflow
    assert "python -m pytest -q fuse/tests" in workflow
    assert "fuse/plugins/community/sst/tests" not in workflow
    assert "fuse/plugins/community/gem5/tests" not in workflow
    assert "plugin-deterministic-tests:" not in workflow
    assert "sst-external-fixture-tests:" not in workflow


def test_readme_uses_independent_deterministic_workflow_badges(repo_root: Path):
    readme = (repo_root / "README.md").read_text(encoding="utf-8")

    badge_events = {
        "core-tests.yml": "push",
        "gem5-deterministic-tests.yml": "workflow_run",
        "sst-deterministic-tests.yml": "workflow_run",
        "sst-external-fixture-tests.yml": "workflow_run",
    }

    for workflow_name, event_name in badge_events.items():
        badge = (
            f"actions/workflows/{workflow_name}/badge.svg?"
            f"branch=develop&event={event_name}"
        )
        link = f"actions/workflows/{workflow_name}"
        assert badge in readme
        assert link in readme


def test_deterministic_plugin_workflows_are_chained_after_core(repo_root: Path):
    workflows = repo_root / ".github" / "workflows"

    for workflow_name in (
        "gem5-deterministic-tests.yml",
        "sst-deterministic-tests.yml",
    ):
        text = (workflows / workflow_name).read_text(encoding="utf-8")
        assert "workflow_run:" in text
        assert "- Tier 1 / Core Tests" in text
        assert "github.event.workflow_run.conclusion == 'success'" in text
        assert "github.event.workflow_run.head_sha" in text
        assert "push:" not in text
        assert "pull_request:" not in text

    text = (workflows / "sst-external-fixture-tests.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_run:" in text
    assert "- Tier 2 / SST Deterministic Tests" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.head_sha" in text
    assert "push:" not in text
    assert "pull_request:" not in text
