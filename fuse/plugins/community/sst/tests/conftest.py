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
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fuse.plugins.community.sst.tests.sst_version_support import (
    detect_installed_sst_version,
)


def _required_sst_majors_for_node(node) -> set[int]:
    """Return SST major versions required by version-specific markers."""
    required: set[int] = set()

    if node.get_closest_marker("sst_15"):
        required.add(15)

    if node.get_closest_marker("sst_16"):
        required.add(16)

    return required


@pytest.fixture(autouse=True)
def skip_incompatible_sst_version_marker(request):
    """Skip SST-version-specific live tests on incompatible local installs."""
    required_majors = _required_sst_majors_for_node(request.node)
    if not required_majors:
        return

    detected = detect_installed_sst_version()

    if detected.major not in required_majors:
        pytest.skip(
            f"Test requires SST major {sorted(required_majors)}, "
            f"but detected SST {detected.text} from {detected.sst_info_path}."
        )



SAMPLE_SSTINFO = """
ELEMENT LIBRARY 0 = testElement (Some test element)
Components (2 total)
Component 0: TestCPU
Description: Test processor component
Category: PROCESSOR COMPONENT
Checkpointable: false
Parameters (2 total)
clock: CPU clock frequency [2GHz]
threads: Number of threads [<required>]
Ports (2 total)
cache_link: Link to cache
memory_link: Link to memory
SubComponent Slots (1 total)
mmu: MMU slot [SST::MMU]
Statistics (1 total)
cycles: Number of cycles, (units="cycles") Enable level = 1

Component 1: TestCache
Description: Test cache component
Category: MEMORY COMPONENT
Checkpointable: true
Parameters (2 total)
size: Cache size [32KiB]
associativity: Cache associativity [8]
Ports (2 total)
cpu_side: Link to CPU
mem_side: Link to memory
Statistics (1 total)
hits: Cache hits, (units="events") Enable level = 1

SubComponents (1 total)
SubComponent 0: TestMMU
Description: Test MMU subcomponent
Interface: SST::MMU
Parameters (1 total)
page_size: Page size [4096]
Ports (1 total)
walk_port: Page table walk port
"""


UPDATED_SAMPLE_SSTINFO = """
ELEMENT LIBRARY 0 = testElement (Some test element)
Components (1 total)
Component 0: TestCPU
Description: Updated test processor component
Category: PROCESSOR COMPONENT
Checkpointable: true
Parameters (1 total)
clock: CPU clock frequency [3GHz]
Ports (1 total)
cache_link: Updated link to cache
Statistics (1 total)
cycles: Number of cycles, (units="cycles") Enable level = 1
"""


@pytest.fixture
def sample_sstinfo():
    return SAMPLE_SSTINFO


@pytest.fixture
def updated_sample_sstinfo():
    return UPDATED_SAMPLE_SSTINFO


@pytest.fixture
def populate_sst_sample(sample_sstinfo):
    def _populate():
        from fuse.core.persistence.db_access import ensure_database_ready
        from fuse.plugins.community.sst.get_sstinfo import (
            parse_sstinfo_output,
            sync_parsed_sstinfo_to_database,
        )

        ensure_database_ready(run_plugin_bootstrap=False)

        elements, components = parse_sstinfo_output(sample_sstinfo)
        sync_parsed_sstinfo_to_database(elements, components)

    return _populate


