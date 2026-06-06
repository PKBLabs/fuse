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


def make_file_definition(name="Cache Pair", composite_id="cache-pair"):
    from fuse.core.model.composite import (
        CompositeComponentDefinition,
        CompositePortMapping,
    )

    return CompositeComponentDefinition.make(
        composite_id=composite_id,
        name=name,
        description="Reusable cache-pair composite.",
        icon_path="icons/cache_pair.png",
        mini_model={
            "components": [
                {"node_id": 1, "name": "cache_a", "x": 0.0, "y": 0.0},
                {"node_id": 2, "name": "cache_b", "x": 180.0, "y": 0.0},
            ],
            "links": [
                {"name": "cache_link", "source_node_id": 1, "target_node_id": 2},
            ],
        },
        port_mappings=[
            CompositePortMapping(
                external_port_name="cache_a.cpu",
                internal_node_id=1,
                internal_component_name="cache_a",
                internal_port_name="cpu",
                iface="memHierarchy.memEvent",
                exposed=False,
            )
        ],
    )


def test_composite_component_file_round_trips_definition(tmp_path):
    from fuse.core.model.composite import COMPOSITE_FILE_KIND
    from fuse.core.persistence.composite_component_files import (
        read_composite_component_file,
        write_composite_component_file,
    )

    output_path = write_composite_component_file(
        make_file_definition(),
        tmp_path / "cache_pair",
    )
    loaded = read_composite_component_file(output_path)
    document = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.suffix == ".fcc"
    assert document["kind"] == COMPOSITE_FILE_KIND
    assert loaded.composite_id == "cache-pair"
    assert loaded.name == "Cache Pair"
    assert loaded.mini_model["components"][0]["name"] == "cache_a"
    assert loaded.port_mappings[0].external_port_name == "cache_a.cpu"
    assert loaded.port_mappings[0].exposed is False
    assert document["definition"]["port_mappings"][0]["exposed"] is False


def test_import_composite_component_file_saves_to_local_database(tmp_path, monkeypatch):
    from fuse.core.persistence.composite_component_files import (
        import_composite_component_file,
        write_composite_component_file,
    )
    from fuse.core.persistence.composite_components import get_composite_component_definition

    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "composites.db"))
    file_path = write_composite_component_file(
        make_file_definition(),
        tmp_path / "cache_pair.fcc",
    )

    imported = import_composite_component_file(file_path)
    loaded = get_composite_component_definition(imported.composite_id)

    assert loaded is not None
    assert loaded.name == "Cache Pair"
    assert loaded.port_mappings[0].internal_port_name == "cpu"
    assert loaded.port_mappings[0].exposed is False


def test_import_composite_component_file_renames_name_collision_with_different_id(tmp_path, monkeypatch):
    from fuse.core.persistence.composite_component_files import (
        import_composite_component_file,
        write_composite_component_file,
    )
    from fuse.core.persistence.composite_components import save_composite_component_definition

    monkeypatch.setenv("FUSE_DB_PATH", str(tmp_path / "composites.db"))
    save_composite_component_definition(
        make_file_definition(name="Cache Pair", composite_id="local-cache-pair")
    )
    file_path = write_composite_component_file(
        make_file_definition(name="Cache Pair", composite_id="shared-cache-pair"),
        tmp_path / "shared_cache_pair.fcc",
    )

    imported = import_composite_component_file(file_path)

    assert imported.composite_id == "shared-cache-pair"
    assert imported.name == "Cache Pair (Imported)"


def test_read_composite_component_file_rejects_wrong_kind(tmp_path):
    from fuse.core.persistence.composite_component_files import (
        CompositeComponentFileError,
        read_composite_component_file,
    )

    path = tmp_path / "not_composite.fcc"
    path.write_text(json.dumps({"kind": "not-a-fuse-composite"}), encoding="utf-8")

    try:
        read_composite_component_file(path)
    except CompositeComponentFileError as exc:
        assert "Unsupported composite component file kind" in str(exc)
    else:
        raise AssertionError("Expected CompositeComponentFileError")
