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
    generated_acceptance_fixtures,
    minimal_two_component_link_fixture,
    simple_element_example_init_fixture,
)
from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)
from fuse.plugins.community.sst.external_validation.runner import (
    SST_EXT_TESTS_ROOT_ENV,
    SSTExternalValidationResult,
    SSTExternalValidationSuiteReport,
    SSTFixtureAcceptanceResult,
    external_suite_root,
    external_validation_enabled,
    find_executable,
    run_generated_fixture_acceptance,
    run_generated_fixture_suite,
    run_json_syntax_check,
    run_metadata_validation_check,
    run_sst_component_availability_check,
    run_sst_element_availability_check,
    run_sst_external_acceptance,
    run_sst_init_check,
    run_sst_runtime_check,
    run_sst_version_check,
    validate_external_suite_root,
)

__all__ = [
    "SST_EXT_TESTS_ROOT_ENV",
    "SSTExternalValidationFixture",
    "SSTExternalValidationMetadata",
    "SSTExternalValidationResult",
    "SSTExternalValidationSuiteReport",
    "SSTFixtureAcceptanceResult",
    "external_suite_root",
    "external_validation_enabled",
    "find_executable",
    "generated_acceptance_fixtures",
    "minimal_two_component_link_fixture",
    "run_generated_fixture_acceptance",
    "run_generated_fixture_suite",
    "run_json_syntax_check",
    "run_metadata_validation_check",
    "run_sst_component_availability_check",
    "run_sst_element_availability_check",
    "run_sst_external_acceptance",
    "run_sst_init_check",
    "run_sst_runtime_check",
    "run_sst_version_check",
    "simple_element_example_init_fixture",
    "validate_external_suite_root",
]
