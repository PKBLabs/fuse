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
"""Helpers for visual SubComponent attachment semantics.

SST historically used a handful of SubComponent parameters, such as ``port``,
to tell Python configuration scripts how an anonymous SubComponent was wired
into its parent. FUSE stores that relationship explicitly as a
``ModelSubcompAttachment`` edge, so those legacy wiring parameters should not
make visual SubComponent assignments fail validation.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


_VISUAL_CONNECTION_PARAMETER_NAMES = {
    "port",
    "port_name",
}

_VISUAL_CONNECTION_PARAMETER_SUFFIXES = (
    ".port",
)

_VISUAL_CONNECTION_DESCRIPTION_MARKERS = (
    "set by parent component",
    "used by parent component",
    "loaded anonymously",
    "named subcomponent",
    "subcomponent slot is filled",
    "slot should be filled",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def is_visual_subcomponent_connection_parameter(
    parameter: Mapping[str, Any] | str,
    *,
    component_is_subcomponent: bool = True,
) -> bool:
    """Return true for legacy wiring params replaced by visual attachments.

    The match is intentionally conservative. It catches the known SST patterns
    that represent parent/slot wiring without suppressing unrelated required
    parameters such as ``local_ports`` or ``oql_track_port``.
    """

    if not component_is_subcomponent:
        return False

    if isinstance(parameter, str):
        name = parameter
        description = ""
    else:
        name = _text(parameter.get("name", ""))
        description = _text(parameter.get("description", ""))

    normalized_name = name.lower()
    normalized_description = description.lower()

    if normalized_name in _VISUAL_CONNECTION_PARAMETER_NAMES:
        return True

    if normalized_name.endswith(_VISUAL_CONNECTION_PARAMETER_SUFFIXES):
        return True

    if "port" not in normalized_name and "port" not in normalized_description:
        return False

    return any(
        marker in normalized_description
        for marker in _VISUAL_CONNECTION_DESCRIPTION_MARKERS
    )


def mark_visual_subcomponent_connection_parameters_optional(
    parameters: list[dict[str, Any]],
    *,
    component_is_subcomponent: bool,
) -> list[dict[str, Any]]:
    """Return copied parameter dictionaries with legacy wiring params optional."""

    normalized: list[dict[str, Any]] = []

    for parameter in parameters:
        copied = dict(parameter)
        if is_visual_subcomponent_connection_parameter(
            copied,
            component_is_subcomponent=component_is_subcomponent,
        ):
            copied["required"] = False
            copied["visual_connection_parameter"] = True
        normalized.append(copied)

    return normalized
