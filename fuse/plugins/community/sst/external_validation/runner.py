# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Optional backend runner for SST external validation fixtures.

This module exports generated SST JSON fixtures and, when explicitly enabled,
checks them against a real SST command-line installation and/or the external
``sst-ext-tests`` suite. All execution is opt-in through environment variables
so normal unit tests remain fast and do not require SST to be installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Sequence

from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)


ENABLE_EXTERNAL_VALIDATION_ENV = "FUSE_ENABLE_SST_EXT_TESTS"
SST_EXT_TESTS_ROOT_ENV = "SST_EXT_TESTS_ROOT"


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
        """Return true when this stage failed instead of passing or skipping."""
        return not self.ok and not self.skipped


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
        """Return true when export and all enabled validation stages succeeded."""
        return (
            self.export_can_export
            and self.expected_top_level_sections_present
            and all(result.ok or result.skipped for result in self.results)
        )

    @property
    def failed_results(self) -> tuple[SSTExternalValidationResult, ...]:
        """Return only failing validation stages for this fixture."""
        return tuple(result for result in self.results if result.failed)


@dataclass(frozen=True)
class SSTExternalValidationSuiteReport:
    """Developer-facing summary for a group of SST backend fixtures."""

    results: tuple[SSTFixtureAcceptanceResult, ...]

    @property
    def passed(self) -> tuple[SSTFixtureAcceptanceResult, ...]:
        """Return fixtures that passed all required checks."""
        return tuple(result for result in self.results if result.ok)

    @property
    def failed(self) -> tuple[SSTFixtureAcceptanceResult, ...]:
        """Return fixtures with at least one failing validation stage."""
        return tuple(result for result in self.results if result.failed_results)

    @property
    def skipped(self) -> tuple[SSTFixtureAcceptanceResult, ...]:
        """Return fixtures for which all runtime validation stages were skipped."""
        return tuple(
            result
            for result in self.results
            if result.results and all(stage.skipped for stage in result.results)
        )

    def to_mapping(self) -> dict[str, object]:
        """Serialize the suite report to a JSON-compatible summary mapping."""
        return {
            "total": len(self.results),
            "passed": len(self.passed),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
            "fixtures": [
                {
                    "name": result.metadata.name,
                    "ok": result.ok,
                    "output_path": str(result.output_path),
                    "stages": [
                        {
                            "stage": stage.stage,
                            "ok": stage.ok,
                            "skipped": stage.skipped,
                            "message": stage.message,
                        }
                        for stage in result.results
                    ],
                }
                for result in self.results
            ],
        }


def successful_stage_result(stage: str, message: str) -> SSTExternalValidationResult:
    """Create a successful external-validation stage result."""
    return SSTExternalValidationResult(ok=True, stage=stage, message=message)


def failed_stage_result(stage: str, message: str) -> SSTExternalValidationResult:
    """Create a failed external-validation stage result."""
    return SSTExternalValidationResult(ok=False, stage=stage, message=message)


def skipped_stage_result(stage: str, message: str) -> SSTExternalValidationResult:
    """Create a skipped external-validation stage result."""
    return SSTExternalValidationResult(ok=False, skipped=True, stage=stage, message=message)


def external_validation_enabled(environ: dict[str, str] | None = None) -> bool:
    """Return whether optional SST external validation has been enabled."""
    values = environ if environ is not None else os.environ
    value = str(values.get(ENABLE_EXTERNAL_VALIDATION_ENV, "")).strip().lower()

    return value in {"1", "true", "yes", "on"}


def external_suite_root(environ: dict[str, str] | None = None) -> Path | None:
    """Return the configured ``sst-ext-tests`` root directory, if any."""
    values = environ if environ is not None else os.environ
    value = str(values.get(SST_EXT_TESTS_ROOT_ENV, "")).strip()

    if not value:
        return None

    return Path(value).expanduser()


def external_suite_root_validation_requested(
    environ: dict[str, str] | None = None,
) -> bool:
    """Return true when a configured sst-ext-tests root should be validated."""
    return external_suite_root(environ) is not None


def validate_external_suite_root(
    environ: dict[str, str] | None = None,
) -> SSTExternalValidationResult:
    """Validate that the optional external suite root exists and is usable."""
    root = external_suite_root(environ)

    if root is None:
        return skipped_stage_result(
            "sst_ext_tests_root",
            f"{SST_EXT_TESTS_ROOT_ENV} is not set; optional sst-ext-tests interoperability is disabled.",
        )
    if not root.exists():
        return failed_stage_result(
            "sst_ext_tests_root",
            f"{SST_EXT_TESTS_ROOT_ENV} does not exist: {root}",
        )
    if not root.is_dir():
        return failed_stage_result(
            "sst_ext_tests_root",
            f"{SST_EXT_TESTS_ROOT_ENV} is not a directory: {root}",
        )

    return successful_stage_result(
        "sst_ext_tests_root",
        f"Optional sst-ext-tests root is available: {root}",
    )


