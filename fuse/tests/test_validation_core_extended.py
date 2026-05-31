from types import SimpleNamespace

from fuse.core.model.models import ModelLink, ModelSubcompAttachment
from fuse.core.model.validation import (
    effective_parameter_value,
    normalize_default_value,
    validate_links,
    validate_plugin_links,
    validate_required_component_parameters,
    validate_subcomp_attachments,
    validate_unique_names,
)


class FakeScene:
    def __init__(self, nodes=None, links=None, attachments=None, active_plugin_id=""):
        self._nodes = nodes or []
        self.links = links or []
        self.subcomp_attachments = attachments or []
        self.active_plugin_id = active_plugin_id

    def component_items(self):
        return list(self._nodes)


def make_node(node_id, name, parameters=None, component=None):
    if component is None:
        component = SimpleNamespace(component_id="comp", plugin_id="sst", target_id="1")
    return SimpleNamespace(
        node_id=node_id,
        instance_name=name,
        parameters=parameters or {},
        component=component,
    )


def make_link(**overrides):
    values = {
        "link_id": 1,
        "name": "link0",
        "source_node_id": 1,
        "source_component_name": "src",
        "source_port": "out",
        "target_node_id": 2,
        "target_component_name": "dst",
        "target_port": "in",
    }
    values.update(overrides)
    return ModelLink(**values)


def test_normalize_default_value_treats_required_marker_and_none_as_empty():
    assert normalize_default_value(None) == ""
    assert normalize_default_value("<required>") == ""
    assert normalize_default_value(123) == "123"


def test_effective_parameter_value_uses_node_override_before_default():
    node = make_node(1, "n", parameters={"clock": " 2GHz "})
    parameter = {"name": "clock", "default_val": "1GHz"}

    assert effective_parameter_value(node, parameter) == "2GHz"


def test_effective_parameter_value_uses_normalized_default_when_missing():
    node = make_node(1, "n", parameters={})

    assert effective_parameter_value(node, {"name": "clock", "default_val": "<required>"}) == ""
    assert effective_parameter_value(node, {"name": "clock", "default_val": "1GHz"}) == "1GHz"


def test_validate_unique_names_flags_empty_component_and_link_names():
    scene = FakeScene(nodes=[make_node(1, "   ")], links=[make_link(name="")])

    issues = validate_unique_names(scene)

    assert {issue.issue_type for issue in issues} == {"component_name", "link_name"}
    assert any(issue.object_name == "<unnamed component>" for issue in issues)
    assert any(issue.object_name == "<unnamed link>" for issue in issues)


def test_validate_unique_names_flags_component_link_name_collisions():
    scene = FakeScene(nodes=[make_node(1, "shared")], links=[make_link(name="shared")])

    issues = validate_unique_names(scene)

    assert len(issues) == 2
    assert {issue.issue_type for issue in issues} == {"component_name", "link_name"}


def test_validate_required_component_parameters_supports_target_aware_lookup(monkeypatch):
    import fuse.core.model.validation as validation_module

    calls = []

    def fake_get_component_details(plugin_id, component_id, target_id):
        calls.append((plugin_id, component_id, target_id))
        return {"parameters": [{"name": "clock", "default_val": "<required>", "required": True}]}

    monkeypatch.setattr(validation_module, "get_component_details", fake_get_component_details)
    scene = FakeScene(nodes=[make_node(1, "node", parameters={})])

    issues = validate_required_component_parameters(scene)

    assert calls == [("sst", "comp", "1")]
    assert len(issues) == 1
    assert issues[0].parameter_name == "clock"


def test_validate_required_component_parameters_falls_back_to_two_argument_lookup(monkeypatch):
    import fuse.core.model.validation as validation_module

    calls = []

    def fake_get_component_details(plugin_id, component_id):
        calls.append((plugin_id, component_id))
        return {"parameters": [{"name": "clock", "default_val": "1GHz", "required": True}]}

    monkeypatch.setattr(validation_module, "get_component_details", fake_get_component_details)
    scene = FakeScene(nodes=[make_node(1, "node", parameters={})])

    issues = validate_required_component_parameters(scene)

    assert calls == [("sst", "comp")]
    assert issues == []


def test_validate_required_component_parameters_ignores_lookup_failures(monkeypatch):
    import fuse.core.model.validation as validation_module

    def fake_get_component_details(plugin_id, component_id, target_id):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(validation_module, "get_component_details", fake_get_component_details)

    assert validate_required_component_parameters(FakeScene(nodes=[make_node(1, "node")])) == []


def test_validate_links_requires_both_endpoint_latencies():
    scene = FakeScene(links=[make_link(source_latency="", target_latency="  ")])

    issues = validate_links(scene)

    assert [issue.parameter_name for issue in issues] == ["source_latency", "target_latency"]


def test_validate_subcomp_attachments_flags_missing_nodes_duplicate_slots_duplicate_children_and_interface_mismatch():
    scene = FakeScene(
        nodes=[make_node(1, "parent"), make_node(2, "child")],
        attachments=[
            ModelSubcompAttachment(1, "a1", 1, "parent", "slot", 2, "child", "ifaceA", "ifaceA"),
            ModelSubcompAttachment(2, "a2", 1, "parent", "slot", 2, "child", "ifaceA", "ifaceB"),
            ModelSubcompAttachment(3, "a3", 99, "missing", "other", 100, "missingChild"),
        ],
    )

    issues = validate_subcomp_attachments(scene)
    messages = "\n".join(issue.message for issue in issues)

    assert "parent node does not exist" in messages
    assert "child node does not exist" in messages
    assert "assigned more than once" in messages
    assert "more than one parent" in messages
    assert "interface mismatch" in messages


def test_validate_plugin_links_skips_without_active_plugin_or_missing_plugin(monkeypatch):
    import fuse.core.model.validation as validation_module

    monkeypatch.setattr(validation_module, "get_plugin_by_id", lambda plugin_id: (_ for _ in ()).throw(KeyError(plugin_id)))

    assert validate_plugin_links(FakeScene(active_plugin_id="")) == []
    assert validate_plugin_links(FakeScene(active_plugin_id="missing")) == []


def test_validate_plugin_links_delegates_to_active_plugin(monkeypatch):
    import fuse.core.model.validation as validation_module

    expected_issue = object()

    class Plugin:
        def validate_links(self, scene):
            return [expected_issue]

    monkeypatch.setattr(validation_module, "get_plugin_by_id", lambda plugin_id: Plugin())

    assert validate_plugin_links(FakeScene(active_plugin_id="sst")) == [expected_issue]
