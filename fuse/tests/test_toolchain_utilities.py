import os
import subprocess
import sys

from fuse.core.model.project_settings import ToolchainSettings
from fuse.core.toolchains.providers import (
    LocalCommandProvider,
    SSHCommandProvider,
    provider_from_toolchain,
)
from fuse.core.toolchains.version_match import compare_version_prefix, parse_version_text


def test_parse_version_text_extracts_first_numeric_version():
    parsed = parse_version_text("gem5 version 25.1.0.1 built May 2026")

    assert parsed.parts == (25, 1, 0, 1)
    assert parsed.text == "25.1.0.1"


def test_parse_version_text_returns_none_when_no_version_present():
    assert parse_version_text("not a version") is None
    assert parse_version_text("") is None


def test_compare_version_prefix_supports_all_success_policies():
    assert compare_version_prefix("15.0.0", "SST 15.1.2", "major").matched
    assert compare_version_prefix("15.1.0", "SST 15.1.2", "major_minor").matched
    assert compare_version_prefix("15.1.2", "SST 15.1.2", "major_minor_patch").matched
    assert compare_version_prefix("15.1.2", "SST 15.1.2", "exact").matched


def test_compare_version_prefix_detects_mismatch_and_missing_versions():
    mismatch = compare_version_prefix("15.1", "SST 16.0", "major_minor")
    missing = compare_version_prefix("15.1", "SST development build", "major")

    assert not mismatch.matched
    assert "not compatible" in mismatch.message
    assert not missing.matched
    assert "Could not detect" in missing.message


def test_compare_version_prefix_allows_missing_expected_version():
    result = compare_version_prefix("", "SST 16.0.0", "exact")

    assert result.matched
    assert "No expected version" in result.message


def test_compare_version_prefix_rejects_unknown_policy():
    import pytest

    with pytest.raises(ValueError, match="Unsupported version match policy"):
        compare_version_prefix("1.0", "1.0", "minor_only")


def test_local_command_provider_runs_successful_command_and_merges_env():
    result = LocalCommandProvider().run(
        [sys.executable, "-c", "import os; print(os.environ['FUSE_TEST_VALUE'])"],
        env={"FUSE_TEST_VALUE": "ok"},
    )

    assert result.return_code == 0
    assert result.stdout.strip() == "ok"
    assert result.backend == "local"


def test_local_command_provider_reports_missing_executable(monkeypatch):
    def raise_not_found(*args, **kwargs):
        raise FileNotFoundError(
            2,
            "No such file or directory",
            "definitely-not-a-real-fuse-command",
        )

    monkeypatch.setattr(subprocess, "run", raise_not_found)

    result = LocalCommandProvider().run(["definitely-not-a-real-fuse-command"])

    assert result.return_code == 127
    assert "Command not found" in result.stderr


def test_local_command_provider_reports_permission_error(monkeypatch):
    def raise_permission(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(subprocess, "run", raise_permission)

    result = LocalCommandProvider().run(["/not/executable"])

    assert result.return_code == 126
    assert "Permission denied" in result.stderr


def test_local_command_provider_reports_timeout(monkeypatch):
    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=["slow"], timeout=3, output="partial")

    monkeypatch.setattr(subprocess, "run", raise_timeout)

    result = LocalCommandProvider().run(["slow"], timeout_seconds=3)

    assert result.return_code == 124
    assert result.stdout == "partial"
    assert "timed out" in result.stderr


def test_ssh_command_provider_builds_quoted_remote_command():
    provider = SSHCommandProvider(
        host="cluster",
        username="alice",
        port=2222,
        remote_setup_command="module load sst",
    )

    remote_command = provider._build_remote_command(
        ["sst-info", "--version"],
        env={"SST_HOME": "/opt/sst 16"},
        cwd="/tmp/work dir",
    )

    assert remote_command.startswith("module load sst && cd")
    assert "env SST_HOME='/opt/sst 16' sst-info --version" in remote_command
    assert provider.remote_target() == "alice@cluster"


def test_ssh_command_provider_rejects_missing_host_without_running_subprocess():
    result = SSHCommandProvider(host="").run(["sst-info"])

    assert result.return_code == 255
    assert result.stderr == "SSH host is not configured."


def test_provider_from_toolchain_selects_ssh_or_local():
    assert isinstance(provider_from_toolchain(ToolchainSettings()), LocalCommandProvider)
    assert isinstance(
        provider_from_toolchain(ToolchainSettings(backend="ssh", host="hpc")),
        SSHCommandProvider,
    )
