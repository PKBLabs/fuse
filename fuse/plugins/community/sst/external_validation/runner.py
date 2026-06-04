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





def run_sst_runtime_check(
    json_path: str | Path,
    *,
    sst_binary: str | None = None,
    timeout_seconds: int = 60,
    expected_return_code: int = 0,
    runtime_args: Sequence[str] = (),
    expected_stdout_fragments: Sequence[str] = (),
    expected_stderr_fragments: Sequence[str] = (),
) -> SSTExternalValidationResult:
    path = Path(json_path)

    if not path.exists():
        return SSTExternalValidationResult(
            ok=False,
            stage="sst_runtime",
            message=f"SST JSON file does not exist: {path}",
        )

    executable = sst_binary or find_executable("sst")

    if executable is None:
        return SSTExternalValidationResult(
            ok=False,
            stage="sst_runtime",
            message="sst executable was not found in PATH.",
            skipped=True,
        )

    command = [executable, *[str(arg) for arg in runtime_args], str(path)]
    result = run_command(
        command,
        stage="sst_runtime",
        timeout_seconds=timeout_seconds,
        expected_return_code=expected_return_code,
    )

    if not result.ok:
        return result

    missing_stdout = [
        fragment
        for fragment in expected_stdout_fragments
        if str(fragment) not in result.stdout
    ]
    missing_stderr = [
        fragment
        for fragment in expected_stderr_fragments
        if str(fragment) not in result.stderr
    ]

    if missing_stdout or missing_stderr:
        details: list[str] = []
        if missing_stdout:
            details.append(
                "stdout missing expected fragment(s): " + ", ".join(missing_stdout)
            )
        if missing_stderr:
            details.append(
                "stderr missing expected fragment(s): " + ", ".join(missing_stderr)
            )
        return SSTExternalValidationResult(
            ok=False,
            stage="sst_runtime",
            message="; ".join(details),
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result

def run_sst_element_availability_check(
    required_elements: Sequence[str],
    *,
    sst_info_binary: str | None = None,
    timeout_seconds: int = 30,
) -> SSTExternalValidationResult:
    """Check that required SST element libraries are visible to SST.

    Missing element libraries make a fixture ineligible on the current test
    machine, not invalid as a FUSE export. Treat those cases as skipped so
    release/CI logs distinguish environment gaps from model failures.
    """
    elements = tuple(str(element).strip() for element in required_elements if str(element).strip())

    if not elements:
        return SSTExternalValidationResult(
            ok=True,
            stage="sst_elements",
            message="No SST element-library requirements declared.",
        )

    executable = sst_info_binary or find_executable("sst-info")

    if executable is None:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_elements",
            message="sst-info executable was not found in PATH.",
        )

    missing: list[str] = []
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []
    commands: list[str] = []

    for element in elements:
        command = [executable, element]
        result = run_command(
            command,
            stage="sst_elements",
            timeout_seconds=timeout_seconds,
            expected_return_code=0,
        )
        commands.extend(result.command)
        stdout_chunks.append(result.stdout)
        stderr_chunks.append(result.stderr)

        if not result.ok:
            missing.append(element)

    if missing:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_elements",
            message=(
                "Required SST element library/libraries unavailable on this "
                f"test machine: {', '.join(missing)}."
            ),
            command=tuple(commands),
            stdout="\n".join(chunk for chunk in stdout_chunks if chunk),
            stderr="\n".join(chunk for chunk in stderr_chunks if chunk),
        )

    return SSTExternalValidationResult(
        ok=True,
        stage="sst_elements",
        message=f"Required SST element library/libraries are available: {', '.join(elements)}.",
        command=tuple(commands),
        stdout="\n".join(chunk for chunk in stdout_chunks if chunk),
        stderr="\n".join(chunk for chunk in stderr_chunks if chunk),
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

    if metadata.run_mode in {"init", "run"}:
        element_result = run_sst_element_availability_check(
            metadata.required_elements,
            timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
        )
        if metadata.required_elements:
            results.append(element_result)

        if element_result.ok and metadata.run_mode == "init":
            results.append(
                run_sst_init_check(
                    json_path,
                    sst_binary=sst_binary,
                    timeout_seconds=metadata.timeout_seconds,
                    expected_return_code=metadata.expected_return_code,
                )
            )
        elif element_result.ok:
            results.append(
                run_sst_runtime_check(
                    json_path,
                    sst_binary=sst_binary,
                    timeout_seconds=metadata.timeout_seconds,
                    expected_return_code=metadata.expected_return_code,
                    runtime_args=metadata.runtime_args,
                    expected_stdout_fragments=metadata.expected_stdout_fragments,
                    expected_stderr_fragments=metadata.expected_stderr_fragments,
                )
            )
    else:
        results.append(
            SSTExternalValidationResult(
                ok=False,
                skipped=True,
                stage="sst_runtime",
                message=(
                    f"Run mode '{metadata.run_mode}' is validated through export "
                    "and JSON syntax only."
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

    if fixture.metadata.run_mode in {"init", "run"}:
        if external_validation_enabled(environ):
            element_result = run_sst_element_availability_check(
                fixture.metadata.required_elements,
                timeout_seconds=min(max(fixture.metadata.timeout_seconds, 1), 30),
            )
            if fixture.metadata.required_elements:
                results.append(element_result)

            if element_result.ok and fixture.metadata.run_mode == "init":
                results.append(
                    run_sst_init_check(
                        output_path,
                        sst_binary=sst_binary,
                        timeout_seconds=fixture.metadata.timeout_seconds,
                        expected_return_code=fixture.metadata.expected_return_code,
                    )
                )
            elif element_result.ok:
                results.append(
                    run_sst_runtime_check(
                        output_path,
                        sst_binary=sst_binary,
                        timeout_seconds=fixture.metadata.timeout_seconds,
                        expected_return_code=fixture.metadata.expected_return_code,
                        runtime_args=fixture.metadata.runtime_args,
                        expected_stdout_fragments=fixture.metadata.expected_stdout_fragments,
                        expected_stderr_fragments=fixture.metadata.expected_stderr_fragments,
                    )
                )
        else:
            results.append(
                SSTExternalValidationResult(
                    ok=False,
                    skipped=True,
                    stage="sst_init" if fixture.metadata.run_mode == "init" else "sst_runtime",
                    message=(
                        f"Set {ENABLE_EXTERNAL_VALIDATION_ENV}=1 to run real SST "
                        f"{fixture.metadata.run_mode} checks for generated fixtures."
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
                    "through export and JSON syntax only."
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