def make_component(
    element: str,
    name: str,
    *,
    is_subcomp: int = 0,
    description: str = "",
    iface: str = "",
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
        "category": element,
        "functionality": "",
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


def memcontroller_component() -> dict:
    return make_component(
        "memHierarchy",
        "MemController",
        description="Memory controller",
        parameters=[
            {
                "name": "clock",
                "description": "Clock frequency",
                "default_val": "1GHz",
                "required": 1,
            },
            {
                "name": "addr_range_start",
                "description": "Start address",
                "default_val": "0",
                "required": 0,
            },
        ],
        ports=[
            {
                "name": "direct_link",
                "description": "Direct link",
                "iface": "SST::Interfaces::SimpleMem",
                "is_variable": 0,
                "base_name": "direct_link",
                "count_parameter": "",
                "default_count": 1,
            },
            {
                "name": "highlink%(num_ports)d",
                "description": "Variable high link",
                "iface": "SST::Interfaces::SimpleMem",
                "is_variable": 1,
                "base_name": "highlink",
                "count_parameter": "num_ports",
                "default_count": 1,
            },
        ],
        subcomp_slots=[
            {
                "name": "backend",
                "description": "Memory backend",
                "iface": "SST::MemHierarchy::MemBackend",
            }
        ],
    )


def cache_component(default_line_size: str = "64") -> dict:
    return make_component(
        "memHierarchy",
        "Cache",
        description="Cache",
        parameters=[
            {
                "name": "cache_line_size",
                "description": "Line size",
                "default_val": default_line_size,
                "required": 0,
            }
        ],
        ports=[
            {
                "name": "highlink",
                "description": "High link",
                "iface": "",
                "is_variable": 0,
                "base_name": "highlink",
                "count_parameter": "",
                "default_count": 1,
            }
        ],
    )


def custom_cpu_component() -> dict:
    return make_component(
        "customElement",
        "CustomCPU",
        description="Custom CPU",
        parameters=[
            {
                "name": "custom_width",
                "description": "Custom width",
                "default_val": "4",
                "required": 0,
            }
        ],
        ports=[
            {
                "name": "memory",
                "description": "Memory port",
                "iface": "SST::Interfaces::SimpleMem",
                "is_variable": 0,
                "base_name": "memory",
                "count_parameter": "",
                "default_count": 1,
            }
        ],
    )


@pytest.fixture()
def sst_env(tmp_path, monkeypatch):
    """Use a temporary FUSE DB and temporary SST catalog directories."""

    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "app.db"))

    import fuse.core.persistence.database as database
    importlib.reload(database)

    import fuse.plugins.community.sst.initialize_db as initialize_db
    importlib.reload(initialize_db)

    import fuse.plugins.community.sst.get_sstinfo as get_sstinfo
    importlib.reload(get_sstinfo)

    import fuse.plugins.community.sst.policy.loader as policy_loader
    importlib.reload(policy_loader)

    import fuse.plugins.community.sst.component_catalog as component_catalog
    importlib.reload(component_catalog)

    import fuse.plugins.community.sst.plugin as sst_plugin
    importlib.reload(sst_plugin)

    policy_dir = tmp_path / "policy_catalogs"
    component_dir = tmp_path / "component_catalogs"
    custom_dir = tmp_path / "custom_component_catalogs"

    monkeypatch.setattr(policy_loader, "CATALOG_DIR", policy_dir)
    monkeypatch.setattr(component_catalog, "_COMPONENT_CATALOG_DIR", component_dir)
    monkeypatch.setattr(component_catalog, "_CUSTOM_CATALOG_DIR", custom_dir)

    initialize_db.initialize_database()

    return SimpleNamespace(
        tmp_path=tmp_path,
        database=database,
        initialize_db=initialize_db,
        get_sstinfo=get_sstinfo,
        policy_loader=policy_loader,
        component_catalog=component_catalog,
        sst_plugin=sst_plugin,
        policy_dir=policy_dir,
        component_dir=component_dir,
        custom_dir=custom_dir,
    )


def write_policy_catalog(env, version: str) -> Path:
    path = env.policy_dir / f"sst-{version}.json"
    write_catalog(
        path,
        {
            "schema_version": 1,
            "sst_version": version,
            "components": {},
        },
    )
    env.policy_loader.load_policy_catalog.cache_clear()
    return path


def write_component_catalog(env, version: str, components: list[dict]) -> Path:
    return write_catalog(
        env.component_dir / f"sst-{version}.json",
        make_catalog(version, components),
    )