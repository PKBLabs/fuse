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
