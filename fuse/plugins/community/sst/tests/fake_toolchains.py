# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Toolchain fixtures for SST tests that should not invoke real processes."""

from __future__ import annotations

from fuse.core.model.project_settings import ToolchainSettings


def local_toolchain(
    *,
    sst_info: str = "/opt/sst/bin/sst-info",
    sst: str = "/opt/sst/bin/sst",
    env: dict[str, str] | None = None,
) -> ToolchainSettings:
    return ToolchainSettings(
        backend="local",
        tool_paths={"sstInfo": sst_info, "sst": sst},
        environment=dict(env or {}),
    )


def ssh_toolchain(
    *,
    host: str = "sst.example.test",
    username: str = "fuse",
    sst_info: str = "/remote/sst/bin/sst-info",
    sst: str = "/remote/sst/bin/sst",
    setup: str = "module load sst",
) -> ToolchainSettings:
    return ToolchainSettings(
        backend="ssh",
        host=host,
        username=username,
        tool_paths={"sstInfo": sst_info, "sst": sst},
        remote_setup_command=setup,
    )


def command_result(module, *, stdout: str = "", stderr: str = "", return_code: int = 0, command=None):
    return module.CommandResult(
        command=list(command or ["sst-info"]),
        return_code=return_code,
        stdout=stdout,
        stderr=stderr,
    )
