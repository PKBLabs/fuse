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
import json
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
class SSTFixtureAcceptanceResult:
    """Structured backend acceptance result for one generated SST fixture."""

    metadata: SSTExternalValidationMetadata
    output_path: Path
    export_can_export: bool
    expected_top_level_sections_present: bool
    results: tuple[SSTExternalValidationResult, ...]

    @property
    def ok(self) -> bool:
        return (
            self.export_can_export
            and self.expected_top_level_sections_present
            and all(result.ok or result.skipped for result in self.results)
        )

    @property
    def failed_results(self) -> tuple[SSTExternalValidationResult, ...]:
        return tuple(result for result in self.results if result.failed)


def successful_stage_result(stage: str, message: str) -> SSTExternalValidationResult:
    return SSTExternalValidationResult(ok=True, stage=stage, message=message)


def failed_stage_result(stage: str, message: str) -> SSTExternalValidationResult:
    return SSTExternalValidationResult(ok=False, stage=stage, message=message)


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


def run_generated_fixture_acceptance(
    fixture,
    output_dir: str | Path,
    *,
    environ: dict[str, str] | None = None,
    sst_binary: str | None = None,
) -> SSTFixtureAcceptanceResult:
    """Export and validate one SST plugin-owned generated acceptance fixture.

    Phase 2 always runs the FUSE export-readiness check, real SST JSON export,
    and JSON syntax validation. Real SST init is still gated by
    FUSE_ENABLE_SST_EXT_TESTS so normal unit tests remain lightweight.
    """
    from fuse.plugins.community.sst.export_json import (
        export_sst_json,
        validate_sst_json_export,
    )

    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / fixture.output_filename

    results: list[SSTExternalValidationResult] = []
    report = validate_sst_json_export(fixture.scene)

    if report.can_export:
        results.append(
            successful_stage_result(
                "export_validation",
                "SST export validation completed successfully.",
            )
        )
    else:
        messages = "; ".join(str(getattr(issue, "message", issue)) for issue in report.errors)
        results.append(
            failed_stage_result(
                "export_validation",
                f"SST export validation failed: {messages}",
            )
        )
        return SSTFixtureAcceptanceResult(
            metadata=fixture.metadata,
            output_path=output_path,
            export_can_export=False,
            expected_top_level_sections_present=False,
            results=tuple(results),
        )

    export_sst_json(fixture.scene, output_path)
    results.append(
        successful_stage_result(
            "export_json",
            f"Exported generated SST fixture to {output_path}.",
        )
    )

    json_result = run_json_syntax_check(
        output_path,
        timeout_seconds=min(max(fixture.metadata.timeout_seconds, 1), 30),
    )
    results.append(json_result)

    expected_sections_present = False
    if json_result.ok:
        data = json.loads(output_path.read_text(encoding="utf-8"))
        expected_sections = tuple(getattr(fixture, "expected_top_level_sections", ()) or ())
        expected_sections_present = all(section in data for section in expected_sections)
        if expected_sections_present:
            results.append(
                successful_stage_result(
                    "sst_json_contract",
                    "Exported SST JSON contains expected top-level sections.",
                )
            )
        else:
            missing = [section for section in expected_sections if section not in data]
            results.append(
                failed_stage_result(
                    "sst_json_contract",
                    f"Exported SST JSON is missing top-level section(s): {', '.join(missing)}.",
                )
            )

    if fixture.metadata.run_mode == "init":
        if external_validation_enabled(environ):
            results.append(
                run_sst_init_check(
                    output_path,
                    sst_binary=sst_binary,
                    timeout_seconds=fixture.metadata.timeout_seconds,
                    expected_return_code=fixture.metadata.expected_return_code,
                )
            )
        else:
            results.append(
                SSTExternalValidationResult(
                    ok=False,
                    skipped=True,
                    stage="sst_init",
                    message=(
                        f"Set {ENABLE_EXTERNAL_VALIDATION_ENV}=1 to run real SST "
                        "init checks for generated fixtures."
                    ),
                )
            )
    else:
        results.append(
            SSTExternalValidationResult(
                ok=False,
                skipped=True,
                stage="sst_runtime",
                message=(
                    f"Fixture run mode '{fixture.metadata.run_mode}' is validated "
                    "through export and JSON syntax only in this phase."
                ),
            )
        )

    return SSTFixtureAcceptanceResult(
        metadata=fixture.metadata,
        output_path=output_path,
        export_can_export=report.can_export,
        expected_top_level_sections_present=expected_sections_present,
        results=tuple(results),
    )
