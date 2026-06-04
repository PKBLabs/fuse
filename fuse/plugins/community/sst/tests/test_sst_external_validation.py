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

from fuse.plugins.community.sst.external_validation.fixtures import (
    generated_acceptance_fixtures,
)
from fuse.plugins.community.sst.external_validation.metadata import (
    SSTExternalValidationMetadata,
)
from fuse.plugins.community.sst.external_validation.runner import (
    ENABLE_EXTERNAL_VALIDATION_ENV,
    SST_EXT_TESTS_ROOT_ENV,
    compare_versions,
    external_validation_enabled,
    parse_version_tuple,
    run_command,
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


def test_sst_external_validation_metadata_round_trips():
    metadata = SSTExternalValidationMetadata.from_mapping(
        {
            "name": "minimal_link_model",
            "description": "Minimal FUSE-generated SST link model",
            "min_sst_version": "15.0.0",
            "required_elements": ["simpleElementExample"],
            "required_components": ["example0"],
            "run_mode": "init",
            "timeout_seconds": 12,
            "expected_return_code": 0,
        }
    )

    assert metadata.name == "minimal_link_model"
    assert metadata.required_elements == ("simpleElementExample",)
    assert metadata.required_components == ("example0",)
    assert metadata.to_mapping()["timeout_seconds"] == 12
    assert metadata.validation_errors() == ()


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

    assert [result.stage for result in results] == [
        "fixture_metadata",
        "json_syntax",
        "sst_init",
    ]
    assert all(result.ok for result in results)
    assert calls[0][1:3] == ["-m", "json.tool"]
    assert calls[1][0:2] == ["/usr/bin/sst", "--run-mode=init"]


def test_sst_external_acceptance_skips_when_backend_gate_is_disabled(tmp_path):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    metadata = SSTExternalValidationMetadata(name="marker_smoke")

    results = run_sst_external_acceptance(
        json_path,
        metadata,
        environ={},
    )

    assert results[0].skipped is True


def format_fixture_acceptance_failure(acceptance):
    lines = [
        f"SST external validation fixture failed: {acceptance.metadata.name}",
        f"output_path: {acceptance.output_path}",
        f"export_can_export: {acceptance.export_can_export}",
        (
            "expected_top_level_sections_present: "
            f"{acceptance.expected_top_level_sections_present}"
        ),
    ]
    for result in acceptance.results:
        status = "SKIP" if result.skipped else "PASS" if result.ok else "FAIL"
        lines.append(f"{status} {result.stage}: {result.message}")
        if result.command:
            lines.append("  command: " + " ".join(result.command))
        if result.stdout:
            lines.append("  stdout: " + result.stdout.strip())
        if result.stderr:
            lines.append("  stderr: " + result.stderr.strip())

    return "\n".join(lines)


@pytest.mark.sst_ext
@pytest.mark.parametrize(
    "fixture",
    generated_acceptance_fixtures(),
    ids=lambda fixture: fixture.metadata.name,
)
def test_generated_acceptance_fixture_passes_backend_validation(fixture, tmp_path):
    acceptance = run_generated_fixture_acceptance(fixture, tmp_path)

    assert acceptance.ok, format_fixture_acceptance_failure(acceptance)


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
        "fixture_metadata",
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
        "fixture_metadata",
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



def test_sst_element_availability_skips_when_sst_info_is_unavailable(monkeypatch):
    monkeypatch.setattr(
        "fuse.plugins.community.sst.external_validation.runner.find_executable",
        lambda name: None,
    )

    result = run_sst_element_availability_check(("simpleElementExample",))

    assert result.skipped is True
    assert result.stage == "sst_elements"
    assert "sst-info executable" in result.message


def test_sst_element_availability_checks_each_required_element(monkeypatch):
    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="element ok", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_sst_element_availability_check(
        ("simpleElementExample", "memHierarchy"),
        sst_info_binary="/usr/bin/sst-info",
    )

    assert result.ok is True
    assert result.skipped is False
    assert calls == [
        ["/usr/bin/sst-info", "simpleElementExample"],
        ["/usr/bin/sst-info", "memHierarchy"],
    ]


def test_simple_element_example_init_fixture_skips_real_sst_when_disabled(tmp_path):
    from fuse.plugins.community.sst.external_validation.fixtures import (
        simple_element_example_init_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    fixture = simple_element_example_init_fixture()
    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={},
    )

    assert acceptance.ok is True
    assert acceptance.metadata.run_mode == "init"
    assert acceptance.results[-1].stage == "sst_init"
    assert acceptance.results[-1].skipped is True



def test_simple_element_example_init_fixture_exports_required_parameters(tmp_path):
    import json

    from fuse.plugins.community.sst.external_validation.fixtures import (
        simple_element_example_init_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    fixture = simple_element_example_init_fixture()
    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={},
    )

    assert acceptance.ok is True
    data = json.loads(acceptance.output_path.read_text(encoding="utf-8"))
    assert data["components"] == [
        {
            "name": "example0",
            "type": "simpleElementExample.example0",
            "params": {"eventsToSend": 0},
        }
    ]

def test_simple_element_example_init_fixture_checks_elements_before_sst_init(
    tmp_path, monkeypatch
):
    from fuse.plugins.community.sst.external_validation.fixtures import (
        simple_element_example_init_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        ENABLE_EXTERNAL_VALIDATION_ENV,
        run_generated_fixture_acceptance,
    )

    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="Component: example0", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(
        "fuse.plugins.community.sst.external_validation.runner.find_executable",
        lambda name: "/usr/bin/sst-info" if name == "sst-info" else None,
    )

    fixture = simple_element_example_init_fixture()
    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={ENABLE_EXTERNAL_VALIDATION_ENV: "1"},
        sst_binary="/usr/bin/sst",
    )

    assert acceptance.ok is True
    assert [result.stage for result in acceptance.results] == [
        "fixture_metadata",
        "export_validation",
        "export_json",
        "json_syntax",
        "sst_json_contract",
        "sst_elements",
        "sst_components",
        "sst_init",
    ]
    assert calls[0][1:3] == ["-m", "json.tool"]
    assert calls[1] == ["/usr/bin/sst-info", "simpleElementExample"]
    assert calls[2] == ["/usr/bin/sst-info", "simpleElementExample"]
    assert calls[3][0:2] == ["/usr/bin/sst", "--run-mode=init"]


