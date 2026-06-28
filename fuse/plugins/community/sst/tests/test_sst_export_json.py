# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.

import json

from PySide6.QtCore import QPointF


def make_component_definition(element: str, name: str, component_id: str):
    from fuse.core.model.models import ComponentDefinition

    return ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        target_label="SST 15.0.0",
        framework_version="15.0.0",
        component_id=component_id,
        element=element,
        name=name,
        category="TEST",
        display_name_override=f"{element}.{name}",
    )


def add_test_node(scene, component, instance_name: str, x: float, y: float, parameters=None):
    from fuse.core.ui.graphics_items import ComponentNodeItem

    node = ComponentNodeItem(
        component=component,
        instance_name=instance_name,
        parameters=parameters or {},
    )

    node.setPos(QPointF(x, y))
    scene.addItem(node)

    return node


def test_build_sst_json_exports_components(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    scene = ModelScene()

    component = make_component_definition(
        element="memHierarchy",
        name="Cache",
        component_id="1",
    )

    add_test_node(
        scene,
        component,
        "cache0",
        100,
        200,
        {
            "cache_size": "32KiB",
            "associativity": "8",
            "empty_param": "",
        },
    )

    data = build_sst_json_dict(scene)

    assert list(data.keys()) == [
        "program_options",
        "statistics_options",
        "components",
        "statistics_group",
        "links",
    ]
    assert "shared_params" not in data

    assert len(data["components"]) == 1

    exported_component = data["components"][0]

    assert exported_component["name"] == "cache0"
    assert exported_component["type"] == "memHierarchy.Cache"
    assert exported_component["params"] == {
        "cache_size": "32KiB",
        "associativity": "8",
    }


def test_build_sst_json_exports_links(qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.model.models import ModelLink
    from fuse.core.ui.graphics_items import ConnectionItem
    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    scene = ModelScene()

    cpu_component = make_component_definition("simpleElementExample", "example0", "1")
    cache_component = make_component_definition("simpleElementExample", "example1", "2")

    cpu_node = add_test_node(scene, cpu_component, "cpu0", 100, 100, {})
    cache_node = add_test_node(scene, cache_component, "cache0", 400, 100, {})

    cpu_out = next(port for port in cpu_node.ports if port.name == "out")
    cache_in = next(port for port in cache_node.ports if port.name == "in")

    link = ModelLink(
        link_id=1,
        name="link_cpu_cache",
        source_node_id=cpu_node.node_id,
        source_component_name="cpu0",
        source_port="out",
        target_node_id=cache_node.node_id,
        target_component_name="cache0",
        target_port="in",
        source_latency="1ns",
        target_latency="1ns",
    )

    scene.addItem(ConnectionItem(link, cpu_out, cache_in))
    scene.links.append(link)

    data = build_sst_json_dict(scene)

    assert len(data["links"]) == 1

    exported_link = data["links"][0]

    assert exported_link == {
        "name": "link_cpu_cache",
        "noCut": False,
        "nonlocal": False,
        "left": {
            "component": "cpu0",
            "port": "out",
            "latency": "1ns",
        },
        "right": {
            "component": "cache0",
            "port": "in",
            "latency": "1ns",
        },
    }


def test_export_sst_json_writes_file(tmp_path, qtbot, monkeypatch):
    monkeypatch.setattr(
        "fuse.core.ui.graphics_items.load_port_names_for_component",
        lambda plugin_id, component_id, target_id=None: ["in", "out"],
    )

    from fuse.core.ui.model_scene import ModelScene
    from fuse.plugins.community.sst.export_json import export_sst_json

    scene = ModelScene()

    component = make_component_definition(
        element="memHierarchy",
        name="Cache",
        component_id="1",
    )

    add_test_node(
        scene,
        component,
        "cache0",
        100,
        200,
        {"cache_size": "32KiB"},
    )

    output_path = tmp_path / "model.sst.json"

    export_sst_json(scene, output_path)

    assert output_path.exists()

    data = json.loads(output_path.read_text(encoding="utf-8"))

    assert data["components"][0]["name"] == "cache0"
    assert data["components"][0]["type"] == "memHierarchy.Cache"

def _fake_node(node_id, instance_name, component, parameters=None, ports=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        node_id=node_id,
        instance_name=instance_name,
        component=component,
        parameters=parameters or {},
        ports=[SimpleNamespace(name=name) for name in (ports or [])],
    )


class _FakeScene:
    def __init__(self, nodes, links=None, attachments=None):
        self._nodes = list(nodes)
        self.links = list(links or [])
        self.subcomp_attachments = list(attachments or [])

    def component_items(self):
        return list(self._nodes)


def test_validate_sst_json_export_rejects_unexportable_graph():
    from fuse.core.model.models import ComponentDefinition, ModelLink
    from fuse.plugins.community.sst.export_json import validate_sst_json_export

    sst_component = ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        element="memHierarchy",
        name="Cache",
    )
    gem5_component = ComponentDefinition(
        plugin_id="gem5",
        target_id="1",
        element="gem5",
        name="System",
    )
    subcomponent = ComponentDefinition(
        plugin_id="sst",
        target_id="1",
        element="mmu",
        name="simpleMMU",
        is_subcomp=1,
    )
    cache = _fake_node(1, "cache0", sst_component, ports=["highlink"])
    gem5 = _fake_node(2, "system0", gem5_component)
    orphan_subcomp = _fake_node(3, "mmu0", subcomponent)
    broken_link = ModelLink(
        1,
        "broken",
        1,
        "cache0",
        "highlink",
        99,
        "missing",
        "port",
    )

    report = validate_sst_json_export(_FakeScene([cache, gem5, orphan_subcomp], [broken_link]))

    messages = "\n".join(issue.message for issue in report.errors)
    assert not report.can_export
    assert "only include SST components" in messages
    assert "must be attached" in messages
    assert "target component no longer exists" in messages


def test_validate_sst_json_export_collects_uncertain_connection_warnings():
    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.export_json import validate_sst_json_export

    component = make_component_definition("memHierarchy", "Cache", "1")
    source = _fake_node(1, "cache0", component, ports=["known"])
    target = _fake_node(2, "cache1", component, ports=["lowlink"])
    link = ModelLink(
        1,
        "uncertain",
        1,
        "cache0",
        "missing_port",
        2,
        "cache1",
        "lowlink",
        compatibility_severity="warning",
        compatibility_message="Interface metadata was incomplete.",
    )

    report = validate_sst_json_export(_FakeScene([source, target], [link]))

    assert report.can_export
    assert len(report.errors) == 0
    warning_text = "\n".join(issue.message for issue in report.warnings)
    assert "missing_port" in warning_text
    assert "Interface metadata was incomplete" in warning_text


def test_build_sst_json_resolves_current_component_names_and_deterministic_order():
    from fuse.core.model.models import ModelLink, ModelSubcompAttachment
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    cpu_component = make_component_definition("prospero", "prosperoCPU", "1")
    cache_component = make_component_definition("memHierarchy", "Cache", "2")
    subcomponent = make_component_definition("mmu", "simpleMMU", "3")
    subcomponent.is_subcomp = 1
    cpu = _fake_node(2, "cpu0_renamed", cpu_component, {"zeta": "last", "clock": "2GHz"}, ["cache"])
    cache = _fake_node(1, "cache0", cache_component, {"cache_size": "32KiB"}, ["highlink"])
    mmu = _fake_node(3, "mmu0", subcomponent, {"page_size": "4096"})
    link = ModelLink(
        5,
        "z_link_cpu_cache",
        2,
        "old_cpu_name",
        "cache",
        1,
        "old_cache_name",
        "highlink",
        source_latency="250ps",
        target_latency="1ns",
    )
    attachment = ModelSubcompAttachment(
        1,
        "attach_mmu",
        2,
        "cpu0_renamed",
        "mmu",
        3,
        "mmu0",
        "SST::MMU",
        "SST::MMU",
    )

    data = build_sst_json_dict(_FakeScene([cache, cpu, mmu], [link], [attachment]))

    assert [component["name"] for component in data["components"]] == ["cache0", "cpu0_renamed"]
    assert data["components"][1]["params"] == {"clock": "2GHz", "zeta": "last"}
    assert data["components"][1]["subcomponents"][0]["slot_name"] == "mmu"
    assert data["links"] == [
        {
            "name": "z_link_cpu_cache",
            "noCut": False,
            "nonlocal": False,
            "left": {"component": "cpu0_renamed", "port": "cache", "latency": "250ps"},
            "right": {"component": "cache0", "port": "highlink", "latency": "1ns"},
        }
    ]


def test_export_sst_json_blocks_errors_and_can_write_warning_report(tmp_path):
    import pytest

    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.export_json import SSTJsonExportError, export_sst_json

    component = make_component_definition("memHierarchy", "Cache", "1")
    source = _fake_node(1, "cache0", component, ports=["known"])
    target = _fake_node(2, "cache1", component, ports=["lowlink"])
    warning_link = ModelLink(1, "warn", 1, "cache0", "unknown", 2, "cache1", "lowlink")
    report_path = tmp_path / "model.sst.export-report.json"
    output_path = tmp_path / "model.sst.json"

    export_sst_json(_FakeScene([source, target], [warning_link]), output_path, report_path=report_path)

    assert output_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["canExport"] is True
    assert report["warnings"]

    broken = ModelLink(2, "broken", 1, "cache0", "known", 99, "missing", "port")
    with pytest.raises(SSTJsonExportError, match="not ready for SST JSON export"):
        export_sst_json(_FakeScene([source], [broken]), tmp_path / "broken.json")


def test_sst_plugin_advertises_plugin_owned_json_export_format():
    from fuse.plugins.community.sst.plugin import SSTPlugin

    formats = SSTPlugin().export_formats()

    assert len(formats) == 1
    fmt = formats[0]
    assert fmt.format_id == "sst.json"
    assert fmt.display_name == "SST JSON"
    assert fmt.default_suffix == ".sst.json"
    assert "SST JSON" in fmt.file_filter


def test_sst_plugin_export_model_writes_json_and_warning_report(tmp_path):
    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.plugin import SSTPlugin

    component = make_component_definition("memHierarchy", "Cache", "1")
    source = _fake_node(1, "cache0", component, ports=["known"])
    target = _fake_node(2, "cache1", component, ports=["lowlink"])
    warning_link = ModelLink(1, "warn", 1, "cache0", "unknown", 2, "cache1", "lowlink")
    output_path = tmp_path / "model.sst.json"

    result = SSTPlugin().export_model(
        _FakeScene([source, target], [warning_link]),
        output_path,
        format_id="sst.json",
    )

    assert output_path.exists()
    assert result.output_path == str(output_path)
    assert result.format_id == "sst.json"
    assert "warning" in result.message.lower()
    assert result.report_path
    report = json.loads(result.report_path and open(result.report_path, encoding="utf-8").read())
    assert report["canExport"] is True
    assert report["warnings"]


def test_sst_plugin_export_model_rejects_unknown_format(tmp_path):
    import pytest

    from fuse.plugins.community.sst.plugin import SSTPlugin

    with pytest.raises(ValueError, match="Unsupported SST export format"):
        SSTPlugin().export_model(_FakeScene([]), tmp_path / "model.json", format_id="sst.text")


def test_validate_sst_json_export_rejects_duplicate_or_missing_link_names():
    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.export_json import validate_sst_json_export

    component = make_component_definition("memHierarchy", "Cache", "1")
    source = _fake_node(1, "cache0", component, ports=["highlink"])
    target = _fake_node(2, "cache1", component, ports=["lowlink"])
    first = ModelLink(1, "dup", 1, "cache0", "highlink", 2, "cache1", "lowlink")
    second = ModelLink(2, "dup", 2, "cache1", "lowlink", 1, "cache0", "highlink")
    unnamed = ModelLink(3, "", 1, "cache0", "highlink", 2, "cache1", "lowlink")

    report = validate_sst_json_export(_FakeScene([source, target], [first, second, unnamed]))

    messages = "\n".join(issue.message for issue in report.errors)
    assert not report.can_export
    assert "link names to be unique" in messages
    assert "every link to have a stable name" in messages


def test_validate_sst_json_export_warns_when_link_latencies_are_defaulted():
    from fuse.core.model.models import ModelLink
    from fuse.plugins.community.sst.export_json import validate_sst_json_export

    component = make_component_definition("memHierarchy", "Cache", "1")
    source = _fake_node(1, "cache0", component, ports=["highlink"])
    target = _fake_node(2, "cache1", component, ports=["lowlink"])
    link = ModelLink(
        1,
        "cache_link",
        1,
        "cache0",
        "highlink",
        2,
        "cache1",
        "lowlink",
        source_latency="",
        target_latency="",
    )

    report = validate_sst_json_export(_FakeScene([source, target], [link]))

    assert report.can_export
    warning_text = "\n".join(issue.message for issue in report.warnings)
    assert "source latency was not set" in warning_text
    assert "target latency was not set" in warning_text
    assert "1ns" in warning_text


def test_full_sst_export_model_matches_golden_json_contract():
    from fuse.core.model.models import ModelLink, ModelSubcompAttachment
    from fuse.plugins.community.sst.export_json import build_sst_json_dict

    cpu_component = make_component_definition("prospero", "prosperoCPU", "1")
    cache_component = make_component_definition("memHierarchy", "Cache", "2")
    bus_component = make_component_definition("memHierarchy", "Bus", "3")
    mem_component = make_component_definition("memHierarchy", "MemController", "4")
    subcomponent = make_component_definition("mmu", "simpleMMU", "5")
    subcomponent.is_subcomp = 1

    cpu = _fake_node(
        1,
        "cpu_auto_1",
        cpu_component,
        {"clock": "2GHz", "empty": "", "verbose": False},
        ["cache", "mmu"],
    )
    cache = _fake_node(
        2,
        "l1_cache",
        cache_component,
        {"cache_size": "32KiB", "associativity": "8"},
        ["highlink", "lowlink"],
    )
    bus = _fake_node(3, "membus", bus_component, {"bus_frequency": "2GHz"}, ["highlink0", "lowlink0"])
    mem = _fake_node(4, "memory", mem_component, {"addr_range_start": "0", "addr_range_end": "0x100000"}, ["direct_link"])
    mmu = _fake_node(5, "cpu_mmu", subcomponent, {"page_size": "4096"}, [])

    links = [
        ModelLink(2, "link_cache_bus", 2, "l1_cache", "lowlink", 3, "membus", "highlink0", source_latency="500ps", target_latency="500ps"),
        ModelLink(1, "link_cpu_cache", 1, "cpu_auto_1", "cache", 2, "l1_cache", "highlink", source_latency="250ps", target_latency="1ns"),
        ModelLink(3, "link_bus_mem", 3, "membus", "lowlink0", 4, "memory", "direct_link", source_latency="1ns", target_latency="2ns"),
    ]
    attachments = [
        ModelSubcompAttachment(1, "attach_cpu_mmu", 1, "cpu_auto_1", "mmu", 5, "cpu_mmu", "SST::MMU", "SST::MMU")
    ]

    data = build_sst_json_dict(
        _FakeScene([mem, bus, cache, cpu, mmu], links, attachments),
        program_options={"timebase": "1ps"},
        statistics_options={"level": 1},
        shared_params=[{"name": "shared_clock", "params": {"clock": "2GHz"}}],
        statistics_group=[{"name": "default", "components": ["cpu_auto_1"]}],
    )

    assert data == {
        "program_options": {"timebase": "1ps"},
        "shared_params": [{"name": "shared_clock", "params": {"clock": "2GHz"}}],
        "statistics_options": {"level": 1},
        "components": [
            {
                "name": "cpu_auto_1",
                "type": "prospero.prosperoCPU",
                "params": {"clock": "2GHz", "verbose": False},
                "subcomponents": [
                    {
                        "name": "cpu_mmu",
                        "type": "mmu.simpleMMU",
                        "params": {"page_size": "4096"},
                        "slot_name": "mmu",
                    }
                ],
            },
            {
                "name": "l1_cache",
                "type": "memHierarchy.Cache",
                "params": {"associativity": "8", "cache_size": "32KiB"},
            },
            {
                "name": "membus",
                "type": "memHierarchy.Bus",
                "params": {"bus_frequency": "2GHz"},
            },
            {
                "name": "memory",
                "type": "memHierarchy.MemController",
                "params": {"addr_range_end": "0x100000", "addr_range_start": "0"},
            },
        ],
        "statistics_group": [{"name": "default", "components": ["cpu_auto_1"]}],
        "links": [
            {
                "name": "link_bus_mem",
                "noCut": False,
                "nonlocal": False,
                "left": {"component": "membus", "port": "lowlink0", "latency": "1ns"},
                "right": {"component": "memory", "port": "direct_link", "latency": "2ns"},
            },
            {
                "name": "link_cache_bus",
                "noCut": False,
                "nonlocal": False,
                "left": {"component": "l1_cache", "port": "lowlink", "latency": "500ps"},
                "right": {"component": "membus", "port": "highlink0", "latency": "500ps"},
            },
            {
                "name": "link_cpu_cache",
                "noCut": False,
                "nonlocal": False,
                "left": {"component": "cpu_auto_1", "port": "cache", "latency": "250ps"},
                "right": {"component": "l1_cache", "port": "highlink", "latency": "1ns"},
            },
        ],
    }
