# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.
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


def _command_text(command: list[str]) -> str:
    try:
        return shlex.join(command)
    except Exception:
        return " ".join(str(part) for part in command)


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

        try:
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

        except FileNotFoundError as error:
            return CommandExecutionResult(
                command=command,
                return_code=127,
                stdout="",
                stderr=(
                    f"Command not found: {error.filename}\n\n"
                    f"Command attempted: {_command_text(command)}\n\n"
                    "Check that the executable is installed and available on PATH, "
                    "or configure the full executable path in Project Settings."
                ),
                backend=self.provider_id,
            )

        except PermissionError as error:
            return CommandExecutionResult(
                command=command,
                return_code=126,
                stdout="",
                stderr=(
                    f"Permission denied while trying to execute: {error.filename}\n\n"
                    f"Command attempted: {_command_text(command)}\n\n"
                    "Check that the configured path points to an executable file. "
                    "If you entered only a command name, make sure it resolves to an "
                    "executable on PATH. If it is a file, it may need execute "
                    "permission, for example: chmod +x <path>."
                ),
                backend=self.provider_id,
            )

        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")

            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")

            timeout_message = (
                f"Command timed out after {timeout_seconds} seconds.\n\n"
                f"Command attempted: {_command_text(command)}"
            )

            if stderr:
                timeout_message += f"\n\nPartial STDERR:\n{stderr}"

            return CommandExecutionResult(
                command=command,
                return_code=124,
                stdout=stdout,
                stderr=timeout_message,
                backend=self.provider_id,
            )

        except OSError as error:
            return CommandExecutionResult(
                command=command,
                return_code=1,
                stdout="",
                stderr=(
                    f"Could not execute command: {_command_text(command)}\n\n"
                    f"{type(error).__name__}: {error}"
                ),
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
                f"{shlex.quote(str(key))}={shlex.quote(str(value))}"
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

        try:
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

        except FileNotFoundError as error:
            return CommandExecutionResult(
                command=ssh_command,
                return_code=127,
                stdout="",
                stderr=(
                    f"ssh command not found: {error.filename}\n\n"
                    "Install the OpenSSH client or use the local execution backend."
                ),
                backend=self.provider_id,
                host=self.host,
            )

        except PermissionError as error:
            return CommandExecutionResult(
                command=ssh_command,
                return_code=126,
                stdout="",
                stderr=(
                    f"Permission denied while trying to execute ssh: {error.filename}\n\n"
                    f"Command attempted: {_command_text(ssh_command)}"
                ),
                backend=self.provider_id,
                host=self.host,
            )

        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""

            if isinstance(stdout, bytes):
                stdout = stdout.decode(errors="replace")

            if isinstance(stderr, bytes):
                stderr = stderr.decode(errors="replace")

            timeout_message = (
                f"SSH command timed out after {timeout_seconds} seconds "
                f"while connecting to {self.host}.\n\n"
                f"Command attempted: {_command_text(ssh_command)}"
            )

            if stderr:
                timeout_message += f"\n\nPartial STDERR:\n{stderr}"

            return CommandExecutionResult(
                command=ssh_command,
                return_code=124,
                stdout=stdout,
                stderr=timeout_message,
                backend=self.provider_id,
                host=self.host,
            )

        except OSError as error:
            return CommandExecutionResult(
                command=ssh_command,
                return_code=1,
                stdout="",
                stderr=(
                    f"Could not execute SSH command: {_command_text(ssh_command)}\n\n"
                    f"{type(error).__name__}: {error}"
                ),
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