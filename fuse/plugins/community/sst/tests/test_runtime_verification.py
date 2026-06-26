
from __future__ import annotations

from types import SimpleNamespace

from conftest import cache_component, custom_cpu_component, make_catalog, write_catalog


def _scene_using(element: str, name: str, *, is_subcomp: int = 0):
    node = SimpleNamespace(
        component=SimpleNamespace(
            plugin_id="sst",
            element=element,
            name=name,
            is_subcomp=is_subcomp,
        )
    )
    return SimpleNamespace(component_items=lambda: [node])


def _seed_custom_target(env):
    baseline_catalog = make_catalog("16.0.0", [cache_component()])
    discovered_catalog = make_catalog("16.0.0", [cache_component(), custom_cpu_component()])

    baseline_path = write_catalog(env.tmp_path / "baseline.json", baseline_catalog)
    env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        baseline_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="baseline",
        is_default=True,
        clear_existing=True,
    )

    discovery = env.component_catalog.SSTComponentDiscovery(
        version="16.0.0",
        source_label="SST 16.0.0 — pytest custom",
        source_fingerprint="runtimecheck",
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
        entries=env.component_catalog.classify_discovered_catalog(
            version="16.0.0",
            discovered_catalog=discovered_catalog,
            baseline_catalog=baseline_catalog,
        ),
        previous_enabled_keys=set(),
        command_text="sst-info",
    )

    custom_key = env.component_catalog.component_key(custom_cpu_component())
    target_id, target_label, _ = env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys={custom_key},
        project_uid="project-runtime",
    )
    return target_id, target_label


def test_runtime_verification_errors_when_used_custom_component_is_missing(sst_env, monkeypatch):
    env = sst_env
    target_id, target_label = _seed_custom_target(env)

    command_result = env.get_sstinfo.CommandResult(
        command=["sst-info"],
        return_code=0,
        stdout="runtime metadata",
        stderr="",
    )

    monkeypatch.setattr(
        env.component_catalog,
        "validate_sst_toolchain",
        lambda **kwargs: (True, "SST: Ok", command_result),
    )
    monkeypatch.setattr(
        env.component_catalog,
        "get_sstinfo_for_toolchain",
        lambda *args, **kwargs: command_result,
    )
    monkeypatch.setattr(
        env.component_catalog,
        "parse_sstinfo_output",
        lambda stdout: ([], []),
    )

    report = env.component_catalog.verify_project_sst_runtime(
        scene=_scene_using("customElement", "CustomCPU"),
        framework_version_id=target_id,
        expected_version="16.0.0",
        target_label=target_label,
        toolchain=env.component_catalog.ToolchainSettings(),
    )

    assert report.ok is False
    assert env.component_catalog.component_key(custom_cpu_component()) in report.missing_used_component_keys
    assert "CustomCPU" in report.message()


def test_runtime_verification_passes_when_used_custom_component_is_available(sst_env, monkeypatch):
    env = sst_env
    target_id, target_label = _seed_custom_target(env)

    command_result = env.get_sstinfo.CommandResult(
        command=["sst-info"],
        return_code=0,
        stdout="runtime metadata",
        stderr="",
    )

    monkeypatch.setattr(
        env.component_catalog,
        "validate_sst_toolchain",
        lambda **kwargs: (True, "SST: Ok", command_result),
    )
    monkeypatch.setattr(
        env.component_catalog,
        "get_sstinfo_for_toolchain",
        lambda *args, **kwargs: command_result,
    )
    monkeypatch.setattr(
        env.component_catalog,
        "parse_sstinfo_output",
        lambda stdout: ([], [env.get_sstinfo.ParsedComponent(
            element_name="customElement",
            name="CustomCPU",
            description="Custom CPU",
            is_subcomp=0,
        )]),
    )

    report = env.component_catalog.verify_project_sst_runtime(
        scene=_scene_using("customElement", "CustomCPU"),
        framework_version_id=target_id,
        expected_version="16.0.0",
        target_label=target_label,
        toolchain=env.component_catalog.ToolchainSettings(),
    )

    assert report.ok is True
    assert not report.missing_used_component_keys
    assert "All custom/changed SST components used by this model are available" in report.message()