def test_generated_acceptance_fixture_registry_contains_json_and_init_fixtures():
    from fuse.plugins.community.sst.external_validation.fixtures import (
        generated_acceptance_fixtures,
    )

    fixtures = generated_acceptance_fixtures()

    assert [fixture.metadata.name for fixture in fixtures] == [
        "minimal_two_component_link",
        "explicit_latency_parameters",
        "subcomponent_slot_assignment",
        "simple_element_example_init",
    ]
    assert [fixture.metadata.run_mode for fixture in fixtures] == [
        "json",
        "json",
        "json",
        "init",
    ]



def test_explicit_latency_parameters_fixture_exports_typed_params_and_endpoint_latencies(tmp_path):
    import json

    from fuse.plugins.community.sst.external_validation.fixtures import (
        explicit_latency_parameters_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    fixture = explicit_latency_parameters_fixture()
    acceptance = run_generated_fixture_acceptance(fixture, tmp_path, environ={})

    assert acceptance.ok is True
    assert acceptance.export_can_export is True
    assert acceptance.expected_top_level_sections_present is True

    data = json.loads(acceptance.output_path.read_text(encoding="utf-8"))
    components = {component["name"]: component for component in data["components"]}

    assert fixture.metadata.external_suite_tags == ("json", "parameters", "latency")
    assert sorted(components) == ["param_source0", "param_target0"]
    assert components["param_source0"]["params"] == {
        "clock": "2GHz",
        "enabled": True,
        "max_reqs": 16,
    }
    assert "empty_parameter" not in components["param_source0"]["params"]
    assert data["links"] == [
        {
            "name": "link_param_source_target",
            "noCut": False,
            "nonlocal": False,
            "left": {
                "component": "param_source0",
                "port": "cache",
                "latency": "250ps",
            },
            "right": {
                "component": "param_target0",
                "port": "cpu",
                "latency": "2ns",
            },
        }
    ]


def test_subcomponent_slot_assignment_fixture_exports_nested_subcomponent(tmp_path):
    import json

    from fuse.plugins.community.sst.external_validation.fixtures import (
        subcomponent_slot_assignment_fixture,
    )
    from fuse.plugins.community.sst.external_validation.runner import (
        run_generated_fixture_acceptance,
    )

    fixture = subcomponent_slot_assignment_fixture()
    acceptance = run_generated_fixture_acceptance(fixture, tmp_path, environ={})

    assert acceptance.ok is True
    assert acceptance.export_can_export is True
    assert acceptance.expected_top_level_sections_present is True

    data = json.loads(acceptance.output_path.read_text(encoding="utf-8"))

    assert fixture.metadata.external_suite_tags == ("json", "subcomponent", "slot")
    assert len(data["components"]) == 1
    assert data["components"][0] == {
        "name": "parent0",
        "type": "fuseExternalValidation.Parent",
        "params": {"clock": "1GHz"},
        "subcomponents": [
            {
                "name": "slot_child0",
                "type": "fuseExternalValidation.ChildSubComponent",
                "params": {"mode": "test"},
                "slot_name": "backend_slot",
            }
        ],
    }
    assert data["links"] == []


def test_sst_external_validation_metadata_includes_runtime_expectations():
    metadata = SSTExternalValidationMetadata.from_mapping(
        {
            "name": "runtime_smoke",
            "run_mode": "run",
            "runtime_args": ["--stop-at=1ns"],
            "expected_stdout_fragments": ["Simulation is complete"],
            "expected_stderr_fragments": ["warning"],
        }
    )

    assert metadata.run_mode == "run"
    assert metadata.runtime_args == ("--stop-at=1ns",)
    assert metadata.expected_stdout_fragments == ("Simulation is complete",)
    assert metadata.expected_stderr_fragments == ("warning",)
    assert metadata.to_mapping()["runtime_args"] == ["--stop-at=1ns"]


def test_sst_runtime_check_runs_sst_with_runtime_args(tmp_path, monkeypatch):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")
    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Simulation is complete",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_sst_runtime_check(
        json_path,
        sst_binary="/usr/bin/sst",
        runtime_args=("--stop-at=1ns",),
        expected_stdout_fragments=("Simulation is complete",),
    )

    assert result.ok is True
    assert result.stage == "sst_runtime"
    assert calls == [["/usr/bin/sst", "--stop-at=1ns", str(json_path)]]


