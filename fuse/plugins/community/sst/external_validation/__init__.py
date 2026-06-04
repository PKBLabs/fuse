# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
"""Backend-only SST external validation helpers owned by the SST plugin."""

from fuse.plugins.community.sst.external_validation.fixtures import (
    SSTExternalValidationFixture,
    minimal_two_component_link_fixture,
)
from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)
from fuse.plugins.community.sst.external_validation.runner import (
    SSTExternalValidationResult,
    SSTFixtureAcceptanceResult,
    external_validation_enabled,
    find_executable,
    run_generated_fixture_acceptance,
    run_json_syntax_check,
    run_sst_external_acceptance,
    run_sst_init_check,
)

__all__ = [
    "SSTExternalValidationFixture",
    "SSTExternalValidationMetadata",
    "SSTExternalValidationResult",
    "SSTFixtureAcceptanceResult",
    "external_validation_enabled",
    "find_executable",
    "minimal_two_component_link_fixture",
    "run_generated_fixture_acceptance",
    "run_json_syntax_check",
    "run_sst_external_acceptance",
    "run_sst_init_check",
]
