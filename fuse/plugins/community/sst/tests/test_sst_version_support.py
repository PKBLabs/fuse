# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
from __future__ import annotations

import subprocess

import pytest

from fuse.plugins.community.sst.tests import sst_version_support as support


def test_parse_sst_version_output_accepts_release_and_dev_suffixes():
    assert support.parse_sst_version_output("SST-Core Version 15.1.2") == "15.1.2"
    assert support.parse_sst_version_output("sst-info 16.0.0-dev+abc123") == "16.0.0"


def test_parse_sst_version_output_returns_none_for_unversioned_output():
    assert support.parse_sst_version_output("SST development build") is None


def test_expected_sst_version_prefers_configured_env(monkeypatch):
    monkeypatch.setenv(support.FUSE_SST_VERSION_ENV, "16.0.0")

    assert support.expected_sst_version() == "16.0.0"


def test_expected_sst_version_detects_local_install_when_unconfigured(monkeypatch):
    monkeypatch.delenv(support.FUSE_SST_VERSION_ENV, raising=False)
    monkeypatch.setattr(support, "require_sst_info", lambda: "/usr/bin/sst-info")

    def fake_run(command, text, stdout, stderr, timeout, check):
        assert command == ["/usr/bin/sst-info", "--version"]
        return subprocess.CompletedProcess(command, 0, stdout="SST-Core 15.1.2", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert support.expected_sst_version() == "15.1.2"


def test_expected_sst_version_policy_is_strict_when_version_is_configured(monkeypatch):
    monkeypatch.setenv(support.FUSE_SST_VERSION_ENV, "15.1.2")
    monkeypatch.delenv(support.FUSE_SST_VERSION_POLICY_ENV, raising=False)

    assert support.expected_sst_version_policy() == "major_minor_patch"


def test_expected_sst_version_policy_is_overrideable(monkeypatch):
    monkeypatch.setenv(support.FUSE_SST_VERSION_ENV, "15.1.2")
    monkeypatch.setenv(support.FUSE_SST_VERSION_POLICY_ENV, "major_minor")

    assert support.expected_sst_version_policy() == "major_minor"


def test_expected_sst_version_policy_is_local_major_when_unconfigured(monkeypatch):
    monkeypatch.delenv(support.FUSE_SST_VERSION_ENV, raising=False)
    monkeypatch.delenv(support.FUSE_SST_VERSION_POLICY_ENV, raising=False)

    assert support.expected_sst_version_policy() == "major"


def test_detect_installed_sst_version_fails_on_nonzero_sst_info(monkeypatch):
    def fake_run(command, text, stdout, stderr, timeout, check):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(pytest.fail.Exception, match="sst-info --version failed"):
        support.detect_installed_sst_version("/usr/bin/sst-info")


def test_detect_installed_sst_version_skips_unparseable_output(monkeypatch):
    def fake_run(command, text, stdout, stderr, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout="development build", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(pytest.skip.Exception, match="Could not detect an SST version"):
        support.detect_installed_sst_version("/usr/bin/sst-info")