def find_executable(name: str) -> str | None:
    """Return the executable path for ``name`` from ``PATH`` when present."""
    return shutil.which(name)


def parse_version_tuple(value: str) -> tuple[int, ...]:
    """Extract comparable numeric version components from free-form text."""
    match = re.search(r"(\d+(?:\.\d+){0,3})", value)
    if match is None:
        return ()
    return tuple(int(part) for part in match.group(1).split("."))


def compare_versions(left: str, right: str) -> int:
    """Compare two version strings using their numeric components."""
    left_parts = parse_version_tuple(left)
    right_parts = parse_version_tuple(right)
    width = max(len(left_parts), len(right_parts))
    left_padded = left_parts + (0,) * (width - len(left_parts))
    right_padded = right_parts + (0,) * (width - len(right_parts))

    if left_padded < right_padded:
        return -1
    if left_padded > right_padded:
        return 1
    return 0


def run_command(
    command: Sequence[str],
    *,
    stage: str,
    timeout_seconds: int,
    expected_return_code: int = 0,
) -> SSTExternalValidationResult:
    """Run an external command and wrap its result for validation reporting."""
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
    """Validate that a generated SST JSON file is syntactically valid JSON."""
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


def run_metadata_validation_check(
    metadata: SSTExternalValidationMetadata,
) -> SSTExternalValidationResult:
    """Validate fixture metadata before runtime checks are attempted."""
    errors = metadata.validation_errors()

    if errors:
        return failed_stage_result(
            "fixture_metadata",
            "Fixture metadata is invalid: " + "; ".join(errors),
        )

    return successful_stage_result(
        "fixture_metadata",
        f"Fixture metadata is valid for {metadata.name}.",
    )


def run_sst_version_check(
    metadata: SSTExternalValidationMetadata,
    *,
    sst_binary: str | None = None,
    timeout_seconds: int = 30,
) -> SSTExternalValidationResult:
    """Check the installed SST version against fixture metadata constraints."""
    if not metadata.min_sst_version and not metadata.max_sst_version:
        return skipped_stage_result(
            "sst_version",
            "Fixture does not declare SST version bounds.",
        )

    executable = sst_binary or find_executable("sst")

    if executable is None:
        return skipped_stage_result("sst_version", "sst executable was not found in PATH.")

    result = run_command(
        [executable, "--version"],
        stage="sst_version",
        timeout_seconds=timeout_seconds,
    )

    if not result.ok:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_version",
            message="Could not determine SST version with 'sst --version'.",
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    version_text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    installed_version = ".".join(str(part) for part in parse_version_tuple(version_text))

    if not installed_version:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_version",
            message="Could not parse an SST version from 'sst --version' output.",
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    if metadata.min_sst_version and compare_versions(installed_version, metadata.min_sst_version) < 0:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_version",
            message=(
                f"Installed SST {installed_version} is older than fixture minimum "
                f"{metadata.min_sst_version}."
            ),
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    if metadata.max_sst_version and compare_versions(installed_version, metadata.max_sst_version) > 0:
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_version",
            message=(
                f"Installed SST {installed_version} is newer than fixture maximum "
                f"{metadata.max_sst_version}."
            ),
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return SSTExternalValidationResult(
        ok=True,
        stage="sst_version",
        message=f"Installed SST {installed_version} satisfies fixture version bounds.",
        command=result.command,
        return_code=result.return_code,
        stdout=result.stdout,
        stderr=result.stderr,
    )


