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
"""SST port-visibility guidance for raw ports shadowed by runtime slots.

SST's ``sst-info`` catalog sometimes exposes a raw port that is also serviced
through a runtime-loaded SubComponent slot.  Showing both by default can make
new models look like the raw port should be wired directly even when the
clearer/modern construction is slot-first.

This module provides a small version-independent overlay for the high-confidence
cases found by scanning SST Elements 15.1.0 and 16.0.0 source.  The overlay is a
UI rule only: hidden/advanced raw ports remain part of the component's model
metadata so older projects and advanced users can still access them.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class PortVisibilityRule:
    """UI visibility/help rule for one SST catalog/raw port."""

    component_type: str
    port_name: str
    mode: str
    default_visible: bool
    use_slot: str = ""
    child_type: str = ""
    child_port: str = ""
    explanation: str = ""


@dataclass(frozen=True)
class DeprecatedConnectorRule:
    """Version-aware UI/export rule for one deprecated SST port or slot."""

    component_type: str
    connector_name: str
    connector_kind: str
    replacement_name: str = ""
    replacement_kind: str = ""
    deprecated_since: str = ""
    removed_in: str = ""
    explanation: str = ""


def _key(component_type: str, port_name: str) -> tuple[str, str]:
    return (component_type.strip(), port_name.strip())


def _connector_key(
    component_type: str,
    connector_kind: str,
    connector_name: str,
) -> tuple[str, str, str]:
    return (
        component_type.strip(),
        connector_kind.strip(),
        connector_name.strip(),
    )


def _connector_template_matches(rule_name: str, connector_name: str) -> bool:
    """Return whether an SST printf/parameterized connector rule names a port.

    SST uses catalog names such as ``high_network_%(high_network_ports)d`` for
    variable port families.  FUSE renders those as concrete connectors like
    ``high_network_0`` and ``high_network_1``.  Deprecated/visibility rules
    should therefore match both exact connector names and these rendered family
    members without letting replacement names inherit deprecated styling.
    """
    rule_name = str(rule_name or "").strip()
    connector_name = str(connector_name or "").strip()
    if not rule_name or not connector_name:
        return False
    if rule_name == connector_name:
        return True
    if "%(" not in rule_name and "%d" not in rule_name:
        return False

    pieces: list[str] = []
    index = 0
    while index < len(rule_name):
        if rule_name.startswith("%(", index):
            end = rule_name.find(")d", index + 2)
            if end != -1:
                pieces.append(r"\d+")
                index = end + 2
                continue
        if rule_name.startswith("%d", index):
            pieces.append(r"\d+")
            index += 2
            continue

        pieces.append(re.escape(rule_name[index]))
        index += 1

    return re.fullmatch("".join(pieces), connector_name) is not None


PORT_VISIBILITY_RULES: dict[tuple[str, str], PortVisibilityRule] = {
    # Firefly NIC: the raw catalog ports are present in sst-info, but Firefly
    # loads the corresponding runtime subcomponents through these slot names.
    _key("firefly.nic", "rtr"): PortVisibilityRule(
        component_type="firefly.nic",
        port_name="rtr",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="rtrLink",
        child_type="merlin.linkcontrol",
        child_port="rtr_port",
        explanation=(
            "This raw SST catalog port is shadowed by the firefly.nic rtrLink "
            "runtime SubComponent slot. In guided models, use "
            "nic.rtrLink -> merlin.linkcontrol, then connect "
            "merlin.linkcontrol.rtr_port to the router."
        ),
    ),
    _key("firefly.nic", "detailed"): PortVisibilityRule(
        component_type="firefly.nic",
        port_name="detailed",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="detailedInterface",
        child_type="firefly.detailedInterface",
        explanation=(
            "This raw detailed-model port is shadowed by the firefly.nic "
            "detailedInterface runtime SubComponent slot."
        ),
    ),
    _key("firefly.nic", "nicDetailedRead"): PortVisibilityRule(
        component_type="firefly.nic",
        port_name="nicDetailedRead",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="nicDetailedRead",
        explanation=(
            "This raw detailed-read port shares a name with a Firefly runtime "
            "SubComponent slot. Use the slot in guided models."
        ),
    ),
    _key("firefly.nic", "nicDetailedWrite"): PortVisibilityRule(
        component_type="firefly.nic",
        port_name="nicDetailedWrite",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="nicDetailedWrite",
        explanation=(
            "This raw detailed-write port shares a name with a Firefly runtime "
            "SubComponent slot. Use the slot in guided models."
        ),
    ),

    # rdmaNic has exact-name catalog ports and runtime slots. Treat the raw
    # ports as advanced because the source loads the StandardMem/SimpleNetwork
    # children through these slots.
    _key("rdmaNic.nic", "mmio"): PortVisibilityRule(
        component_type="rdmaNic.nic",
        port_name="mmio",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="mmio",
        explanation=(
            "rdmaNic.mmio is a runtime StandardMem SubComponent slot. The raw "
            "port is hidden by default to avoid confusing it with the slot."
        ),
    ),
    _key("rdmaNic.nic", "dma"): PortVisibilityRule(
        component_type="rdmaNic.nic",
        port_name="dma",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="dma",
        explanation=(
            "rdmaNic.dma is a runtime StandardMem SubComponent slot when DMA "
            "cache support is enabled. The raw port is advanced."
        ),
    ),
    _key("rdmaNic.nic", "rtrLink"): PortVisibilityRule(
        component_type="rdmaNic.nic",
        port_name="rtrLink",
        mode="runtime_slot_shadow",
        default_visible=False,
        use_slot="rtrLink",
        child_type="merlin.linkcontrol",
        child_port="rtr_port",
        explanation=(
            "rdmaNic.rtrLink is a runtime SimpleNetwork SubComponent slot. "
            "Attach a network-interface child rather than wiring the raw port."
        ),
    ),

    # memHierarchy: highlink/lowlink direct ports are first-class direct-link
    # ports for memHierarchy-to-memHierarchy wiring.  They should remain visible
    # by default.  Hide only the deprecated legacy aliases and deprecated
    # network* raw ports that SST now routes through MemLink/MemNIC subcomponents.
    _key("memHierarchy.standardInterface", "port"): PortVisibilityRule(
        component_type="memHierarchy.standardInterface",
        port_name="port",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemLink",
        explanation=(
            "This is the deprecated StandardInterface port name. Use the "
            "lowlink port for direct memHierarchy links, or the lowlink slot "
            "with memHierarchy.MemNIC when connecting through a network."
        ),
    ),
    _key("memHierarchy.Bus", "high_network_0"): PortVisibilityRule(
        component_type="memHierarchy.Bus",
        port_name="high_network_0",
        mode="advanced_raw",
        default_visible=False,
        explanation="Deprecated bus CPU-side port alias; use highlink0.",
    ),
    _key("memHierarchy.Bus", "low_network_0"): PortVisibilityRule(
        component_type="memHierarchy.Bus",
        port_name="low_network_0",
        mode="advanced_raw",
        default_visible=False,
        explanation="Deprecated bus memory-side port alias; use lowlink0.",
    ),
    _key("memHierarchy.Bus", "high_network_%(high_network_ports)d"): PortVisibilityRule(
        component_type="memHierarchy.Bus",
        port_name="high_network_%(high_network_ports)d",
        mode="advanced_raw",
        default_visible=False,
        explanation="Deprecated bus CPU-side port alias; use the matching highlinkN port.",
    ),
    _key("memHierarchy.Bus", "low_network_%(low_network_ports)d"): PortVisibilityRule(
        component_type="memHierarchy.Bus",
        port_name="low_network_%(low_network_ports)d",
        mode="advanced_raw",
        default_visible=False,
        explanation="Deprecated bus memory-side port alias; use the matching lowlinkN port.",
    ),
    _key("memHierarchy.Cache", "high_network_0"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="high_network_0",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated cache CPU-side direct-link alias; use highlink.",
    ),
    _key("memHierarchy.Cache", "low_network_0"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="low_network_0",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated cache memory-side direct-link alias; use lowlink.",
    ),
    _key("memHierarchy.Cache", "cache"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="cache",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNIC",
        explanation=(
            "Deprecated cache network port. Use a MemNIC or MemNICFour in the "
            "highlink slot and connect the child port(s) to the network."
        ),
    ),
    _key("memHierarchy.Cache", "cache_ack"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="cache_ack",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network ack port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.Cache", "cache_fwd"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="cache_fwd",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network fwd port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.Cache", "cache_data"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="cache_data",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network data port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.Cache", "directory"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="directory",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemNIC",
        explanation=(
            "Deprecated cache network port. Use a MemNIC or MemNICFour in the "
            "lowlink slot and connect the child port(s) to the network."
        ),
    ),
    _key("memHierarchy.Cache", "directory_ack"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="directory_ack",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network ack port; use lowlink -> MemNICFour.",
    ),
    _key("memHierarchy.Cache", "directory_fwd"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="directory_fwd",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network fwd port; use lowlink -> MemNICFour.",
    ),
    _key("memHierarchy.Cache", "directory_data"): PortVisibilityRule(
        component_type="memHierarchy.Cache",
        port_name="directory_data",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated cache split-network data port; use lowlink -> MemNICFour.",
    ),
    _key("memHierarchy.DirectoryController", "network"): PortVisibilityRule(
        component_type="memHierarchy.DirectoryController",
        port_name="network",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNIC",
        explanation=(
            "Deprecated directory network port. Use the highlink slot with "
            "memHierarchy.MemNIC or MemNICFour and connect the child port(s)."
        ),
    ),
    _key("memHierarchy.DirectoryController", "network_ack"): PortVisibilityRule(
        component_type="memHierarchy.DirectoryController",
        port_name="network_ack",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated directory split-network ack port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.DirectoryController", "network_fwd"): PortVisibilityRule(
        component_type="memHierarchy.DirectoryController",
        port_name="network_fwd",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated directory split-network fwd port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.DirectoryController", "network_data"): PortVisibilityRule(
        component_type="memHierarchy.DirectoryController",
        port_name="network_data",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated directory split-network data port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.DirectoryController", "memory"): PortVisibilityRule(
        component_type="memHierarchy.DirectoryController",
        port_name="memory",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated directory memory port; use lowlink instead.",
    ),
    _key("memHierarchy.MemController", "direct_link"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="direct_link",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated memory-controller direct-link port; use highlink.",
    ),
    _key("memHierarchy.MemController", "network"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="network",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNIC",
        explanation=(
            "Deprecated memory-controller network port. Use the highlink slot "
            "with memHierarchy.MemNIC or MemNICFour and connect the child port(s)."
        ),
    ),
    _key("memHierarchy.MemController", "network_ack"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="network_ack",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated memory-controller split-network ack port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.MemController", "network_fwd"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="network_fwd",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated memory-controller split-network fwd port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.MemController", "network_data"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="network_data",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemNICFour",
        explanation="Deprecated memory-controller split-network data port; use highlink -> MemNICFour.",
    ),
    _key("memHierarchy.MemController", "cube_link"): PortVisibilityRule(
        component_type="memHierarchy.MemController",
        port_name="cube_link",
        mode="advanced_raw",
        default_visible=False,
        explanation="Deprecated memory-controller cube_link port.",
    ),
    _key("memHierarchy.Scratchpad", "cpu"): PortVisibilityRule(
        component_type="memHierarchy.Scratchpad",
        port_name="cpu",
        mode="advanced_raw",
        default_visible=False,
        use_slot="highlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated scratchpad CPU-side direct-link port; use highlink.",
    ),
    _key("memHierarchy.Scratchpad", "memory"): PortVisibilityRule(
        component_type="memHierarchy.Scratchpad",
        port_name="memory",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemLink",
        explanation="Deprecated scratchpad memory-side direct-link port; use lowlink.",
    ),
    _key("memHierarchy.Scratchpad", "network"): PortVisibilityRule(
        component_type="memHierarchy.Scratchpad",
        port_name="network",
        mode="advanced_raw",
        default_visible=False,
        use_slot="lowlink",
        child_type="memHierarchy.MemNIC",
        explanation=(
            "Deprecated scratchpad network port. Use the lowlink slot with "
            "memHierarchy.MemNIC or MemNICFour and connect the child port(s)."
        ),
    ),
}


DEPRECATED_CONNECTOR_RULES: dict[tuple[str, str, str], DeprecatedConnectorRule] = {
    # memHierarchy renamed its link sides to highlink/lowlink while retaining
    # older aliases for source compatibility.  Rules are intentionally version
    # aware: the first SST major that marks a connector deprecated keeps it
    # visible but styled as deprecated; later majors hide it by default and keep
    # it available through the deprecated/legacy connector overlay.
    _connector_key("memHierarchy.standardInterface", "port", "port"): DeprecatedConnectorRule(
        component_type="memHierarchy.standardInterface",
        connector_name="port",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation=(
            "The StandardInterface port named 'port' was renamed to 'lowlink'. "
            "Use lowlink for direct memHierarchy links, or the lowlink slot for "
            "explicit MemLink/MemNIC-style construction."
        ),
    ),
    _connector_key("memHierarchy.standardInterface", "slot", "memlink"): DeprecatedConnectorRule(
        component_type="memHierarchy.standardInterface",
        connector_name="memlink",
        connector_kind="slot",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The StandardInterface memlink slot was renamed to lowlink.",
    ),

    _connector_key("memHierarchy.Bus", "port", "high_network_0"): DeprecatedConnectorRule(
        component_type="memHierarchy.Bus",
        connector_name="high_network_0",
        connector_kind="port",
        replacement_name="highlink0",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use highlink0 for direct bus links on the upper/processor side.",
    ),
    _connector_key("memHierarchy.Bus", "port", "low_network_0"): DeprecatedConnectorRule(
        component_type="memHierarchy.Bus",
        connector_name="low_network_0",
        connector_kind="port",
        replacement_name="lowlink0",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use lowlink0 for direct bus links on the lower/memory side.",
    ),

    _connector_key("memHierarchy.Bus", "port", "high_network_%(high_network_ports)d"): DeprecatedConnectorRule(
        component_type="memHierarchy.Bus",
        connector_name="high_network_%(high_network_ports)d",
        connector_kind="port",
        replacement_name="matching highlinkN",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use the corresponding highlinkN port for direct bus links on the upper/processor side.",
    ),
    _connector_key("memHierarchy.Bus", "port", "low_network_%(low_network_ports)d"): DeprecatedConnectorRule(
        component_type="memHierarchy.Bus",
        connector_name="low_network_%(low_network_ports)d",
        connector_kind="port",
        replacement_name="matching lowlinkN",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use the corresponding lowlinkN port for direct bus links on the lower/memory side.",
    ),

    _connector_key("memHierarchy.Cache", "slot", "cpulink"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="cpulink",
        connector_kind="slot",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The Cache cpulink slot was renamed to highlink.",
    ),
    _connector_key("memHierarchy.Cache", "slot", "memlink"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="memlink",
        connector_kind="slot",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The Cache memlink slot was renamed to lowlink.",
    ),
    _connector_key("memHierarchy.Cache", "port", "high_network_0"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="high_network_0",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use the highlink port for direct CPU-side cache links.",
    ),
    _connector_key("memHierarchy.Cache", "port", "low_network_0"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="low_network_0",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use the lowlink port for direct memory-side cache links.",
    ),
    _connector_key("memHierarchy.Cache", "port", "cache"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="cache",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNIC or MemNICFour for networked CPU-side cache links.",
    ),
    _connector_key("memHierarchy.Cache", "port", "cache_ack"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="cache_ack",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network ack traffic.",
    ),
    _connector_key("memHierarchy.Cache", "port", "cache_fwd"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="cache_fwd",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network fwd traffic.",
    ),
    _connector_key("memHierarchy.Cache", "port", "cache_data"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="cache_data",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network data traffic.",
    ),
    _connector_key("memHierarchy.Cache", "port", "directory"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="directory",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use lowlink -> memHierarchy.MemNIC or MemNICFour for networked memory-side cache links.",
    ),
    _connector_key("memHierarchy.Cache", "port", "directory_ack"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="directory_ack",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use lowlink -> memHierarchy.MemNICFour for split-network ack traffic.",
    ),
    _connector_key("memHierarchy.Cache", "port", "directory_fwd"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="directory_fwd",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use lowlink -> memHierarchy.MemNICFour for split-network fwd traffic.",
    ),
    _connector_key("memHierarchy.Cache", "port", "directory_data"): DeprecatedConnectorRule(
        component_type="memHierarchy.Cache",
        connector_name="directory_data",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use lowlink -> memHierarchy.MemNICFour for split-network data traffic.",
    ),

    _connector_key("memHierarchy.DirectoryController", "slot", "cpulink"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="cpulink",
        connector_kind="slot",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The DirectoryController cpulink slot was renamed to highlink.",
    ),
    _connector_key("memHierarchy.DirectoryController", "slot", "memlink"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="memlink",
        connector_kind="slot",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The DirectoryController memlink slot was renamed to lowlink.",
    ),
    _connector_key("memHierarchy.DirectoryController", "port", "network"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="network",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNIC or MemNICFour for directory network links.",
    ),
    _connector_key("memHierarchy.DirectoryController", "port", "network_ack"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="network_ack",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network ack traffic.",
    ),
    _connector_key("memHierarchy.DirectoryController", "port", "network_fwd"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="network_fwd",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network fwd traffic.",
    ),
    _connector_key("memHierarchy.DirectoryController", "port", "network_data"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="network_data",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network data traffic.",
    ),
    _connector_key("memHierarchy.DirectoryController", "port", "memory"): DeprecatedConnectorRule(
        component_type="memHierarchy.DirectoryController",
        connector_name="memory",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use lowlink for direct directory-to-memory links.",
    ),

    _connector_key("memHierarchy.MemController", "slot", "cpulink"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="cpulink",
        connector_kind="slot",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The MemController cpulink slot was renamed to highlink.",
    ),
    _connector_key("memHierarchy.MemController", "port", "direct_link"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="direct_link",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use highlink for direct memory-controller links.",
    ),
    _connector_key("memHierarchy.MemController", "port", "network"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="network",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNIC or MemNICFour for memory-controller network links.",
    ),
    _connector_key("memHierarchy.MemController", "port", "network_ack"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="network_ack",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network ack traffic.",
    ),
    _connector_key("memHierarchy.MemController", "port", "network_fwd"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="network_fwd",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network fwd traffic.",
    ),
    _connector_key("memHierarchy.MemController", "port", "network_data"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="network_data",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use highlink -> memHierarchy.MemNICFour for split-network data traffic.",
    ),
    _connector_key("memHierarchy.MemController", "port", "cube_link"): DeprecatedConnectorRule(
        component_type="memHierarchy.MemController",
        connector_name="cube_link",
        connector_kind="port",
        deprecated_since="15.0.0",
        explanation="cube_link is a deprecated memory-controller port.",
    ),

    _connector_key("memHierarchy.Scratchpad", "slot", "cpulink"): DeprecatedConnectorRule(
        component_type="memHierarchy.Scratchpad",
        connector_name="cpulink",
        connector_kind="slot",
        replacement_name="highlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The Scratchpad cpulink slot was renamed to highlink.",
    ),
    _connector_key("memHierarchy.Scratchpad", "slot", "memlink"): DeprecatedConnectorRule(
        component_type="memHierarchy.Scratchpad",
        connector_name="memlink",
        connector_kind="slot",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="The Scratchpad memlink slot was renamed to lowlink.",
    ),
    _connector_key("memHierarchy.Scratchpad", "port", "cpu"): DeprecatedConnectorRule(
        component_type="memHierarchy.Scratchpad",
        connector_name="cpu",
        connector_kind="port",
        replacement_name="highlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use highlink for direct scratchpad CPU-side links.",
    ),
    _connector_key("memHierarchy.Scratchpad", "port", "memory"): DeprecatedConnectorRule(
        component_type="memHierarchy.Scratchpad",
        connector_name="memory",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="port",
        deprecated_since="15.0.0",
        explanation="Use lowlink for direct scratchpad memory-side links.",
    ),
    _connector_key("memHierarchy.Scratchpad", "port", "network"): DeprecatedConnectorRule(
        component_type="memHierarchy.Scratchpad",
        connector_name="network",
        connector_kind="port",
        replacement_name="lowlink",
        replacement_kind="slot",
        deprecated_since="15.0.0",
        explanation="Use a MemNIC/MemNICFour in the appropriate highlink or lowlink slot for scratchpad network links.",
    ),
}


def sst_type_for_node(node: Any) -> str:
    component = getattr(node, "component", None)
    if component is None:
        return ""

    element = str(getattr(component, "element", "") or "").strip()
    name = str(getattr(component, "name", "") or "").strip()

    if element and name:
        return f"{element}.{name}"
    return name


def rule_for_component_port(component_type: str, port_name: str) -> PortVisibilityRule | None:
    component_type = str(component_type or "").strip()
    port_name = str(port_name or "").strip()
    exact = PORT_VISIBILITY_RULES.get(_key(component_type, port_name))
    if exact is not None:
        return exact

    for (rule_component_type, rule_port_name), rule in PORT_VISIBILITY_RULES.items():
        if rule_component_type != component_type:
            continue
        if _connector_template_matches(rule_port_name, port_name):
            return rule

    return None


def rule_for_node_port(node: Any, port_name: str) -> PortVisibilityRule | None:
    return rule_for_component_port(sst_type_for_node(node), str(port_name or "").strip())


def rules_for_node(node: Any) -> dict[str, PortVisibilityRule]:
    component_type = sst_type_for_node(node)
    if not component_type:
        return {}

    return {
        port_name: rule
        for (rule_component_type, port_name), rule in PORT_VISIBILITY_RULES.items()
        if rule_component_type == component_type
    }


def _version_major(value: Any) -> int | None:
    """Return the leading major version from target labels such as 'SST 16.0.0'."""
    match = re.search(r"(?<!\d)(\d+)(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _node_target_version_text(node: Any) -> str:
    component = getattr(node, "component", None)
    fields = (
        getattr(component, "framework_version", ""),
        getattr(component, "target_id", ""),
        getattr(component, "target_label", ""),
    )
    return " ".join(str(value or "") for value in fields if str(value or "").strip())


def deprecated_connector_stage(
    rule: DeprecatedConnectorRule,
    *,
    target_version: Any = "",
) -> str:
    """Return newly_deprecated, legacy_deprecated, removed, or deprecated."""
    target_major = _version_major(target_version)
    since_major = _version_major(getattr(rule, "deprecated_since", ""))
    removed_major = _version_major(getattr(rule, "removed_in", ""))

    if target_major is not None and removed_major is not None and target_major >= removed_major:
        return "removed"

    if target_major is None or since_major is None:
        return "deprecated"

    if target_major <= since_major:
        return "newly_deprecated"

    return "legacy_deprecated"


def deprecated_connector_stage_for_node(
    node: Any,
    rule: DeprecatedConnectorRule,
) -> str:
    return deprecated_connector_stage(rule, target_version=_node_target_version_text(node))


def deprecated_connector_default_visible_for_stage(stage: str) -> bool:
    # Newly-deprecated connectors remain visible for transition.  Once the target
    # moves past the first known deprecated major, the guided view hides them by
    # default but keeps them revealable.
    return stage in {"newly_deprecated", "deprecated"}


def deprecated_connector_default_visible_for_node(
    node: Any,
    rule: DeprecatedConnectorRule,
) -> bool:
    return deprecated_connector_default_visible_for_stage(
        deprecated_connector_stage_for_node(node, rule)
    )


def deprecated_connector_rule_for_component(
    component_type: str,
    connector_name: str,
    connector_kind: str,
) -> DeprecatedConnectorRule | None:
    component_type = str(component_type or "").strip()
    connector_kind = str(connector_kind or "").strip()
    connector_name = str(connector_name or "").strip()

    exact = DEPRECATED_CONNECTOR_RULES.get(
        _connector_key(component_type, connector_kind, connector_name)
    )
    if exact is not None:
        return exact

    for (
        rule_component_type,
        rule_connector_kind,
        rule_connector_name,
    ), rule in DEPRECATED_CONNECTOR_RULES.items():
        if rule_component_type != component_type:
            continue
        if rule_connector_kind != connector_kind:
            continue
        if _connector_template_matches(rule_connector_name, connector_name):
            return rule

    return None


def deprecated_connector_rule_for_node(
    node: Any,
    connector_name: str,
    connector_kind: str,
) -> DeprecatedConnectorRule | None:
    return deprecated_connector_rule_for_component(
        sst_type_for_node(node),
        str(connector_name or "").strip(),
        str(connector_kind or "").strip(),
    )


def deprecated_port_rule_for_node(
    node: Any,
    port_name: str,
) -> DeprecatedConnectorRule | None:
    return deprecated_connector_rule_for_node(node, port_name, "port")


def deprecated_slot_rule_for_node(
    node: Any,
    slot_name: str,
) -> DeprecatedConnectorRule | None:
    return deprecated_connector_rule_for_node(node, slot_name, "slot")


def deprecated_rules_for_node(
    node: Any,
    connector_kind: str | None = None,
) -> dict[str, DeprecatedConnectorRule]:
    component_type = sst_type_for_node(node)
    if not component_type:
        return {}

    kind_filter = str(connector_kind or "").strip()
    return {
        connector_name: rule
        for (
            rule_component_type,
            rule_connector_kind,
            connector_name,
        ), rule in DEPRECATED_CONNECTOR_RULES.items()
        if rule_component_type == component_type
        and (not kind_filter or rule_connector_kind == kind_filter)
    }


def deprecated_connector_status_label(stage: str) -> str:
    return {
        "newly_deprecated": "Deprecated SST connector",
        "legacy_deprecated": "Deprecated/legacy SST connector",
        "removed": "Removed SST connector",
    }.get(stage, "Deprecated SST connector")


def deprecated_connector_tooltip(
    rule: DeprecatedConnectorRule,
    *,
    stage: str = "deprecated",
) -> str:
    kind = "SubComponent slot" if rule.connector_kind == "slot" else "port"
    lines = [f"{deprecated_connector_status_label(stage)} ({kind})"]

    if getattr(rule, "deprecated_since", ""):
        lines.append(f"Deprecated since SST {rule.deprecated_since}")
    if getattr(rule, "removed_in", ""):
        lines.append(f"Removed in SST {rule.removed_in}")

    if rule.replacement_name:
        replacement_kind = rule.replacement_kind or rule.connector_kind
        lines.append(f"Preferred {replacement_kind}: {rule.replacement_name}")

    if stage == "newly_deprecated":
        lines.append("Still visible in this target, but new models should use the replacement.")
    elif stage == "legacy_deprecated":
        lines.append("Hidden by default in this target; reveal deprecated/legacy connectors to edit old models.")
    elif stage == "removed":
        lines.append("Not valid for this SST target except as a loaded legacy/orphaned connector.")

    if rule.explanation:
        lines.append("")
        lines.append(rule.explanation)

    return "\n".join(lines)


def port_rule_tooltip(rule: PortVisibilityRule) -> str:
    label = "Advanced/raw SST port"
    if rule.mode == "runtime_slot_shadow":
        label = "Raw SST port shadowed by runtime SubComponent slot"

    lines = [label]
    if rule.use_slot:
        lines.append(f"Preferred slot: {rule.use_slot}")
    if rule.child_type:
        lines.append(f"Preferred child: {rule.child_type}")
    if rule.child_port:
        lines.append(f"Preferred child port: {rule.child_port}")
    if rule.explanation:
        lines.append("")
        lines.append(rule.explanation)

    lines.append("")
    lines.append("Use the component '+' menu to show or hide advanced/raw ports.")
    return "\n".join(lines)
