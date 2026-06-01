from types import SimpleNamespace

import pytest

from fuse.core.model.project_settings import PluginProjectSettings, ToolchainSettings
from fuse.core.toolchains.providers import CommandExecutionResult
from fuse.plugins.community.gem5.plugin import (
    BUILTIN_GEM5_COMPONENTS,
    Gem5Plugin,
    gem5_command_from_toolchain,
    validate_gem5_toolchain,
)


def test_gem5_command_from_toolchain_prefers_configured_binary_paths():
    assert gem5_command_from_toolchain(ToolchainSettings()) == ["gem5"]
    assert gem5_command_from_toolchain(ToolchainSettings(tool_paths={"gem5Binary": "/a/gem5"})) == ["/a/gem5"]
    assert gem5_command_from_toolchain(ToolchainSettings(tool_paths={"remoteGem5Binary": "/r/gem5"})) == ["/r/gem5"]


def test_validate_gem5_toolchain_success(monkeypatch):
    class Provider:
        def run(self, command, timeout_seconds=60):
            return CommandExecutionResult(command, 0, "gem5 version 25.1.0.1", "")

    monkeypatch.setattr("fuse.plugins.community.gem5.plugin.provider_from_toolchain", lambda toolchain: Provider())

    ok, message, output = validate_gem5_toolchain(
        ToolchainSettings(tool_paths={"gem5Binary": "/bin/gem5"}),
        expected_version="25.1.0.1",
    )

    assert ok is True
    assert "/bin/gem5 --version" in message
    assert output == "gem5 version 25.1.0.1"


def test_validate_gem5_toolchain_reports_command_failure(monkeypatch):
    class Provider:
        def run(self, command, timeout_seconds=60):
            return CommandExecutionResult(command, 127, "", "missing", backend="ssh", host="hpc")

    monkeypatch.setattr("fuse.plugins.community.gem5.plugin.provider_from_toolchain", lambda toolchain: Provider())

    ok, message, output = validate_gem5_toolchain(ToolchainSettings())

    assert ok is False
    assert "gem5 validation failed" in message
    assert "Backend: ssh" in message
    assert "Host: hpc" in message
    assert output == "missing"


def test_validate_gem5_toolchain_rejects_non_gem5_output(monkeypatch):
    class Provider:
        def run(self, command, timeout_seconds=60):
            return CommandExecutionResult(command, 0, "python 3.13", "")

    monkeypatch.setattr("fuse.plugins.community.gem5.plugin.provider_from_toolchain", lambda toolchain: Provider())

    ok, message, _ = validate_gem5_toolchain(ToolchainSettings())

    assert ok is False
    assert "does not look like gem5" in message


def test_validate_gem5_toolchain_rejects_unexpected_version(monkeypatch):
    class Provider:
        def run(self, command, timeout_seconds=60):
            return CommandExecutionResult(command, 0, "gem5 version 24.1.0.3", "")

    monkeypatch.setattr("fuse.plugins.community.gem5.plugin.provider_from_toolchain", lambda toolchain: Provider())

    ok, message, output = validate_gem5_toolchain(ToolchainSettings(), expected_version="25.1.0.1")

    assert ok is False
    assert "reported a different version" in message
    assert output == "gem5 version 24.1.0.3"


def test_gem5_plugin_load_item_details_maps_connectors_and_properties(monkeypatch):
    target = SimpleNamespace(
        target_id="1",
        display_name="gem5 25",
        framework_version="25.1.0.1",
    )
    plugin = Gem5Plugin()
    monkeypatch.setattr(plugin, "list_targets", lambda: [target])

    details = plugin.load_item_details("timing_simple_cpu", target_id="1")

    assert details.palette_item.type_name == "TimingSimpleCPU"
    assert details.palette_item.target_label == "gem5 25"
    assert [connector.name for connector in details.connectors] == ["icache_port", "dcache_port"]
    assert {prop.name: prop.required for prop in details.properties}["clock"] is True


def test_gem5_plugin_load_item_details_raises_for_unknown_item(monkeypatch):
    plugin = Gem5Plugin()
    monkeypatch.setattr(plugin, "list_targets", lambda: [])

    with pytest.raises(KeyError, match="not implemented"):
        plugin.load_item_details("missing")


def test_gem5_plugin_validate_toolchain_delegates_to_validation_helper(monkeypatch):
    calls = []

    def fake_validate(toolchain, expected_version, timeout_seconds):
        calls.append((toolchain, expected_version, timeout_seconds))
        return True, "ok", "gem5 version"

    monkeypatch.setattr("fuse.plugins.community.gem5.plugin.validate_gem5_toolchain", fake_validate)

    settings = PluginProjectSettings(
        plugin_id="gem5",
        framework_version="25.1.0.1",
        toolchain=ToolchainSettings(tool_paths={"gem5Binary": "/bin/gem5"}),
    )
    ok, message = Gem5Plugin().validate_toolchain(settings)

    assert ok is True
    assert message == "ok"
    assert calls == [(settings.toolchain, "25.1.0.1", 60)]


def test_gem5_builtin_catalog_has_unique_item_ids_and_required_fields():
    assert len(BUILTIN_GEM5_COMPONENTS) == len(set(BUILTIN_GEM5_COMPONENTS))
    for item_id, metadata in BUILTIN_GEM5_COMPONENTS.items():
        assert item_id
        assert metadata["display_name"].startswith("gem5.")
        assert metadata["type_name"]
        assert metadata["connectors"]
        assert metadata["properties"]


