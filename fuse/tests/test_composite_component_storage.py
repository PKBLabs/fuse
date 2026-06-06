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


def make_test_composite():
    from fuse.core.model.composite import (
        CompositeComponentDefinition,
        CompositePortMapping,
    )

    return CompositeComponentDefinition.make(
        composite_id="composite-cache-pair",
        name="Cache Pair",
        description="Two linked caches captured as a reusable mini-model.",
        icon_path="icons/cache_pair.png",
        mini_model={
            "components": [
                {"node_id": 1, "name": "cache_a", "x": 0, "y": 0},
                {"node_id": 2, "name": "cache_b", "x": 180, "y": 0},
            ],
            "links": [
                {"name": "internal_link", "source_node_id": 1, "target_node_id": 2},
            ],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.cpu",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="cpu",
                iface="memHierarchy.memEvent",
                description="CPU-side cache port",
                exposed=True,
            ),
            CompositePortMapping(
                external_port_name="cache_b.mem",
                internal_node_id=2,
                internal_component_name="cache_b",
                internal_port_name="mem",
                iface="memHierarchy.memEvent",
                description="Memory-side cache port",
                exposed=False,
            ),
        ],
    )


def test_core_database_initialization_creates_composite_table():
    from fuse.core.persistence.database import get_connection
    from fuse.core.persistence.db_access import ensure_database_ready

    ensure_database_ready(run_plugin_bootstrap=False)

    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'core_composite_components'
            """
        ).fetchone()

    assert row is not None


def test_composite_definition_storage_round_trips_model_and_ports():
    from fuse.core.persistence.composite_components import (
        get_composite_component_definition,
        save_composite_component_definition,
    )

    saved = save_composite_component_definition(make_test_composite())
    loaded = get_composite_component_definition(saved.composite_id)

    assert loaded is not None
    assert loaded.composite_id == "composite-cache-pair"
    assert loaded.name == "Cache Pair"
    assert loaded.description.startswith("Two linked caches")
    assert loaded.icon_path == "icons/cache_pair.png"
    assert loaded.mini_model["components"][0]["name"] == "cache_a"
    assert loaded.port_mappings[0].external_port_name == "cache_a.cpu"
    assert loaded.port_mappings[1].internal_port_name == "mem"
    assert loaded.port_mappings[0].exposed is True
    assert loaded.port_mappings[1].exposed is False


def test_composite_definition_update_keeps_original_created_timestamp():
    from fuse.core.persistence.composite_components import (
        get_composite_component_definition,
        save_composite_component_definition,
    )

    saved = save_composite_component_definition(make_test_composite())
    saved.description = "Updated description"
    updated = save_composite_component_definition(saved)
    loaded = get_composite_component_definition(saved.composite_id)

    assert loaded is not None
    assert loaded.description == "Updated description"
    assert loaded.created_at == saved.created_at
    assert loaded.updated_at == updated.updated_at


def test_load_component_definitions_includes_composite_definitions(monkeypatch):
    from fuse.core.persistence.composite_components import save_composite_component_definition
    from fuse.core.persistence.db_access import load_component_definitions

    monkeypatch.setattr(
        "fuse.core.persistence.db_access.load_all_palette_items",
        lambda *args, **kwargs: [],
    )
    save_composite_component_definition(make_test_composite())

    definitions = load_component_definitions()
    composites = [definition for definition in definitions if definition.is_composite]

    assert len(composites) == 1
    assert composites[0].name == "Cache Pair"
    assert composites[0].plugin_id == "core"
    assert composites[0].target_id == "fuse-composite"
    assert composites[0].component_id == "composite-cache-pair"
    assert composites[0].display_name == "Cache Pair (Composite)"


def test_composite_component_details_expose_only_explicit_external_ports():
    from fuse.core.persistence.composite_components import save_composite_component_definition
    from fuse.core.persistence.db_access import get_component_details, load_port_metadata_for_component

    save_composite_component_definition(make_test_composite())

    ports = load_port_metadata_for_component(
        "core",
        "composite-cache-pair",
        "fuse-composite",
    )
    details = get_component_details("core", "composite-cache-pair", "fuse-composite")

    assert [port["name"] for port in ports] == ["cache_a.cpu"]
    assert details["component"]["is_composite"] == 1
    assert details["component"]["composite_id"] == "composite-cache-pair"
    assert details["ports"][0]["iface"] == "memHierarchy.memEvent"


def test_component_definition_drag_payload_preserves_composite_identity():
    from fuse.core.model.models import ComponentDefinition

    definition = ComponentDefinition(
        plugin_id="core",
        target_id="fuse-composite",
        component_id="composite-cache-pair",
        element="Composite Components",
        name="Cache Pair",
        category="Composite Components",
        is_composite=1,
        composite_id="composite-cache-pair",
    )

    loaded = ComponentDefinition.from_drag_text(definition.to_drag_text())

    assert loaded.is_composite == 1
    assert loaded.composite_id == "composite-cache-pair"
    assert loaded.display_name == "Cache Pair (Composite)"