def run_sst_init_check(
    json_path: str | Path,
    *,
    sst_binary: str | None = None,
    timeout_seconds: int = 60,
    expected_return_code: int = 0,
) -> SSTExternalValidationResult:
    """Run SST initialization validation for a generated fixture."""
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
    """Run a generated fixture under SST and validate expected output fragments."""
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
            details.append(f"stdout missing: {', '.join(missing_stdout)}")
        if missing_stderr:
            details.append(f"stderr missing: {', '.join(missing_stderr)}")

        return SSTExternalValidationResult(
            ok=False,
            stage="sst_runtime",
            message="Runtime output did not match expectations: " + "; ".join(details),
            command=result.command,
            return_code=result.return_code,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    return result


def run_expected_output_file_check(
    output_dir: str | Path,
    metadata: SSTExternalValidationMetadata,
) -> SSTExternalValidationResult:
    """Check that runtime validation produced the files declared by metadata."""
    if not metadata.expected_output_files:
        return skipped_stage_result(
            "expected_files",
            "Fixture does not declare expected output files.",
        )

    root = Path(output_dir)
    missing = [name for name in metadata.expected_output_files if not (root / name).exists()]

    if missing:
        return failed_stage_result(
            "expected_files",
            f"Expected runtime output file(s) were not created: {', '.join(missing)}.",
        )

    return successful_stage_result(
        "expected_files",
        f"Expected runtime output file(s) were created: {', '.join(metadata.expected_output_files)}.",
    )


def run_sst_element_availability_check(
    elements: Sequence[str],
    *,
    sst_info_binary: str | None = None,
    timeout_seconds: int = 30,
) -> SSTExternalValidationResult:
    """Check that required SST element libraries are visible to ``sst-info``."""
    if not elements:
        return successful_stage_result(
            "sst_elements",
            "Fixture does not require specific SST element libraries.",
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
    commands: list[str] = []
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    for element in elements:
        command = [executable, str(element)]
        commands.extend(command)
        result = run_command(
            command,
            stage="sst_elements",
            timeout_seconds=timeout_seconds,
        )
        stdout_chunks.append(result.stdout)
        stderr_chunks.append(result.stderr)
        if not result.ok:
            missing.append(str(element))

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


def run_sst_component_availability_check(
    metadata: SSTExternalValidationMetadata,
    *,
    sst_info_binary: str | None = None,
    timeout_seconds: int = 30,
) -> SSTExternalValidationResult:
    """Check that required SST components are visible to ``sst-info``."""
    if not metadata.required_components:
        return successful_stage_result(
            "sst_components",
            "Fixture does not require specific SST components.",
        )

    executable = sst_info_binary or find_executable("sst-info")

    if executable is None:
        return skipped_stage_result("sst_components", "sst-info executable was not found in PATH.")

    missing: list[str] = []
    commands: list[str] = []
    stdout_chunks: list[str] = []
    stderr_chunks: list[str] = []

    for element in metadata.required_elements:
        command = [executable, str(element)]
        commands.extend(command)
        result = run_command(
            command,
            stage="sst_components",
            timeout_seconds=timeout_seconds,
        )
        stdout_chunks.append(result.stdout)
        stderr_chunks.append(result.stderr)
        if not result.ok:
            missing.extend(metadata.required_components)
            continue

        combined = f"{result.stdout}\n{result.stderr}"
        for component in metadata.required_components:
            if component not in combined:
                missing.append(component)

    if missing:
        unique_missing = tuple(dict.fromkeys(missing))
        return SSTExternalValidationResult(
            ok=False,
            skipped=True,
            stage="sst_components",
            message=(
                "Required SST component(s) unavailable on this test machine: "
                f"{', '.join(unique_missing)}."
            ),
            command=tuple(commands),
            stdout="\n".join(chunk for chunk in stdout_chunks if chunk),
            stderr="\n".join(chunk for chunk in stderr_chunks if chunk),
        )

    return SSTExternalValidationResult(
        ok=True,
        stage="sst_components",
        message=f"Required SST component(s) are available: {', '.join(metadata.required_components)}.",
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
    """Run the backend acceptance ladder for exported SST JSON.

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

    metadata_result = run_metadata_validation_check(metadata)
    results = [metadata_result]
    if not metadata_result.ok:
        return results

    json_result = run_json_syntax_check(
        json_path,
        timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
    )
    results.append(json_result)

    if not json_result.ok:
        return results

    if external_suite_root_validation_requested(environ):
        external_root_result = validate_external_suite_root(environ)
        results.append(external_root_result)
        if external_root_result.failed:
            return results

    if metadata.run_mode in {"init", "run"}:
        version_result = run_sst_version_check(
            metadata,
            sst_binary=sst_binary,
            timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
        )
        if metadata.min_sst_version or metadata.max_sst_version:
            results.append(version_result)
        if version_result.failed:
            return results

        element_result = run_sst_element_availability_check(
            metadata.required_elements,
            timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
        )
        if metadata.required_elements:
            results.append(element_result)
        if element_result.failed:
            return results

        component_result = run_sst_component_availability_check(
            metadata,
            timeout_seconds=min(max(metadata.timeout_seconds, 1), 30),
        )
        if metadata.required_components:
            results.append(component_result)
        if component_result.failed:
            return results

        if element_result.ok and component_result.ok and metadata.run_mode == "init":
            results.append(
                run_sst_init_check(
                    json_path,
                    sst_binary=sst_binary,
                    timeout_seconds=metadata.timeout_seconds,
                    expected_return_code=metadata.expected_return_code,
                )
            )
        elif element_result.ok and component_result.ok:
            runtime_result = run_sst_runtime_check(
                json_path,
                sst_binary=sst_binary,
                timeout_seconds=metadata.timeout_seconds,
                expected_return_code=metadata.expected_return_code,
                runtime_args=metadata.runtime_args,
                expected_stdout_fragments=metadata.expected_stdout_fragments,
                expected_stderr_fragments=metadata.expected_stderr_fragments,
            )
            results.append(runtime_result)
            if runtime_result.ok and metadata.expected_output_files:
                results.append(run_expected_output_file_check(Path(json_path).parent, metadata))
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
    """Export and validate one SST plugin-owned generated acceptance fixture."""
    from fuse.plugins.community.sst.export_json import (
        export_sst_json,
        validate_sst_json_export,
    )

    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)
    output_path = output_directory / fixture.output_filename

    results: list[SSTExternalValidationResult] = []
    metadata_result = run_metadata_validation_check(fixture.metadata)
    results.append(metadata_result)

    if not metadata_result.ok:
        return SSTFixtureAcceptanceResult(
            metadata=fixture.metadata,
            output_path=output_path,
            export_can_export=False,
            expected_top_level_sections_present=False,
            results=tuple(results),
        )

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

    if external_suite_root_validation_requested(environ):
        external_root_result = validate_external_suite_root(environ)
        results.append(external_root_result)
        if external_root_result.failed:
            return SSTFixtureAcceptanceResult(
                metadata=fixture.metadata,
                output_path=output_path,
                export_can_export=report.can_export,
                expected_top_level_sections_present=expected_sections_present,
                results=tuple(results),
            )

    if fixture.metadata.run_mode in {"init", "run"}:
        if external_validation_enabled(environ):
            version_result = run_sst_version_check(
                fixture.metadata,
                sst_binary=sst_binary,
                timeout_seconds=min(max(fixture.metadata.timeout_seconds, 1), 30),
            )
            if fixture.metadata.min_sst_version or fixture.metadata.max_sst_version:
                results.append(version_result)

            if not version_result.failed:
                element_result = run_sst_element_availability_check(
                    fixture.metadata.required_elements,
                    timeout_seconds=min(max(fixture.metadata.timeout_seconds, 1), 30),
                )
                if fixture.metadata.required_elements:
                    results.append(element_result)

                component_result = run_sst_component_availability_check(
                    fixture.metadata,
                    timeout_seconds=min(max(fixture.metadata.timeout_seconds, 1), 30),
                )
                if fixture.metadata.required_components:
                    results.append(component_result)

                if element_result.ok and component_result.ok and fixture.metadata.run_mode == "init":
                    results.append(
                        run_sst_init_check(
                            output_path,
                            sst_binary=sst_binary,
                            timeout_seconds=fixture.metadata.timeout_seconds,
                            expected_return_code=fixture.metadata.expected_return_code,
                        )
                    )
                elif element_result.ok and component_result.ok:
                    runtime_result = run_sst_runtime_check(
                        output_path,
                        sst_binary=sst_binary,
                        timeout_seconds=fixture.metadata.timeout_seconds,
                        expected_return_code=fixture.metadata.expected_return_code,
                        runtime_args=fixture.metadata.runtime_args,
                        expected_stdout_fragments=fixture.metadata.expected_stdout_fragments,
                        expected_stderr_fragments=fixture.metadata.expected_stderr_fragments,
                    )
                    results.append(runtime_result)
                    if runtime_result.ok and fixture.metadata.expected_output_files:
                        results.append(
                            run_expected_output_file_check(output_directory, fixture.metadata)
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


def run_generated_fixture_suite(
    fixtures: Sequence[object],
    output_dir: str | Path,
    *,
    environ: dict[str, str] | None = None,
    sst_binary: str | None = None,
) -> SSTExternalValidationSuiteReport:
    """Export fixtures and run all configured optional SST validation stages."""
    output_directory = Path(output_dir)
    results = tuple(
        run_generated_fixture_acceptance(
            fixture,
            output_directory / fixture.metadata.name,
            environ=environ,
            sst_binary=sst_binary,
        )
        for fixture in fixtures
    )
    return SSTExternalValidationSuiteReport(results=results)
