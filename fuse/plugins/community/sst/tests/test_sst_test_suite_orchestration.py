# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""SST-owned regression tests for standard test-suite orchestration."""

from __future__ import annotations

from pathlib import Path

import pytest

from fuse.tools.run_tests import (
    FAST_MARKERS,
    SST_EXTERNAL_FIXTURE_MARKERS,
    SST_PLUGIN_MARKERS,
    SUITES,
    build_pytest_args,
)


pytestmark = pytest.mark.sst


def test_sst_test_suites_are_registered():
    assert {
        "sst-fast",
        "sst-external-fixtures",
        "sst-full",
        "sst-live",
        "sst-live-15",
        "sst-live-16",
        "sst-external-live",
        "sst-remote",
        "coverage-sst",
    }.issubset(SUITES)


def test_sst_fast_suite_excludes_live_external_remote_and_slow_tests():
    args = build_pytest_args("sst-fast")

    assert "fuse/plugins/community/sst/tests" in args
    assert "fuse/tests" not in args
    assert SST_PLUGIN_MARKERS in args

    for marker in ("sst_live", "sst_remote", "sst_ext", "sst_external", "slow"):
        assert f"not {marker}" in SST_PLUGIN_MARKERS


def test_sst_external_fixture_suite_is_a_distinct_deterministic_tier():
    args = build_pytest_args("sst-external-fixtures")

    assert "fuse/plugins/community/sst/tests" in args
    assert "fuse/tests" not in args
    assert SST_EXTERNAL_FIXTURE_MARKERS in args
    assert "sst_external" in SST_EXTERNAL_FIXTURE_MARKERS
    assert "not sst_live" in SST_EXTERNAL_FIXTURE_MARKERS
    assert "not sst_ext" in SST_EXTERNAL_FIXTURE_MARKERS


def test_sst_live_version_specific_suites_use_sst_version_markers():
    assert "sst_live" in build_pytest_args("sst-live")
    assert "sst_live and sst_15" in build_pytest_args("sst-live-15")
    assert "sst_live and sst_16" in build_pytest_args("sst-live-16")


def test_sst_external_live_and_remote_are_manual_tiers():
    assert "sst_ext" in build_pytest_args("sst-external-live")
    assert "sst_remote" in build_pytest_args("sst-remote")


def test_fast_suite_includes_sst_deterministic_tests_but_excludes_live_external_live_and_remote():
    args = build_pytest_args("fast")

    assert "fuse/plugins/community/sst/tests" in args
    assert FAST_MARKERS in args
    assert "not sst_ext" in FAST_MARKERS
    assert "not sst_live" in FAST_MARKERS
    assert "not sst_remote" in FAST_MARKERS


def test_coverage_sst_suite_is_sst_plugin_only():
    args = build_pytest_args("coverage-sst")

    assert "fuse/plugins/community/sst/tests" in args
    assert "fuse/tests" not in args
    assert "--cov=fuse.plugins.community.sst" in args
    assert "--cov=fuse.core" not in args
    assert "--cov=fuse.app" not in args


def test_makefile_exposes_sst_tiered_test_targets(repo_root: Path):
    text = (repo_root / "Makefile").read_text(encoding="utf-8")

    for target in (
        "test-sst-fast:",
        "test-sst-external-fixtures:",
        "test-sst-live:",
        "test-sst-live-15:",
        "test-sst-live-16:",
        "test-sst-external-live:",
        "test-sst-remote:",
        "test-coverage-sst:",
    ):
        assert target in text


def test_core_workflow_runs_sst_fixture_tier_after_plugin_deterministic_tests(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "sst-external-fixture-tests:" in text
    assert "needs: plugin-deterministic-tests" in text
    assert "plugins/community/sst/tests" in text
    assert "sst_external and not sst_live and not sst_remote and not sst_ext and not slow" in text


def test_core_workflow_does_not_run_live_sst_or_live_external_jobs(repo_root: Path):
    text = (repo_root / ".github" / "workflows" / "core-tests.yml").read_text(
        encoding="utf-8"
    )

    assert "sst-live:" not in text
    assert "sst-external-validation:" not in text
    assert 'pytest -q -m "sst_live"' not in text
    assert 'pytest -q -m "sst_ext"' not in text
