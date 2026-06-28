# Flexible User-extensible Simulation Editor (FUSE)
# Copyright (c) 2026 PKB Research Labs, LLC.
#
# This file is part of FUSE.

"""Reusable SST catalog fixtures for plugin tests.

The helpers in this module are deliberately normal Python helpers instead of
``conftest.py`` fixtures so tests can import them explicitly. This keeps pytest
collection predictable and avoids relying on implementation details of conftest
module import paths.
"""

from __future__ import annotations

import json
from pathlib import Path


COMPREHENSIVE_SSTINFO = """
ELEMENT LIBRARY 0 = memHierarchy (Synthetic memHierarchy fixture)
Components (2 total)
Component 0: Cache
Description: Synthetic cache component
Category: MEMORY COMPONENT
Checkpointable: true
Parameters (3 total)
cache_line_size: Cache line size [64]
cache_size: Cache capacity [32KiB]
replacement_policy: Replacement policy [lru]
Ports (2 total)
highlink: CPU-side link
lowlink: Memory-side link
SubComponent Slots (1 total)
replacement: Replacement slot [SST::MemHierarchy::ReplacementPolicy]
Statistics (1 total)
hits: Cache hits, (units="events") Enable level = 1

Component 1: MemController
Description: Synthetic memory controller component
Category: MEMORY COMPONENT
Checkpointable: false
Parameters (3 total)
clock: Clock frequency [<required>]
addr_range_start: Starting address [0]
num_ports: Number of high ports [2]
Ports (2 total)
direct_link: Direct link
highlink%(num_ports)d: Variable high-side link
SubComponent Slots (1 total)
backend: Memory backend slot [SST::MemHierarchy::MemBackend]
Statistics (1 total)
requests: Memory requests, (units="requests") Enable level = 1

SubComponents (1 total)
SubComponent 0: simpleMemBackend
Description: Synthetic simple backend
Interface: SST::MemHierarchy::MemBackend
Parameters (2 total)
access_time: Access latency [10ns]
mem_size: Memory size [1GiB]
Ports (1 total)
unused_port: Synthetic backend port

ELEMENT LIBRARY 1 = customElement (Synthetic custom SST element)
Components (1 total)
Component 0: CustomCPU
Description: Synthetic custom processor
Category: PROCESSOR COMPONENT
Checkpointable: false
Parameters (2 total)
clock: CPU clock [2GHz]
custom_width: Custom issue width [4]
Ports (1 total)
memory: Memory link
Statistics (1 total)
instructions: Retired instructions, (units="instructions") Enable level = 1

SubComponents (1 total)
SubComponent 0: CustomMMU
Description: Synthetic custom MMU
Interface: SST::MMU
Parameters (1 total)
page_size: Page size [4096]
Ports (1 total)
walk_port: Page table walk port
"""


MALFORMED_BUT_PARSEABLE_SSTINFO = """
This header is intentionally ignored by the parser.
ELEMENT LIBRARY 0 = oddElement (Odd element)
Components (1 total)
Component 0: OddComponent
Description: Component with continuation lines
Parameters (1 total)
long_param: First line [default]
continued description text
Ports (1 total)
port%d: Simple printf variable port
"""


def make_component(
    element: str,
    name: str,
    *,
    is_subcomp: int = 0,
    description: str = "",
    iface: str = "",
    category: str = "",
    parameters: list[dict] | None = None,
    ports: list[dict] | None = None,
    subcomp_slots: list[dict] | None = None,
    statistics: list[dict] | None = None,
) -> dict:
    return {
        "element_name": element,
        "name": name,
        "description": description or f"{element}.{name}",
        "is_subcomp": int(is_subcomp),
        "iface": iface,
        "category": category or ("SUBCOMPONENT" if is_subcomp else element),
        "functionality": description or f"{element}.{name}",
        "checkpointable": 0,
        "parameters": parameters or [],
        "ports": ports or [],
        "subcomp_slots": subcomp_slots or [],
        "statistics": statistics or [],
    }


def make_catalog(version: str, components: list[dict]) -> dict:
    element_names = sorted({component["element_name"] for component in components})
    return {
        "schema_version": "1.0.0",
        "source": "pytest fixture",
        "sst_version": version,
        "elements": [
            {"name": element_name, "description": f"{element_name} element"}
            for element_name in element_names
        ],
        "components": components,
    }


