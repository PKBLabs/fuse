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

def test_gem5_deterministic_workflow_is_a_dedicated_tier(repo_root: Path):
    text = (
        repo_root / ".github" / "workflows" / "gem5-deterministic-tests.yml"
    ).read_text(encoding="utf-8")

    assert "name: Tier 2 / gem5 Deterministic Tests" in text
    assert "workflow_run:" in text
    assert "- Tier 1 / Core Tests" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.head_sha" in text
    assert "push:" not in text
    assert "pull_request:" not in text
    assert "gem5-deterministic-tests:" in text
    assert "PYTHONPATH: ${{ github.workspace }}" in text
    assert "working-directory: fuse" not in text
    assert "fuse/plugins/community/gem5/tests" in text
    assert "not gem5_live and not slow" in text
    assert "fuse/plugins/community/sst/tests" not in text
    assert "fuse/tests" not in text


def test_core_workflow_does_not_run_gem5_plugin_tests(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "fuse/plugins/community/gem5/tests" not in text
    assert "gem5-deterministic-tests:" not in text

