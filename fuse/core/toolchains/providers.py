# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol
import os
import shlex
import subprocess

from fuse.core.model.project_settings import ToolchainSettings


@dataclass
class CommandExecutionResult:
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    backend: str = "local"
    host: str = ""


class CommandProvider(Protocol):
    provider_id: str

    def run(
        self,
        command: list[str],
        timeout_seconds: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandExecutionResult:
        ...


@dataclass
class LocalCommandProvider:
    provider_id: str = "local"

    def run(
        self,
        command: list[str],
        timeout_seconds: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandExecutionResult:
        merged_env = os.environ.copy()
        if env:
            merged_env.update(env)

        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
            cwd=cwd,
            env=merged_env,
        )

        return CommandExecutionResult(
            command=command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            backend=self.provider_id,
        )


@dataclass
class SSHCommandProvider:
    host: str
    username: str = ""
    port: int = 22
    remote_setup_command: str = ""
    ssh_options: list[str] = field(default_factory=list)
    provider_id: str = "ssh"

    def remote_target(self) -> str:
        if self.username:
            return f"{self.username}@{self.host}"
        return self.host

    def _build_remote_command(
        self,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> str:
        parts: list[str] = []

        if self.remote_setup_command.strip():
            parts.append(self.remote_setup_command.strip())

        if cwd:
            parts.append(f"cd {shlex.quote(cwd)}")

        env_prefix = ""
        if env:
            env_prefix = " ".join(
                f"{shlex.quote(key)}={shlex.quote(value)}"
                for key, value in env.items()
            )

        command_text = shlex.join(command)
        if env_prefix:
            command_text = f"env {env_prefix} {command_text}"

        parts.append(command_text)
        return " && ".join(parts)

    def run(
        self,
        command: list[str],
        timeout_seconds: int = 60,
        env: dict[str, str] | None = None,
        cwd: str | None = None,
    ) -> CommandExecutionResult:
        if not self.host:
            return CommandExecutionResult(
                command=command,
                return_code=255,
                stdout="",
                stderr="SSH host is not configured.",
                backend=self.provider_id,
                host=self.host,
            )

        remote_command = self._build_remote_command(command, env=env, cwd=cwd)

        ssh_command = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-p",
            str(self.port or 22),
            *self.ssh_options,
            self.remote_target(),
            remote_command,
        ]

        completed = subprocess.run(
            ssh_command,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )

        return CommandExecutionResult(
            command=ssh_command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            backend=self.provider_id,
            host=self.host,
        )


def provider_from_toolchain(settings: ToolchainSettings) -> CommandProvider:
    if settings.backend == "ssh":
        return SSHCommandProvider(
            host=settings.host,
            username=settings.username,
            port=settings.port,
            remote_setup_command=settings.remote_setup_command,
        )

    return LocalCommandProvider()