def write_catalog(path: Path, catalog: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def parameter(name: str, default: str = "", *, description: str = "", required: bool = False) -> dict:
    return {
        "name": name,
        "description": description or name,
        "default_val": "<required>" if required else default,
        "required": 1 if required else 0,
    }


def port(
    name: str,
    *,
    description: str = "",
    iface: str = "",
    is_variable: bool = False,
    base_name: str = "",
    count_parameter: str = "",
    default_count: int = 1,
) -> dict:
    return {
        "name": name,
        "description": description or name,
        "iface": iface,
        "is_variable": 1 if is_variable else 0,
        "base_name": base_name or name,
        "count_parameter": count_parameter,
        "default_count": default_count,
    }


def slot(name: str, iface: str, *, description: str = "") -> dict:
    return {
        "name": name,
        "description": description or name,
        "iface": iface,
    }


def statistic(name: str, units: str = "", *, description: str = "") -> dict:
    return {
        "name": name,
        "description": description or name,
        "units": units,
        "iface": "",
        "parameters": [],
    }


def cache_component(default_line_size: str = "64", *, port_iface: str = "") -> dict:
    return make_component(
        "memHierarchy",
        "Cache",
        description="Synthetic cache",
        category="MEMORY COMPONENT",
        parameters=[
            parameter("cache_line_size", default_line_size, description="Line size"),
            parameter("cache_size", "32KiB", description="Cache size"),
        ],
        ports=[
            port("highlink", description="High link", iface=port_iface),
            port("lowlink", description="Low link", iface=port_iface),
        ],
        subcomp_slots=[
            slot("replacement", "SST::MemHierarchy::ReplacementPolicy"),
        ],
        statistics=[
            statistic("hits", "events", description="Cache hits"),
        ],
    )


def memcontroller_component() -> dict:
    return make_component(
        "memHierarchy",
        "MemController",
        description="Synthetic memory controller",
        category="MEMORY COMPONENT",
        parameters=[
            parameter("clock", "1GHz", description="Clock frequency", required=True),
            parameter("addr_range_start", "0", description="Start address"),
            parameter("num_ports", "1", description="Number of high ports"),
        ],
        ports=[
            port(
                "direct_link",
                description="Direct link",
                iface="SST::Interfaces::SimpleMem",
            ),
            port(
                "highlink%(num_ports)d",
                description="Variable high link",
                iface="SST::Interfaces::SimpleMem",
                is_variable=True,
                base_name="highlink",
                count_parameter="num_ports",
                default_count=1,
            ),
        ],
        subcomp_slots=[
            slot("backend", "SST::MemHierarchy::MemBackend", description="Memory backend"),
        ],
        statistics=[
            statistic("requests", "requests", description="Memory requests"),
        ],
    )


def backend_subcomponent() -> dict:
    return make_component(
        "memHierarchy",
        "simpleMemBackend",
        is_subcomp=1,
        iface="SST::MemHierarchy::MemBackend",
        description="Synthetic backend",
        parameters=[
            parameter("access_time", "10ns", description="Access latency"),
            parameter("mem_size", "1GiB", description="Memory size"),
        ],
    )


def custom_cpu_component() -> dict:
    return make_component(
        "customElement",
        "CustomCPU",
        description="Synthetic custom CPU",
        category="PROCESSOR COMPONENT",
        parameters=[
            parameter("clock", "2GHz", description="CPU clock"),
            parameter("custom_width", "4", description="Issue width"),
        ],
        ports=[
            port("memory", description="Memory port", iface="SST::Interfaces::SimpleMem"),
        ],
        statistics=[
            statistic("instructions", "instructions", description="Retired instructions"),
        ],
    )


def custom_mmu_subcomponent() -> dict:
    return make_component(
        "customElement",
        "CustomMMU",
        is_subcomp=1,
        iface="SST::MMU",
        description="Synthetic custom MMU",
        parameters=[
            parameter("page_size", "4096", description="Page size"),
        ],
        ports=[
            port("walk_port", description="Page table walk port"),
        ],
    )


def baseline_catalog(version: str = "16.0.0") -> dict:
    return make_catalog(
        version,
        [
            cache_component(),
            memcontroller_component(),
            backend_subcomponent(),
        ],
    )


def discovered_custom_catalog(version: str = "16.0.0") -> dict:
    return make_catalog(
        version,
        [
            cache_component(),
            memcontroller_component(),
            backend_subcomponent(),
            custom_cpu_component(),
            custom_mmu_subcomponent(),
        ],
    )


def discovered_changed_catalog(version: str = "16.0.0") -> dict:
    return make_catalog(
        version,
        [
            cache_component(default_line_size="128", port_iface="SST::Interfaces::SimpleMem"),
            memcontroller_component(),
            backend_subcomponent(),
            custom_cpu_component(),
        ],
    )
