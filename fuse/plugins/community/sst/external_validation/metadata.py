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
from typing import Any


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
    run_mode: str = "init"
    timeout_seconds: int = 60
    expected_return_code: int = 0
    runtime_args: tuple[str, ...] = field(default_factory=tuple)
    expected_stdout_fragments: tuple[str, ...] = field(default_factory=tuple)
    expected_stderr_fragments: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "SSTExternalValidationMetadata":
        required_elements = data.get("required_elements", ()) or ()
        runtime_args = data.get("runtime_args", ()) or ()
        expected_stdout_fragments = data.get("expected_stdout_fragments", ()) or ()
        expected_stderr_fragments = data.get("expected_stderr_fragments", ()) or ()

        return cls(
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "")).strip(),
            min_sst_version=data.get("min_sst_version"),
            max_sst_version=data.get("max_sst_version"),
            required_elements=tuple(str(item) for item in required_elements),
            run_mode=str(data.get("run_mode", "init") or "init"),
            timeout_seconds=int(data.get("timeout_seconds", 60) or 60),
            expected_return_code=int(data.get("expected_return_code", 0) or 0),
            runtime_args=tuple(str(item) for item in runtime_args),
            expected_stdout_fragments=tuple(str(item) for item in expected_stdout_fragments),
            expected_stderr_fragments=tuple(str(item) for item in expected_stderr_fragments),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "min_sst_version": self.min_sst_version,
            "max_sst_version": self.max_sst_version,
            "required_elements": list(self.required_elements),
            "run_mode": self.run_mode,
            "timeout_seconds": self.timeout_seconds,
            "expected_return_code": self.expected_return_code,
            "runtime_args": list(self.runtime_args),
            "expected_stdout_fragments": list(self.expected_stdout_fragments),
            "expected_stderr_fragments": list(self.expected_stderr_fragments),
        }
