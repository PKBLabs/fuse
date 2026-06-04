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

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Sequence

from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)


ENABLE_EXTERNAL_VALIDATION_ENV = "FUSE_ENABLE_SST_EXT_TESTS"


@dataclass(frozen=True)
class SSTExternalValidationResult:
    """Result from one stage of backend SST external validation."""

    ok: bool
    stage: str
    message: str
    skipped: bool = False
    command: tuple[str, ...] = field(default_factory=tuple)
    return_code: int | None = None
    stdout: str = ""
    stderr: str = ""

    @property
    def failed(self) -> bool:
        return not self.ok and not self.skipped


def external_validation_enabled(environ: dict[str, str] | None = None) -> bool:
    values = environ if environ is not None else os.environ
    value = str(values.get(ENABLE_EXTERNAL_VALIDATION_ENV, "")).strip().lower()

    return value in {"1", "true", "yes", "on"}


def find_executable(name: str) -> str | None:
    return shutil.which(name)


def run_command(
    command: Sequence[str],
    *,
    stage: str,
    timeout_seconds: int,
    expected_return_code: int = 0,
) -> SSTExternalValidationResult:
    try:
        completed = subprocess.run(
            list(command),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return SSTExternalValidationResult(
            ok=False,
            stage=stage,
            message=f"{stage} timed out after {timeout_seconds} second(s).",
            command=tuple(str(item) for item in command),
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
        )

    ok = completed.returncode == expected_return_code
    message = f"{stage} completed successfully."

    if not ok:
        message = (
            f"{stage} returned {completed.returncode}; "
            f"expected {expected_return_code}."
        )

    return SSTExternalValidationResult(
        ok=ok,
        stage=stage,
        message=message,
        command=tuple(str(item) for item in command),
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def run_json_syntax_check(
    json_path: str | Path,
    *,
    python_executable: str | None = None,
    timeout_seconds: int = 30,
) -> SSTExternalValidationResult:
    path = Path(json_path)

    if not path.exists():
        return SSTExternalValidationResult(
            ok=False,
            stage="json_syntax",
            message=f"SST JSON file does not exist: {path}",
        )

    executable = python_executable or sys.executable

    return run_command(
        [executable, "-m", "json.tool", str(path)],
        stage="json_syntax",
        timeout_seconds=timeout_seconds,
    )


def run_sst_init_check(
    json_path: str | Path,
    *,
    sst_binary: str | None = None,
    timeout_seconds: int = 60,
    expected_return_code: int = 0,
) -> SSTExternalValidationResult:
    path = Path(json_path)

    if not path.exists():
        return SSTExternalValidationResult(
            ok=False,
            stage="sst_init",
            message=f"SST JSON file does not exist: {path}",
        )

    executable = sst_binary or find_executable("sst")

    if executable is None:
        return SSTExternalValidationResult(
            ok=False,
            stage="sst_init",
            message="sst executable was not found in PATH.",
            skipped=True,
        )

    return run_command(
        [executable, "--run-mode=init", str(path)],
        stage="sst_init",
        timeout_seconds=timeout_seconds,
        expected_return_code=expected_return_code,
    )


def run_sst_external_acceptance(
    json_path: str | Path,
    metadata: SSTExternalValidationMetadata,
    *,
    require_enabled: bool = True,
    sst_binary: str | None = None,
    environ: dict[str, str] | None = None,
) -> list[SSTExternalValidationResult]:
    """Run the phase-1 backend acceptance ladder for exported SST JSON.

    This is intentionally plugin-owned and backend-only. It does not drive any
    user-facing validation UI.
    """
    if require_enabled and not external_validation_enabled(environ):
        return [
            SSTExternalValidationResult(
                ok=False,
                skipped=True,
                stage="enabled",
                message=(
                    f"Set {ENABLE_EXTERNAL_VALIDATION_ENV}=1 to run SST "
                    "external validation checks."
                ),
            )
        ]

    json_result = run_json_syntax_check(
        json_path,
        timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
    )

    results = [json_result]

    if not json_result.ok:
        return results

    if metadata.run_mode == "init":
        results.append(
            run_sst_init_check(
                json_path,
                sst_binary=sst_binary,
                timeout_seconds=metadata.timeout_seconds,
                expected_return_code=metadata.expected_return_code,
            )
        )
    else:
        results.append(
            SSTExternalValidationResult(
                ok=False,
                skipped=True,
                stage="sst_runtime",
                message=(
                    f"Run mode '{metadata.run_mode}' is reserved for a later "
                    "runtime acceptance phase."
                ),
            )
        )

    return results
