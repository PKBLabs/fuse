# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""gem5-owned regression tests for standard test-suite orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from fuse.tools.run_tests import GEM5_PLUGIN_MARKERS, SUITES, build_pytest_args


pytestmark = pytest.mark.gem5


def test_gem5_test_suites_are_registered():
    assert "gem5-fast" in SUITES


def test_gem5_fast_suite_excludes_live_and_slow_tests():
    args = build_pytest_args("gem5-fast")

    assert "fuse/plugins/community/gem5/tests" in args
    assert "fuse/tests" not in args
    assert GEM5_PLUGIN_MARKERS in args
    assert "not gem5_live" in GEM5_PLUGIN_MARKERS
    assert "not slow" in GEM5_PLUGIN_MARKERS


def test_plugin_suite_includes_gem5_without_core_tests():
    args = build_pytest_args("plugins")

    assert "fuse/tests" not in args
    assert "fuse/plugins/community/gem5/tests" in args

def test_gem5_deterministic_job_is_in_tiered_workflow(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "name: Tiered Deterministic Test Suite" in text
    assert "gem5-deterministic-tests:" in text
    assert "name: Tier 2 / gem5 deterministic plugin tests" in text
    assert "needs: core-tests" in text
    assert "PYTHONPATH: ${{ github.workspace }}" in text
    assert "working-directory: fuse" not in text
    assert "fuse/plugins/community/gem5/tests" in text
    assert "not gem5_live and not slow" in text


def test_deprecated_gem5_split_workflow_is_manual_only(repo_root: Path):
    text = (
        repo_root / ".github" / "workflows" / "gem5-deterministic-tests.yml"
    ).read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text
    assert "workflow_run:" not in text
    assert "push:" not in text
    assert "pull_request:" not in text
    assert "Use Tiered Deterministic Test Suite" in text


def test_core_job_does_not_run_gem5_plugin_tests(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )
    core_start = text.index("  core-tests:")
    gem5_start = text.index("  gem5-deterministic-tests:")
    core_job = text[core_start:gem5_start]

    assert "fuse/plugins/community/gem5/tests" not in core_job
