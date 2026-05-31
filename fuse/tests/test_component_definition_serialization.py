# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.
#
# FUSE is free software: you can redistribute it and/or modify it under the
# terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or, at your option, any later
# version.
#
# FUSE is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR
# A PARTICULAR PURPOSE. See the GNU General Public License for more details.

import json

from fuse.core.model.models import ComponentDefinition, ModelLink, ModelSubcompAttachment


def test_component_definition_drag_json_preserves_plugin_target_and_display_metadata():
    component = ComponentDefinition(
        component_id=42,
        plugin_id="sst",
        target_id="15",
        target_label="SST 15.0.0",
        framework_version="15.0.0",
        element="memHierarchy",
        name="Cache",
        is_subcomp=0,
        category="MEMORY COMPONENT",
        functionality="cache hierarchy",
        description="L1/L2 cache",
        iface="",
        icon_path="core/resources/media/arch_component_icons/memory_cache_controller.png",
        display_name_override="memHierarchy.Cache (Component)",
    )

    payload = json.loads(component.to_drag_text())
    restored = ComponentDefinition.from_drag_text(component.to_drag_text())

    assert payload["plugin_id"] == "sst"
    assert payload["target_id"] == "15"
    assert payload["target_label"] == "SST 15.0.0"
    assert payload["framework_version"] == "15.0.0"
    assert restored.component_id == "42"
    assert restored.plugin_id == "sst"
    assert restored.target_id == "15"
    assert restored.target_label == "SST 15.0.0"
    assert restored.framework_version == "15.0.0"
    assert restored.icon_path.endswith("memory_cache_controller.png")
    assert restored.display_name == "memHierarchy.Cache (Component)"


def test_component_definition_reads_plugin_aware_pipe_drag_payload():
    restored = ComponentDefinition.from_drag_text(
        "7|gem5|cpu|TimingSimpleCPU|0|CPU||icons/cpu.png|gem5 CPU"
    )

    assert restored.component_id == "7"
    assert restored.plugin_id == "gem5"
    assert restored.element == "cpu"
    assert restored.name == "TimingSimpleCPU"
    assert restored.category == "CPU"
    assert restored.icon_path == "icons/cpu.png"
    assert restored.display_name == "gem5 CPU"


def test_component_definition_reads_legacy_sst_pipe_drag_payload():
    restored = ComponentDefinition.from_drag_text("3|memHierarchy|Cache|0|MEMORY|")

    assert restored.component_id == "3"
    assert restored.plugin_id == "sst"
    assert restored.element == "memHierarchy"
    assert restored.name == "Cache"
    assert restored.category == "MEMORY"


def test_model_link_latency_property_updates_both_endpoint_latencies():
    link = ModelLink(
        link_id=1,
        name="link_cpu_cache",
        source_node_id=1,
        source_component_name="cpu0",
        source_port="cache",
        target_node_id=2,
        target_component_name="cache0",
        target_port="cpu",
        source_latency="250ps",
        target_latency="1ns",
    )

    assert link.latency == "250ps"

    link.latency = "2ns"

    assert link.source_latency == "2ns"
    assert link.target_latency == "2ns"
    assert link.latency == "2ns"


def test_model_link_and_subcomponent_warning_error_helpers():
    warning_link = ModelLink(
        link_id=1,
        name="warn",
        source_node_id=1,
        source_component_name="a",
        source_port="out",
        target_node_id=2,
        target_component_name="b",
        target_port="in",
        compatibility_severity="warning",
    )
    error_attachment = ModelSubcompAttachment(
        attachment_id=1,
        name="bad_subcomp",
        parent_node_id=1,
        parent_component_name="cpu0",
        slot_name="mmu",
        child_node_id=2,
        child_component_name="tlb0",
        compatibility_severity="error",
    )

    assert warning_link.has_warning is True
    assert warning_link.has_error is False
    assert error_attachment.has_error is True
    assert error_attachment.has_warning is False
