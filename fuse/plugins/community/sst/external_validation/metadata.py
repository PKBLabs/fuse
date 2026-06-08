# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Metadata model for optional backend SST external validation fixtures.

External validation fixtures are exported by FUSE and can optionally be checked
against a real SST installation or the separate ``sst-ext-tests`` suite. This
module keeps the fixture metadata serializable and independent of Qt objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


VALID_RUN_MODES = ("json", "init", "run")


def tuple_of_strings(value: Any) -> tuple[str, ...]:
    """Normalize a scalar or iterable value into a tuple of strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


@dataclass(frozen=True)
class SSTExternalValidationMetadata:
    """Metadata for one backend-only SST acceptance fixture.

    The shape intentionally mirrors the information an external SST acceptance
    harness needs without making FUSE core aware of SST-specific concepts.
    """

    name: str
    description: str = ""
    min_sst_version: str | None = None
    max_sst_version: str | None = None
    required_elements: tuple[str, ...] = field(default_factory=tuple)
    required_components: tuple[str, ...] = field(default_factory=tuple)
    run_mode: str = "init"
    timeout_seconds: int = 60
    expected_return_code: int = 0
    runtime_args: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_output_files: tuple[str, ...] = field(default_factory=tuple)
    external_suite_tags: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SSTExternalValidationMetadata":
        """Build fixture metadata from a JSON/YAML-style mapping."""
        return cls(
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "")).strip(),
            min_sst_version=data.get("min_sst_version"),
            max_sst_version=data.get("max_sst_version"),
            required_elements=tuple_of_strings(data.get("required_elements", ())),
            required_components=tuple_of_strings(data.get("required_components", ())),
            run_mode=str(data.get("run_mode", "init") or "init"),
            timeout_seconds=int(data.get("timeout_seconds", 60) or 60),
            expected_return_code=int(data.get("expected_return_code", 0) or 0),
            runtime_args=tuple_of_strings(data.get("runtime_args", ())),
            expected_stdout_fragments=tuple_of_strings(
                data.get("expected_stdout_fragments", ())
            ),
            expected_stderr_fragments=tuple_of_strings(
                data.get("expected_stderr_fragments", ())
            ),
            expected_output_files=tuple_of_strings(data.get("expected_output_files", ())),
            external_suite_tags=tuple_of_strings(data.get("external_suite_tags", ())),
        )

    def to_mapping(self) -> dict[str, Any]:
        """Serialize this metadata to a JSON-compatible mapping."""
        return {
            "name": self.name,
            "description": self.description,
            "min_sst_version": self.min_sst_version,
            "max_sst_version": self.max_sst_version,
            "required_elements": list(self.required_elements),
            "required_components": list(self.required_components),
            "run_mode": self.run_mode,
            "timeout_seconds": self.timeout_seconds,
            "expected_return_code": self.expected_return_code,
            "runtime_args": list(self.runtime_args),
            "expected_stdout_fragments": list(self.expected_stdout_fragments),
            "expected_stderr_fragments": list(self.expected_stderr_fragments),
            "expected_output_files": list(self.expected_output_files),
            "external_suite_tags": list(self.external_suite_tags),
        }

    def validation_errors(self) -> tuple[str, ...]:
        """Return human-readable configuration errors for this fixture."""
        errors: list[str] = []

        if not self.name.strip():
            errors.append("Fixture metadata requires a non-empty name.")
        if self.run_mode not in VALID_RUN_MODES:
            errors.append(
                "Fixture run_mode must be one of "
                f"{', '.join(VALID_RUN_MODES)}; got {self.run_mode!r}."
            )
        if self.timeout_seconds <= 0:
            errors.append("Fixture timeout_seconds must be greater than zero.")
        if self.run_mode == "json" and self.runtime_args:
            errors.append("JSON-only fixtures cannot define runtime_args.")
        if self.run_mode == "json" and self.expected_stdout_fragments:
            errors.append("JSON-only fixtures cannot define expected_stdout_fragments.")
        if self.run_mode == "json" and self.expected_stderr_fragments:
            errors.append("JSON-only fixtures cannot define expected_stderr_fragments.")
        if self.expected_output_files and self.run_mode != "run":
            errors.append("expected_output_files are only valid for run-mode fixtures.")
        if self.required_components and not self.required_elements:
            errors.append("required_components require at least one required element library.")

        return tuple(errors)

    @property
    def valid(self) -> bool:
        """Return true when the metadata is internally consistent."""
        return not self.validation_errors()
