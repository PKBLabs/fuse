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

import subprocess
import sys

import pytest

from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)
from fuse.plugins.community.sst.external_validation.runner import (
    ENABLE_EXTERNAL_VALIDATION_ENV,
    external_validation_enabled,
    run_command,
    run_json_syntax_check,
    run_sst_external_acceptance,
    run_sst_init_check,
)


def test_sst_external_validation_metadata_round_trips():
    metadata = SSTExternalValidationMetadata.from_mapping(
        {
            "name": "minimal_link_model",
            "description": "Minimal FUSE-generated SST link model",
            "min_sst_version": "15.0.0",
            "required_elements": ["simpleElementExample"],
            "run_mode": "init",
            "timeout_seconds": 12,
            "expected_return_code": 0,
        }
    )

    assert metadata.name == "minimal_link_model"
    assert metadata.required_elements == ("simpleElementExample",)
    assert metadata.to_mapping()["timeout_seconds"] == 12


def test_sst_external_validation_enabled_reads_explicit_environment_flag():
    assert external_validation_enabled({ENABLE_EXTERNAL_VALIDATION_ENV: "1"}) is True
    assert external_validation_enabled({ENABLE_EXTERNAL_VALIDATION_ENV: "true"}) is True
    assert external_validation_enabled({ENABLE_EXTERNAL_VALIDATION_ENV: "off"}) is False
    assert external_validation_enabled({}) is False


def test_json_syntax_check_accepts_valid_exported_json(tmp_path):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text(
        '{"components": [], "links": [], "program_options": {}}',
        encoding="utf-8",
    )

    result = run_json_syntax_check(json_path)

    assert result.ok is True
    assert result.skipped is False
    assert result.stage == "json_syntax"
    assert result.return_code == 0


def test_json_syntax_check_rejects_invalid_exported_json(tmp_path):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text('{"components": [}', encoding="utf-8")

    result = run_json_syntax_check(json_path)

    assert result.ok is False
    assert result.failed is True
    assert result.stage == "json_syntax"
    assert result.return_code != 0


def test_sst_init_check_skips_when_sst_is_unavailable(tmp_path, monkeypatch):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        "fuse.plugins.community.sst.external_validation.runner.find_executable",
        lambda name: None,
    )

    result = run_sst_init_check(json_path, sst_binary=None)

    assert result.ok is False
    assert result.skipped is True
    assert "sst executable" in result.message


def test_run_command_reports_nonzero_return_code():
    result = run_command(
        [sys.executable, "-c", "import sys; sys.exit(7)"],
        stage="example",
        timeout_seconds=30,
    )

    assert result.ok is False
    assert result.failed is True
    assert result.return_code == 7
    assert "expected 0" in result.message


def test_external_acceptance_skips_unless_explicitly_enabled(tmp_path):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    metadata = SSTExternalValidationMetadata(name="minimal_link_model")

    results = run_sst_external_acceptance(
        json_path,
        metadata,
        environ={},
    )

    assert len(results) == 1
    assert results[0].skipped is True
    assert results[0].stage == "enabled"


def test_external_acceptance_runs_json_and_sst_init_when_enabled(tmp_path, monkeypatch):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    metadata = SSTExternalValidationMetadata(name="minimal_link_model")
    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    results = run_sst_external_acceptance(
        json_path,
        metadata,
        environ={ENABLE_EXTERNAL_VALIDATION_ENV: "1"},
        sst_binary="/usr/bin/sst",
    )

    assert [result.stage for result in results] == ["json_syntax", "sst_init"]
    assert all(result.ok for result in results)
    assert calls[0][1:3] == ["-m", "json.tool"]
    assert calls[1][0:2] == ["/usr/bin/sst", "--run-mode=init"]


@pytest.mark.sst_ext
def test_sst_external_acceptance_marker_is_backend_only(tmp_path):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    metadata = SSTExternalValidationMetadata(name="marker_smoke")

    results = run_sst_external_acceptance(
        json_path,
        metadata,
        environ={},
    )

    assert results[0].skipped is True


def test_minimal_two_component_fixture_exports_expected_contract(tmp_path):
    import json

    from fuse.plugins.community.sst.external_validation.fixtures import (
        minimal_two_component_link_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    fixture = minimal_two_component_link_fixture()
    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={},
    )

    assert acceptance.ok is True
    assert acceptance.output_path.exists()
    assert acceptance.export_can_export is True
    assert acceptance.expected_top_level_sections_present is True
    assert [result.stage for result in acceptance.results] == [
        "export_validation",
        "export_json",
        "json_syntax",
        "sst_json_contract",
        "sst_runtime",
    ]
    assert acceptance.results[-1].skipped is True

    data = json.loads(acceptance.output_path.read_text(encoding="utf-8"))

    assert list(data.keys()) == list(fixture.expected_top_level_sections)
    assert [component["name"] for component in data["components"]] == [
        "source0",
        "target0",
    ]
    assert [link["name"] for link in data["links"]] == ["link_source_target"]
    assert data["components"][0]["params"] == {"clock": "1GHz"}
    assert data["links"][0]["left"] == {
        "component": "source0",
        "port": "out",
        "latency": "1ns",
    }
    assert data["links"][0]["right"] == {
        "component": "target0",
        "port": "in",
        "latency": "1ns",
    }


def test_generated_fixture_acceptance_can_run_sst_init_when_enabled(tmp_path, monkeypatch):
    import subprocess
    from dataclasses import replace

    from fuse.plugins.community.sst.external_validation.fixtures import (
        minimal_two_component_link_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        ENABLE_EXTERNAL_VALIDATION_ENV,
        run_generated_fixture_acceptance,
    )

    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    fixture = minimal_two_component_link_fixture()
    fixture = replace(
        fixture,
        metadata=replace(fixture.metadata, run_mode="init"),
    )

    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={ENABLE_EXTERNAL_VALIDATION_ENV: "1"},
        sst_binary="/usr/bin/sst",
    )

    assert acceptance.ok is True
    assert [result.stage for result in acceptance.results] == [
        "export_validation",
        "export_json",
        "json_syntax",
        "sst_json_contract",
        "sst_init",
    ]
    assert calls[0][1:3] == ["-m", "json.tool"]
    assert calls[1][0:2] == ["/usr/bin/sst", "--run-mode=init"]


def test_generated_fixture_acceptance_reports_export_validation_errors(tmp_path):
    from fuse.plugins.community.sst.external_validation.fixtures import (
        SSTExternalValidationFixture,
        SSTExternalValidationScene,
        make_fixture_component,
        make_fixture_node,
    )
    from fuse.plugins.community.sst.external_validation.metadata import (
        SSTExternalValidationMetadata,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    component = make_fixture_component(
        component_id="broken",
        element="fuseExternalValidation",
        name="Broken",
    )
    first = make_fixture_node(
        node_id=1,
        instance_name="duplicate",
        component=component,
        ports=("out",),
    )
    second = make_fixture_node(
        node_id=2,
        instance_name="duplicate",
        component=component,
        ports=("in",),
    )
    fixture = SSTExternalValidationFixture(
        metadata=SSTExternalValidationMetadata(name="broken_duplicate_names"),
        scene=SSTExternalValidationScene([first, second]),
    )

    acceptance = run_generated_fixture_acceptance(fixture, tmp_path, environ={})

    assert acceptance.ok is False
    assert acceptance.output_path.exists() is False
    assert acceptance.export_can_export is False
    assert acceptance.failed_results[0].stage == "export_validation"
    assert "unique" in acceptance.failed_results[0].message
