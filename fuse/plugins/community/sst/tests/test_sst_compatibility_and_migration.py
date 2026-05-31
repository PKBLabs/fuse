from types import SimpleNamespace

from fuse.core.model.models import ModelLink
from fuse.plugins.community.sst.compatibility import (
    TargetComponentMatch,
    format_compatibility_report,
    validate_scene_for_target,
)
from fuse.plugins.community.sst.migration import apply_scene_migration, plan_scene_migration


class FakeScene:
    def __init__(self, nodes=None, links=None):
        self._nodes = nodes or []
        self.links = links or []
        self.rerouted = False

    def component_items(self):
        return list(self._nodes)

    def reroute_all_links(self):
        self.rerouted = True


def make_component(
    element="memHierarchy",
    name="Cache",
    plugin_id="sst",
    target_id="1",
    is_subcomp=0,
):
    return SimpleNamespace(
        element=element,
        name=name,
        plugin_id=plugin_id,
        target_id=target_id,
        is_subcomp=is_subcomp,
        category="Memory",
        iface="",
        icon_path="old.svg",
        component_id="old-id",
        target_label="Old Target",
        framework_version="15.0.0",
    )


def make_node(node_id=1, instance_name="cache0", parameters=None, component=None):
    return SimpleNamespace(
        node_id=node_id,
        instance_name=instance_name,
        parameters=parameters or {},
        component=component or make_component(),
        set_icon_path=lambda path: setattr(component or make_component(), "set_icon_called_with", path),
    )


def match(component_id=10, framework_version_id=2):
    return TargetComponentMatch(
        component_id=component_id,
        framework_version_id=framework_version_id,
        element_name="memHierarchy",
        component_name="Cache",
        is_subcomp=0,
        category="Memory",
        iface="",
        icon_path="cache.svg",
        framework_version="16.0.0",
        target_label="SST 16",
    )


def details(required_value="1GHz"):
    return {
        "parameters": [
            {"name": "clock", "default_val": required_value, "required": True},
            {"name": "replacement", "default_val": "lru", "required": False},
        ],
        "ports": [{"name": "high"}, {"name": "low"}],
    }


def test_validate_scene_for_target_reports_incomplete_identity(monkeypatch):
    node = make_node(component=make_component(element="", name="Cache"))
    scene = FakeScene(nodes=[node])

    report = validate_scene_for_target(scene, target_id="2")

    assert report.has_errors
    assert "identity is incomplete" in report.issues[0].message


def test_validate_scene_for_target_reports_missing_target_component(monkeypatch):
    import fuse.plugins.community.sst.compatibility as compatibility

    monkeypatch.setattr(compatibility, "find_target_component", lambda *args, **kwargs: None)
    scene = FakeScene(nodes=[make_node()])

    report = validate_scene_for_target(scene, target_id="2")

    assert report.has_errors
    assert "is not available" in report.issues[0].message


def test_validate_scene_for_target_warns_unknown_parameter_and_errors_missing_required(monkeypatch):
    import fuse.plugins.community.sst.compatibility as compatibility

    monkeypatch.setattr(compatibility, "find_target_component", lambda *args, **kwargs: match())
    monkeypatch.setattr(compatibility, "get_component_details", lambda *args, **kwargs: details("<required>"))
    scene = FakeScene(nodes=[make_node(parameters={"stale": "value"})])

    report = validate_scene_for_target(scene, target_id="2")

    severities = [issue.severity for issue in report.issues]
    assert "warning" in severities
    assert "error" in severities
    assert any(issue.parameter_name == "stale" for issue in report.issues)
    assert any(issue.parameter_name == "clock" for issue in report.issues)


def test_validate_scene_for_target_reports_missing_connected_ports(monkeypatch):
    import fuse.plugins.community.sst.compatibility as compatibility

    source = make_node(node_id=1, instance_name="src")
    target = make_node(node_id=2, instance_name="dst")
    link = ModelLink(1, "l0", 1, "src", "missing_src", 2, "dst", "missing_dst")
    scene = FakeScene(nodes=[source, target], links=[link])
    monkeypatch.setattr(compatibility, "find_target_component", lambda *args, **kwargs: match())
    monkeypatch.setattr(compatibility, "get_component_details", lambda *args, **kwargs: details())

    report = validate_scene_for_target(scene, target_id="2")

    assert len([issue for issue in report.issues if issue.link_id == 1]) == 2
    assert report.has_errors