def test_sst_runtime_check_reports_missing_expected_output(tmp_path, monkeypatch):
    json_path = tmp_path / "model.sst.json"
    json_path.write_text("{}", encoding="utf-8")

    def fake_run(command, text, stdout, stderr, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout="different output", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_sst_runtime_check(
        json_path,
        sst_binary="/usr/bin/sst",
        expected_stdout_fragments=("expected output",),
    )

    assert result.ok is False
    assert result.failed is True
    assert "stdout missing" in result.message


def test_generated_fixture_acceptance_can_run_runtime_when_enabled(tmp_path, monkeypatch):
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
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="runtime ok",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    fixture = minimal_two_component_link_fixture()
    fixture = replace(
        fixture,
        metadata=replace(
            fixture.metadata,
            run_mode="run",
            runtime_args=("--stop-at=1ns",),
            expected_stdout_fragments=("runtime ok",),
        ),
    )

    acceptance = run_generated_fixture_acceptance(
        fixture,
        tmp_path,
        environ={ENABLE_EXTERNAL_VALIDATION_ENV: "1"},
        sst_binary="/usr/bin/sst",
    )

    assert acceptance.ok is True
    assert [result.stage for result in acceptance.results] == [
        "fixture_metadata",
        "export_validation",
        "export_json",
        "json_syntax",
        "sst_json_contract",
        "sst_runtime",
    ]
    assert calls[0][1:3] == ["-m", "json.tool"]
    assert calls[1] == ["/usr/bin/sst", "--stop-at=1ns", str(acceptance.output_path)]


def test_sst_external_validation_metadata_rejects_invalid_combinations():
    metadata = SSTExternalValidationMetadata(
        name="bad_json_runtime",
        run_mode="json",
        runtime_args=("--stop-at=1ns",),
    )

    errors = metadata.validation_errors()

    assert any("JSON-only" in error for error in errors)


def test_sst_external_validation_metadata_rejects_unknown_run_mode():
    metadata = SSTExternalValidationMetadata(name="bad_mode", run_mode="profile")

    result = run_metadata_validation_check(metadata)

    assert result.failed is True
    assert "run_mode" in result.message


def test_sst_external_validation_metadata_requires_component_elements():
    metadata = SSTExternalValidationMetadata(
        name="component_without_element",
        required_components=("example0",),
    )

    assert any("required_components" in error for error in metadata.validation_errors())


def test_sst_version_parser_and_comparison_tolerate_banner_text():
    assert parse_version_tuple("SST-Core Version 15.0.1") == (15, 0, 1)
    assert compare_versions("15.0.1", "15.0.0") == 1
    assert compare_versions("15.0", "15.0.0") == 0
    assert compare_versions("14.1.0", "15.0.0") == -1


def test_sst_version_check_skips_when_version_is_outside_fixture_bounds(monkeypatch):
    def fake_run(command, text, stdout, stderr, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout="SST-Core Version 14.0.0", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    metadata = SSTExternalValidationMetadata(
        name="needs_newer_sst",
        min_sst_version="15.0.0",
    )

    result = run_sst_version_check(metadata, sst_binary="/usr/bin/sst")

    assert result.skipped is True
    assert "older than" in result.message


def test_sst_component_availability_checks_required_components(monkeypatch):
    calls = []

    def fake_run(command, text, stdout, stderr, timeout, check):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Component: example0\nComponent: example1",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    metadata = SSTExternalValidationMetadata(
        name="simple_component",
        required_elements=("simpleElementExample",),
        required_components=("example0",),
    )

    result = run_sst_component_availability_check(
        metadata,
        sst_info_binary="/usr/bin/sst-info",
    )

    assert result.ok is True
    assert result.stage == "sst_components"
    assert calls == [["/usr/bin/sst-info", "simpleElementExample"]]


def test_sst_component_availability_skips_when_required_component_is_missing(monkeypatch):
    def fake_run(command, text, stdout, stderr, timeout, check):
        return subprocess.CompletedProcess(command, 0, stdout="Component: other", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    metadata = SSTExternalValidationMetadata(
        name="missing_component",
        required_elements=("simpleElementExample",),
        required_components=("example0",),
    )

    result = run_sst_component_availability_check(
        metadata,
        sst_info_binary="/usr/bin/sst-info",
    )

    assert result.skipped is True
    assert "example0" in result.message


def test_external_suite_root_validation_is_optional(tmp_path):
    missing = validate_external_suite_root({})
    assert missing.skipped is True

    available = validate_external_suite_root({SST_EXT_TESTS_ROOT_ENV: str(tmp_path)})
    assert available.ok is True

    unavailable = validate_external_suite_root({SST_EXT_TESTS_ROOT_ENV: str(tmp_path / "missing")})
    assert unavailable.failed is True


def test_generated_fixture_suite_report_summarizes_results(tmp_path):
    from fuse.plugins.community.sst.external_validation.fixtures import (
        minimal_two_component_link_fixture,
    )

    report = run_generated_fixture_suite(
        (minimal_two_component_link_fixture(),),
        tmp_path,
        environ={},
    )

    assert report.to_mapping()["total"] == 1
    assert report.to_mapping()["passed"] == 1
    assert report.results[0].metadata.name == "minimal_two_component_link"
