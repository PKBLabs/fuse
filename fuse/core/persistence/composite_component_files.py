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
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fuse.core.model.composite import (
    COMPOSITE_FILE_KIND,
    COMPOSITE_SCHEMA_VERSION,
    CompositeComponentDefinition,
)
from fuse.core.persistence.composite_components import (
    get_composite_component_definition,
    list_composite_component_definitions,
    save_composite_component_definition,
)

COMPOSITE_FILE_EXTENSION = ".fcc"


class CompositeComponentFileError(ValueError):
    pass


def composite_file_document(definition: CompositeComponentDefinition) -> dict[str, Any]:
    return {
        "kind": COMPOSITE_FILE_KIND,
        "schema_version": COMPOSITE_SCHEMA_VERSION,
        "definition": definition.to_dict(),
    }


def write_composite_component_file(
    definition: CompositeComponentDefinition,
    file_path: str | Path,
) -> Path:
    output_path = Path(file_path)
    if output_path.suffix.lower() != COMPOSITE_FILE_EXTENSION:
        output_path = output_path.with_suffix(COMPOSITE_FILE_EXTENSION)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(composite_file_document(definition), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_path


def read_composite_component_file(file_path: str | Path) -> CompositeComponentDefinition:
    path = Path(file_path)

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompositeComponentFileError(f"Invalid composite component JSON: {exc}") from exc
    except OSError as exc:
        raise CompositeComponentFileError(f"Unable to read composite component file: {exc}") from exc

    if not isinstance(document, dict):
        raise CompositeComponentFileError("Composite component file must contain a JSON object.")

    kind = str(document.get("kind") or "")
    if kind != COMPOSITE_FILE_KIND:
        raise CompositeComponentFileError(
            f"Unsupported composite component file kind: {kind or '(missing)'}"
        )

    raw_definition = document.get("definition")
    if raw_definition is None:
        raw_definition = document.get("composite")

    if not isinstance(raw_definition, dict):
        raise CompositeComponentFileError("Composite component file is missing a definition object.")

    definition = CompositeComponentDefinition.from_dict(raw_definition)
    if not definition.composite_id:
        raise CompositeComponentFileError("Composite component definition is missing an id.")
    if not definition.name.strip():
        raise CompositeComponentFileError("Composite component definition is missing a name.")

    return definition


def unique_imported_composite_name(name: str, existing_names: set[str]) -> str:
    base_name = name.strip() or "Imported Composite"
    lowered_existing = {existing.lower() for existing in existing_names}

    if base_name.lower() not in lowered_existing:
        return base_name

    imported_name = f"{base_name} (Imported)"
    if imported_name.lower() not in lowered_existing:
        return imported_name

    index = 2
    while True:
        candidate = f"{base_name} (Imported {index})"
        if candidate.lower() not in lowered_existing:
            return candidate
        index += 1


def import_composite_component_file(file_path: str | Path) -> CompositeComponentDefinition:
    definition = read_composite_component_file(file_path)

    existing = get_composite_component_definition(definition.composite_id)
    if existing is None:
        existing_names = {
            item.name
            for item in list_composite_component_definitions()
            if item.composite_id != definition.composite_id
        }
        definition.name = unique_imported_composite_name(definition.name, existing_names)

    return save_composite_component_definition(definition)
