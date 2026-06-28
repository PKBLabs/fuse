
from __future__ import annotations

from fuse.plugins.community.sst.tests.conftest import cache_component, custom_cpu_component, make_catalog, memcontroller_component


def test_classify_discovered_catalog_marks_baseline_custom_changed_and_missing(sst_env):
    env = sst_env

    baseline_catalog = make_catalog(
        "16.0.0",
        [
            cache_component(default_line_size="64"),
            memcontroller_component(),
        ],
    )
    discovered_catalog = make_catalog(
        "16.0.0",
        [
            cache_component(default_line_size="128"),
            custom_cpu_component(),
        ],
    )

    entries = env.component_catalog.classify_discovered_catalog(
        version="16.0.0",
        discovered_catalog=discovered_catalog,
        baseline_catalog=baseline_catalog,
    )
    status_by_display_name = {entry.display_name: entry.status for entry in entries}

    assert status_by_display_name["memHierarchy.Cache"] == "changed"
    assert status_by_display_name["customElement.CustomCPU"] == "custom"
    assert status_by_display_name["memHierarchy.MemController"] == "missing"

    cache_entry = next(entry for entry in entries if entry.display_name == "memHierarchy.Cache")
    assert cache_entry.enabled_by_default is True

    custom_entry = next(entry for entry in entries if entry.display_name == "customElement.CustomCPU")
    assert custom_entry.enabled_by_default is False


def test_describe_component_metadata_diff_lists_changed_fields(sst_env):
    env = sst_env

    baseline_catalog = make_catalog(
        "16.0.0",
        [
            cache_component(default_line_size="64"),
        ],
    )
    discovered_catalog = make_catalog(
        "16.0.0",
        [
            cache_component(default_line_size="128"),
            custom_cpu_component(),
        ],
    )

    cache_key = "memHierarchy.Cache|component"
    diff = env.component_catalog.describe_component_metadata_diff(
        key=cache_key,
        baseline_catalog=baseline_catalog,
        discovered_catalog=discovered_catalog,
    )

    assert diff.status == "changed"
    assert any("Changed parameters" in line for line in diff.lines)
    assert "cache_line_size" in "\n".join(diff.lines)

    custom_diff = env.component_catalog.describe_component_metadata_diff(
        key="customElement.CustomCPU|component",
        baseline_catalog=baseline_catalog,
        discovered_catalog=discovered_catalog,
    )

    assert custom_diff.status == "custom"
    assert "not part of the bundled baseline catalog" in "\n".join(custom_diff.lines)

