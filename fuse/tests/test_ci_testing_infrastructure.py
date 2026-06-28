# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Tests that lock down the pytest/GitHub Actions tier contract.

These tests are intentionally dependency-light. They make CI wiring changes
visible in the fast suite so live simulator coverage is not accidentally
removed while editing workflows or pytest markers.
"""


def test_pytest_configuration_declares_all_simulator_test_tiers(repo_root):
    pytest_ini = (repo_root / "fuse" / "pytest.ini").read_text(encoding="utf-8")

    for test_path in (
        "tests",
        "plugins/community/sst/tests",
        "plugins/community/gem5/tests",
    ):
        assert test_path in pytest_ini

    for marker in ("sst_live", "sst_ext", "sst_15", "sst_16", "gem5_live"):
        assert f"{marker}:" in pytest_ini


def test_core_workflow_preserves_fast_live_and_external_sst_tiers(repo_root):
    workflow = (
        repo_root / ".github" / "workflows" / "core-tests.yml"
    ).read_text(encoding="utf-8")

    assert (
        'python -m pytest -q -m "not sst_live and not gem5_live and not sst_ext"'
        in workflow
    )
    assert "sst-live:" in workflow
    assert "sst-external-validation:" in workflow
    assert 'FUSE_ENABLE_SST_EXT_TESTS: "1"' in workflow
    assert "SST_EXT_TESTS_ROOT: /opt/sst-ext-tests" in workflow
    assert "FUSE_SST_VERSION_POLICY: major_minor_patch" in workflow
    assert '/tmp/fuse-venv/bin/python -m pytest -q -m "sst_live"' in workflow
    assert '/tmp/fuse-venv/bin/python -m pytest -q -m "sst_ext"' in workflow


def test_standalone_sst_external_workflow_matches_pytest_contract(repo_root):
    workflow = (
        repo_root / ".github" / "workflows" / "sst-external-validation.yml"
    ).read_text(encoding="utf-8")

    assert 'FUSE_ENABLE_SST_EXT_TESTS: "1"' in workflow
    assert "SST_EXT_TESTS_ROOT: /opt/sst-ext-tests" in workflow
    assert "FUSE_SST_VERSION_POLICY: major_minor_patch" in workflow
    assert "sst-info simpleElementExample" in workflow
    assert '/tmp/fuse-venv/bin/python -m pytest -q -m "sst_ext"' in workflow


def test_standalone_sst_live_workflow_matches_pytest_contract(repo_root):
    workflow = (
        repo_root / ".github" / "workflows" / "sst-integration.yml"
    ).read_text(encoding="utf-8")

    assert "FUSE_SST_VERSION:" in workflow
    assert "FUSE_SST_VERSION_POLICY: major_minor_patch" in workflow
    assert "sst-info > /tmp/sst-info.txt" in workflow
    assert '/tmp/fuse-venv/bin/python -m pytest -q -m "sst_live"' in workflow
