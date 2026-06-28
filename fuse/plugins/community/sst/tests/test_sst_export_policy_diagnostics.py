# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

from __future__ import annotations

from dataclasses import dataclass, field

from fuse.core.model.models import ComponentDefinition
from fuse.plugins.community.sst.export_json import validate_sst_json_export
from fuse.plugins.community.sst.tests.conftest import (
    cache_component,
    custom_cpu_component,
    make_catalog,
    write_catalog,
)


@dataclass
class FakeNode:
    node_id: int
    instance_name: str
    component: ComponentDefinition
    parameters: dict = field(default_factory=dict)


class FakeScene:
    def __init__(self, nodes):
        self._nodes = list(nodes)
        self.links = []
        self.subcomp_attachments = []

    def component_items(self):
        return list(self._nodes)


def _component(
    element: str,
    name: str,
    *,
    target_id: int | str,
    is_subcomp: int = 0,
    component_id: int | str | None = None,
) -> ComponentDefinition:
    return ComponentDefinition(
        component_id=component_id,
        plugin_id="sst",
        target_id=str(target_id),
        target_label=f"SST target {target_id}",
        framework_version="16.0.0",
        element=element,
        name=name,
        is_subcomp=is_subcomp,
    )


def _seed_custom_target(env, *, enable_changed: bool = False):
    baseline_catalog = make_catalog("16.0.0", [cache_component(default_line_size="64")])
    discovered_components = [
        cache_component(default_line_size="128" if enable_changed else "64"),
        custom_cpu_component(),
    ]
    discovered_catalog = make_catalog("16.0.0", discovered_components)

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
        source_fingerprint="exportpolicychanged" if enable_changed else "exportpolicycustom",
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

    enabled_keys = {env.component_catalog.component_key(custom_cpu_component())}
    if enable_changed:
        enabled_keys.add(env.component_catalog.component_key(cache_component()))

    return env.component_catalog.import_custom_component_selection(
        discovery=discovery,
        enabled_keys=enabled_keys,
        project_uid="project-export-policy",
    )[0]


def _warning_messages(report):
    return [
        str(getattr(issue, "message", "") or "")
        for issue in report.warnings
    ]


def test_export_validation_groups_custom_component_policy_warning(sst_env):
    env = sst_env
    target_id = _seed_custom_target(env)

    scene = FakeScene(
        [
            FakeNode(
                1,
                "custom_cpu0",
                _component("customElement", "CustomCPU", target_id=target_id),
                {"custom_width": "4"},
            )
        ]
    )

    report = validate_sst_json_export(scene)
    messages = _warning_messages(report)

    assert report.can_export
    assert any("uses custom SST components" in message for message in messages)
    assert any("customElement.CustomCPU" in message for message in messages)


def test_export_validation_groups_changed_component_policy_warning(sst_env):
    env = sst_env
    target_id = _seed_custom_target(env, enable_changed=True)

    scene = FakeScene(
        [
            FakeNode(
                1,
                "cache0",
                _component("memHierarchy", "Cache", target_id=target_id),
                {"cache_line_size": "128"},
            )
        ]
    )

    report = validate_sst_json_export(scene)
    messages = _warning_messages(report)

    assert report.can_export
    assert any("metadata differs from the bundled baseline" in message for message in messages)
    assert any("memHierarchy.Cache" in message for message in messages)


def test_export_validation_does_not_warn_for_unused_custom_component(sst_env):
    env = sst_env
    target_id = _seed_custom_target(env)

    scene = FakeScene(
        [
            FakeNode(
                1,
                "cache0",
                _component("memHierarchy", "Cache", target_id=target_id),
                {"cache_line_size": "64"},
            )
        ]
    )

    report = validate_sst_json_export(scene)
    messages = _warning_messages(report)

    assert report.can_export
    assert not any("uses custom SST components" in message for message in messages)
    assert not any("customElement.CustomCPU" in message for message in messages)


def test_export_validation_does_not_warn_for_bundled_baseline_target(sst_env):
    env = sst_env
    baseline_catalog = make_catalog("16.0.0", [cache_component()])
    baseline_path = write_catalog(env.tmp_path / "baseline-only.json", baseline_catalog)
    target_id = env.get_sstinfo.sync_sstinfo_catalog_json_to_database(
        baseline_path,
        version="16.0.0",
        label="SST 16.0.0",
        source_kind="bundled-component-catalog",
        source_path="",
        command="baseline",
        is_default=True,
        clear_existing=True,
    )

    scene = FakeScene(
        [
            FakeNode(
                1,
                "cache0",
                _component("memHierarchy", "Cache", target_id=target_id),
                {"cache_line_size": "64"},
            )
        ]
    )

    report = validate_sst_json_export(scene)
    messages = _warning_messages(report)

    assert report.can_export
    assert not any("custom SST components" in message for message in messages)
    assert not any("metadata differs from the bundled baseline" in message for message in messages)