def test_validate_scene_for_target_ignores_cross_plugin_links_after_missing_endpoint_checks(monkeypatch):
    import fuse.plugins.community.sst.compatibility as compatibility

    sst_node = make_node(node_id=1)
    gem5_node = make_node(node_id=2, component=make_component(plugin_id="gem5"))
    link = ModelLink(1, "cross", 1, "sst", "absent", 2, "gem5", "absent")
    scene = FakeScene(nodes=[sst_node, gem5_node], links=[link])
    monkeypatch.setattr(compatibility, "find_target_component", lambda *args, **kwargs: match())
    monkeypatch.setattr(compatibility, "get_component_details", lambda *args, **kwargs: details())

    report = validate_scene_for_target(scene, target_id="2")

    assert not any(issue.link_id == 1 for issue in report.issues)


def test_validate_scene_for_target_reports_links_to_deleted_nodes(monkeypatch):
    import fuse.plugins.community.sst.compatibility as compatibility

    scene = FakeScene(nodes=[make_node(node_id=1)], links=[ModelLink(1, "dangling", 1, "src", "high", 99, "dst", "low")])
    monkeypatch.setattr(compatibility, "find_target_component", lambda *args, **kwargs: match())
    monkeypatch.setattr(compatibility, "get_component_details", lambda *args, **kwargs: details())

    report = validate_scene_for_target(scene, target_id="2")

    assert report.has_errors
    assert "Target component no longer exists" in report.issues[0].message


def test_format_compatibility_report_limits_output_and_reports_extra_count():
    from fuse.plugin_api.interfaces import CompatibilityIssue, CompatibilityReport

    report = CompatibilityReport(plugin_id="sst", destination_target_id="2")
    report.issues = [CompatibilityIssue("warning", f"node{i}", "issue") for i in range(3)]

    text = format_compatibility_report(report, limit=2)

    assert "Compatibility check for target 2" in text
    assert "[WARNING] node0" in text
    assert "...and 1 more issue" in text


def test_plan_scene_migration_builds_updates_and_drops_stale_parameters(monkeypatch):
    import fuse.plugins.community.sst.migration as migration

    node = make_node(parameters={"clock": "2GHz", "stale": "remove-me"})
    scene = FakeScene(nodes=[node])
    monkeypatch.setattr(migration, "find_target_component", lambda *args, **kwargs: match(component_id=42))
    monkeypatch.setattr(migration, "get_component_details", lambda *args, **kwargs: details())
    monkeypatch.setattr(migration, "validate_scene_for_target", lambda *args, **kwargs: __import__("fuse.plugin_api.interfaces", fromlist=["CompatibilityReport"]).CompatibilityReport(plugin_id="sst", source_target_id="1", destination_target_id="2"))

    plan = plan_scene_migration(scene, target_id="2")

    assert plan.can_apply
    assert plan.source_target_id == "1"
    assert plan.node_updates == [
        {
            "node_id": 1,
            "component_id": "42",
            "target_id": "2",
            "target_label": "SST 16",
            "framework_version": "16.0.0",
            "element": "memHierarchy",
            "name": "Cache",
            "is_subcomp": 0,
            "category": "Memory",
            "iface": "",
            "icon_path": "cache.svg",
            "parameters": {"clock": "2GHz", "replacement": "lru"},
        }
    ]


def test_plan_scene_migration_stops_when_compatibility_has_errors(monkeypatch):
    import fuse.plugins.community.sst.migration as migration
    from fuse.plugin_api.interfaces import CompatibilityIssue, CompatibilityReport

    report = CompatibilityReport(plugin_id="sst")
    report.issues.append(CompatibilityIssue("error", "node", "not portable"))
    monkeypatch.setattr(migration, "validate_scene_for_target", lambda *args, **kwargs: report)

    plan = plan_scene_migration(FakeScene(nodes=[make_node()]), target_id="2")

    assert not plan.can_apply
    assert plan.node_updates == []


def test_apply_scene_migration_mutates_component_parameters_and_reroutes(monkeypatch):
    import fuse.plugins.community.sst.migration as migration
    from fuse.plugin_api.interfaces import CompatibilityReport

    component = make_component()
    node = make_node(component=component, parameters={"clock": "2GHz"})
    scene = FakeScene(nodes=[node])
    monkeypatch.setattr(migration, "find_target_component", lambda *args, **kwargs: match(component_id=77))
    monkeypatch.setattr(migration, "get_component_details", lambda *args, **kwargs: details())
    monkeypatch.setattr(migration, "validate_scene_for_target", lambda *args, **kwargs: CompatibilityReport(plugin_id="sst", source_target_id="1", destination_target_id="2"))

    plan = apply_scene_migration(scene, target_id="2")

    assert plan.can_apply
    assert component.component_id == "77"
    assert component.target_id == "2"
    assert component.target_label == "SST 16"
    assert component.framework_version == "16.0.0"
    assert node.parameters == {"clock": "2GHz", "replacement": "lru"}
    assert scene.rerouted is True