def test_gem5_link_compatibility_allows_request_to_response_ports():
    from fuse.plugin_api.interfaces import LinkEndpoint

    plugin = Gem5Plugin()
    result = plugin.check_link_compatibility(
        LinkEndpoint("cpu", "dcache_port", {"iface": "request_port"}),
        LinkEndpoint("xbar", "cpu_side_ports", {"iface": "response_port"}),
    )

    assert result.is_ok
    assert result.can_create


def test_gem5_link_compatibility_rejects_same_direction_ports():
    from fuse.plugin_api.interfaces import LinkEndpoint

    plugin = Gem5Plugin()
    result = plugin.check_link_compatibility(
        LinkEndpoint("cpu0", "dcache_port", {"iface": "request_port"}),
        LinkEndpoint("cpu1", "icache_port", {"iface": "request_port"}),
    )

    assert result.is_error
    assert not result.can_create
    assert "cannot be linked" in result.message


def test_gem5_export_validation_requires_system_component():
    plugin = Gem5Plugin()
    node = SimpleNamespace(
        component=SimpleNamespace(plugin_id="gem5", name="TimingSimpleCPU"),
    )
    scene = SimpleNamespace(component_items=lambda: [node])

    issues = plugin.validate_export(scene)

    assert any("System component" in issue.message for issue in issues)

class FakePort:
    def __init__(self, name, iface):
        self.name = name
        self.metadata = {"iface": iface}


def _gem5_node(node_id, name, type_name, ports, parameters=None, target_id="1"):
    return SimpleNamespace(
        node_id=node_id,
        instance_name=name,
        parameters=parameters or {},
        component=SimpleNamespace(
            plugin_id="gem5",
            name=type_name,
            target_id=target_id,
        ),
        ports=[FakePort(port_name, iface) for port_name, iface in ports],
    )


def _valid_gem5_scene():
    from fuse.core.model.models import ModelLink

    system = _gem5_node(
        1,
        "system0",
        "System",
        [("system_port", "request_port")],
        {"clock": "1GHz", "mem_ranges": "512MiB"},
    )
    cpu = _gem5_node(
        2,
        "cpu0",
        "TimingSimpleCPU",
        [("icache_port", "request_port"), ("dcache_port", "request_port")],
        {"clock": "2GHz"},
    )
    xbar = _gem5_node(
        3,
        "membus",
        "SystemXBar",
        [("cpu_side_ports", "response_port"), ("mem_side_ports", "request_port")],
    )
    memory = _gem5_node(
        4,
        "mem0",
        "DDR3_1600_8x8",
        [("port", "response_port")],
        {"range": "512MiB"},
    )
    links = [
        ModelLink(1, "icache", 2, "cpu0", "icache_port", 3, "membus", "cpu_side_ports", plugin_id="gem5"),
        ModelLink(2, "dcache", 2, "cpu0", "dcache_port", 3, "membus", "cpu_side_ports", plugin_id="gem5"),
        ModelLink(3, "mem", 3, "membus", "mem_side_ports", 4, "mem0", "port", plugin_id="gem5"),
    ]
    return SimpleNamespace(
        component_items=lambda: [system, cpu, xbar, memory],
        links=links,
        subcomp_attachments=[],
    )


def test_gem5_export_validation_accepts_minimal_connected_system():
    issues = Gem5Plugin().validate_export(_valid_gem5_scene())

    assert issues == []


def test_gem5_export_validation_reports_missing_topology_parts():
    scene = SimpleNamespace(
        component_items=lambda: [
            _gem5_node(1, "system0", "System", [("system_port", "request_port")]),
            _gem5_node(2, "cpu0", "TimingSimpleCPU", [("icache_port", "request_port"), ("dcache_port", "request_port")]),
        ],
        links=[],
        subcomp_attachments=[],
    )

    messages = "\n".join(issue.message for issue in Gem5Plugin().validate_export(scene))

    assert "CPU port 'icache_port' must be connected" in messages
    assert "CPU port 'dcache_port' must be connected" in messages
    assert "SystemXBar interconnect" in messages
    assert "memory controller/DRAM" in messages


def test_gem5_export_validation_rejects_mixed_target_versions():
    scene = _valid_gem5_scene()
    scene.component_items()[1].component.target_id = "2"

    messages = "\n".join(issue.message for issue in Gem5Plugin().validate_export(scene))

    assert "same target/version" in messages


def test_build_gem5_python_exports_connected_model(tmp_path):
    from fuse.plugins.community.gem5.export_python import build_gem5_python, export_gem5_python

    text = build_gem5_python(_valid_gem5_scene())

    assert "system = System()" in text
    assert "system.cpu0 = TimingSimpleCPU()" in text
    assert "system.membus = SystemXBar()" in text
    assert "system.mem0 = MemCtrl()" in text
    assert "system.cpu0.icache_port = system.membus.cpu_side_ports" in text
    assert "system.cpu0.dcache_port = system.membus.cpu_side_ports" in text
    assert "system.membus.mem_side_ports = system.mem0.port" in text
    assert "root = Root(full_system=False, system=system)" in text

    output = tmp_path / "model.py"
    export_gem5_python(_valid_gem5_scene(), output)
    assert output.read_text(encoding="utf-8") == text
